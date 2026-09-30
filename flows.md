## CRAWLING → EXTRACTION → PROCESSING PIPELINE

One-command run: `uv run python scripts/run_pipeline.py`. Every stage
persists to JSONL merged by id (`sha256(source_url)`), so re-running only
spends on rows it hasn't seen — safe to interrupt and resume, never produces
duplicates. Full design rationale lives in `workflow.MD`; this is the
five-minute version.

### End-to-end flow

```mermaid
flowchart TD
    SRC["data/sources.yaml\n(human-curated listing pages)"]
    MAN["data/manual/intake.csv\n(hand-filled, no crawler)"]

    SRC --> CRAWL["crawler.py — Discovery\n1 LLM call: classify links + find pagination"]
    CRAWL --> DISC["data/discovered/*.jsonl\n(candidate URLs)"]
    DISC --> EXTR["extraction.py — Extraction\n1 LLM call: extract fields + is_open_call"]
    MAN --> MANUAL["manual_entry.py"]

    EXTR -- rejected --> REJ["data/rejected/*.jsonl\n(cached, never re-billed)"]
    EXTR -- accepted --> RAW["data/raw/**\nRawOpportunity"]
    MANUAL --> RAW

    RAW --> NORM["normalize.py — Normalization\ndeadline parsing · translation ·\ncanonicalization · funding extraction"]
    NORM --> PROC["data/processed/opportunities.jsonl\nProcessedOpportunity"]
    PROC --> EXPORT["export_dataset.py\ndrop content-duplicates"]
    EXPORT --> OUT["dataset/opportunities.csv\npublished — EDA + RQ1 input"]

    style SRC fill:#2a78d6,color:#fff
    style OUT fill:#1baf7a,color:#fff
    style REJ fill:#e1e0d9,color:#333
```

`data/` (raw/discovered/rejected/processed/manual) is its own nested,
gitignored local repo — none of it is published. `dataset/opportunities.csv`
is the one file this project actually ships.

### Stage by stage

| Stage | Script | Reads | Writes | LLM call? |
|---|---|---|---|---|
| Discovery | `src/collectors/crawler.py` | `sources.yaml` listing page | `data/discovered/` | Yes — classify harvested links as real opportunities vs. noise |
| Extraction | `src/collectors/extraction.py` | each discovered URL (HTML/PDF) | `data/raw/**` or `data/rejected/` | Yes — extract fields + accept/reject, `temperature=0` |
| Manual entry | `src/collectors/manual_entry.py` | `data/manual/intake.csv` | `data/raw/**` | No |
| Normalization | `src/processing/normalize.py` | `data/raw/**` | `data/processed/opportunities.jsonl` | Yes, only if source language ≠ English (translation) |
| Export | `scripts/export_dataset.py` | `data/processed/opportunities.jsonl` | `dataset/opportunities.csv` | No |

All LLM stages call `gpt-5.4-mini` via `client.chat.completions.parse()`
with a pydantic `response_format` — schema-constrained extraction/
classification/translation, not reasoning work.

### Why two LLM calls, not one

Discovery is deliberately **recall-oriented**: an ambiguous link (could be a
live call, could be retrospective news) gets kept rather than guessed away,
because that distinction usually isn't decidable from anchor text alone.
Extraction is where that ambiguity actually gets resolved — it reads the
whole fetched page, so it can tell a genuinely closed or non-eligibility
page apart from a real open call. Splitting the two steps keeps each
LLM call scoped to what it can actually see.

### Cost guards (why re-running is cheap)

```mermaid
flowchart LR
    P["source's listing page"] --> H{"page hash\nunchanged since\nlast crawl?"}
    H -- yes --> SKIP["skip — 0 LLM calls"]
    H -- no --> SEEN{"link already\nin seen_ids?"}
    SEEN -- yes --> DROP["drop before\nclassify_links()"]
    SEEN -- no --> CLASSIFY["classify_links()\n1 LLM call per new link batch"]
```

- **Discovery**: a hash of each page's harvested candidate links (not raw
  HTML, so a stray timestamp/CSRF token can't trigger a false "changed") is
  cached in `data/discovered/_page_hashes.json` — an unchanged page skips
  the classify call entirely. Already-seen candidates are filtered out
  *before* classification too.
- **Extraction**: rejected URLs are cached in `data/rejected/` and never
  re-fetched; accepted ones are cached in `data/raw/**` by id. Force a
  re-check by deleting the specific cached line.
- **Normalization**: merges by id like every other stage — only rows not
  already in `data/processed/opportunities.jsonl` get (re-)translated.

### What normalization actually adds

`RawOpportunity` fields are carried through verbatim — normalization never
rewrites `requirements_text`/`title`, it only adds alongside them:

| Raw field | Processed additions |
|---|---|
| `deadline` (literal string) | `deadline_date` — parsed via `dateparser`, restricted to `[source_language, "en"]` to avoid cross-language misparses |
| `title`, `requirements_text`, `description` | `*_en` — machine-translated only if the source's declared language isn't English |
| `discipline`, `opportunity_type`, `career_stage`, `country` | `*_en` translation **and** `*_canonical` — mapped onto a fixed controlled vocabulary (list-valued; a source value can name several categories at once) |
| `city` | `city_en` only — no fixed vocabulary for an open field |
| `funding`, `application_fee` | structured extraction: `funding_components` (list of `{category, amount_min, amount_max, currency, period, note}`) and `application_fee_has_fee`/`_amount_min`/`_amount_max`/`_currency` |

Language is tagged **per source**, by hand, in `sources.yaml` — not
auto-detected — since each source's language was already confirmed while
curating it.

### Downstream of this pipeline

```
dataset/opportunities.csv ──► notebooks/eda.ipynb (Acts I–III)
                          ──► scripts/select_annotation_candidates.py ──► data/labels/candidate_chunks.csv
                                                                       ──► scripts/label_chunks.py ──► data/labels/eligibility_annotations.csv (RQ1 training data)
```


## Annotation flow

Two scripts, no LLM call baked into either — this is regex-based chunking
plus a plain CLI labeling loop. Full taxonomy, edge-case rules and the
decision log live in `ANNOTATION_GUIDELINES.md`; this is the five-minute
version.

### End-to-end flow

```mermaid
flowchart TD
    OUT["dataset/opportunities.csv\n(published corpus)"]
    OUT --> SEL["select_annotation_candidates.py\nsentence/bullet regex-split each\nrequirements_text_en · random opportunity\nsample · per-source cap"]
    SEL --> CAND["dataset/labels/candidate_chunks.csv\n(intermediate, not the deliverable)"]
    CAND --> LAB["label_chunks.py\ninteractive CLI, one chunk at a time,\nresumable — no LLM call in the tool itself"]
    LAB -- labeled --> ANN["dataset/labels/eligibility_annotations.csv\n(RQ1 training data)"]
    LAB -- set aside --> SKIP["dataset/labels/skipped_chunks.csv\n(malformed splits, not force-labeled)"]
    CAND --> EXT["extend_annotation_candidates.py\nround 2: +350 random, +92 keyword-targeted\n(appends, never touches round 1)"]
    EXT --> PRE["pre-labels (Claude Code session)\n→ eligibility_annotations.csv"]
    PRE --> REV["dataset/labels/review/\nblind 10% sample + flagged rows"]
    REV --> APPLY["apply_label_review.py\nhuman label wins · Cohen's kappa"]
    APPLY --> ANN

    style OUT fill:#2a78d6,color:#fff
    style ANN fill:#1baf7a,color:#fff
    style SKIP fill:#e1e0d9,color:#333
```

### Stage by stage

| Stage | Script | Reads | Writes | LLM call? |
|---|---|---|---|---|
| Candidate selection | `scripts/select_annotation_candidates.py` | `dataset/opportunities.csv` | `dataset/labels/candidate_chunks.csv` | No — regex sentence/bullet splitting, then whole opportunities sampled at random (never cherry-picked) with a per-source cap |
| Labeling | `scripts/label_chunks.py` | `dataset/labels/candidate_chunks.csv` | `dataset/labels/eligibility_annotations.csv`, `dataset/labels/skipped_chunks.csv` | No — a plain CLI prompt against the 9-class taxonomy; the labels themselves were applied by a human/Claude Code session following `ANNOTATION_GUIDELINES.md`, not generated by a model call |

### Round 2: from 292 to 678 labeled rows

Added because the learning curve showed the embeddings model still
improving with more data (see "Would more annotated data help?" below).
Two batches, tagged in `candidate_chunks.csv`'s `batch` column:
**random** (350 chunks, 76 whole opportunities — same method as round 1,
keeps the class mix realistic) and **targeted** (92 chunks keyword-matched
to the thin classes). Labeled by a Claude Code session against the
guidelines — 386 rows after splits, 100 set aside (form-field residue,
untranslated text, broken splits) — then reviewed by the human annotator:

- **Blind sample** (`review/round2_blind.csv`): a random 10%, pre-label
  hidden, labeled from scratch → **measured human-vs-LLM agreement
  (Cohen's kappa)**. This puts a number on label quality and on the
  "agreement bias" caveat of the LLM reference model.
- **Flagged rows** (`review/round2_flagged.csv`): every pre-label the
  session marked uncertain, with its reason.

`scripts/apply_label_review.py` applies the decisions (human always
wins) and saves the agreement to `review/round2_agreement.json`;
`scripts/review_labels.py` is the CLI used to fill the two files.

**Result: Cohen's kappa 0.675 (74.4% raw agreement)** on the blind
sample — "substantial" agreement. The 10 disagreements cluster on the
boundaries the guidelines already call hard (EDUCATION / STUDENT_STATUS
/ CAREER_STAGE, organisation type vs. RESIDENCE). Nine reviewer answers
that contradicted a written rule were adjudicated back to the rule
(`review/round2_adjudication.csv`); kappa is computed *before* that
step, on the reviewer's original answers. Full rules, patterns and the
EDUCATION finding: `ANNOTATION_GUIDELINES.md` §6.

### Why sample whole opportunities, not chunks directly

Selecting whole opportunities at random and taking every sentence from
each — rather than hand-picking "eligibility-looking" chunks — keeps
`NONE` naturally represented instead of silently under-sampled, and
matches how a classifier will actually see text at inference (a full
call's sentences, not pre-filtered ones). The per-source cap (18% of
target, recomputed live against the current corpus each run rather than
trusting a stale percentage) stops one prolific source's boilerplate
phrasing from dominating the labeled sample — same reasoning as
`workflow.MD`'s corpus-imbalance note, applied at sampling time.

### Result

**678 labeled chunks across 217 opportunities** after two rounds, all 9
classes represented (EDUCATION 15 … NONE 194) —
`dataset/labels/eligibility_annotations.csv`, the training data for the
eligibility classifier. Round 1, below, produced the first 292 (79
opportunities). 3 opportunities with a
broken `requirements_text` were excluded before chunking (§0); 27 chunks
sit in `skipped_chunks.csv` instead of being force-labeled — 17 malformed
splits set aside during labeling, plus 10 bare section headings ("Who can
apply?", "Eligible applicants") removed after the baseline showed them
teaching the model that eligibility vocabulary means `NONE`
(`ANNOTATION_GUIDELINES.md` §6, 2026-09-29). A model-assisted label audit
of the baseline's top-30 confident errors changed 4 labels (same §6).


## Eligibility classifier (RQ1)

`notebooks/eligibility_classifier.ipynb`. Validation is 5-fold
`StratifiedGroupKFold` grouped by `opportunity_id`: stratified because
the 9 classes are imbalanced (15–194), grouped because chunks from the
same call share phrasing and would otherwise leak across train/test.
Every model is compared on these same folds, macro-F1 as the headline
metric.

All numbers on the final 678-row set; round-1 (292 rows) in brackets,
kept because the change between the two is itself a finding.

| Model | Mean CV macro-F1 | Notes |
|---|---|---|
| TF-IDF + Logistic Regression (baseline) | 0.707 *(0.625)* | `class_weight='balanced'`, `GridSearchCV` over `C`, n-gram range, `min_df`; best C=1, unigrams, min_df=1 |
| TF-IDF + Linear SVM | 0.681 *(0.643)* | same TF-IDF grid, best C=0.1. **Now below the baseline** on all 5 folds — its round-1 edge did not survive more data |
| **Sentence embeddings (`bge-base-en-v1.5`) + LogReg** | **0.740** *(0.723)* | frozen embeddings via `fastembed`, best C=10. Best trained model; beats the baseline on 4 of 5 folds. LogReg kept over LinearSVC on the embeddings (0.740 vs 0.722, ahead on 3 of 5 folds): isolates the representation change, and gives probabilities for routing low-confidence labels to human review |
| OpenAI LLM, few-shot (reference only, not a product candidate) | 0.767 *(0.766)* | `gpt-5.4-mini`, temperature 0, taxonomy in the prompt + 2 examples per label drawn from each fold's *training* chunks only; answers cached in `notebooks/cache/llm_predictions.jsonl`. Gap to the embeddings model narrowed from 0.043 to 0.027, and the embeddings model now wins 3 of 5 folds against it |

### What round 2 changed

- **Every trained model improved, TF-IDF the most** (+0.08, vs +0.02 for
  embeddings) — exactly the learning curve's prediction: TF-IDF only
  knows words it has seen, so it's the model most starved for data.
- **The SVM's round-1 win was small-sample noise.** At 292 rows it beat
  the baseline on all 5 folds by +0.018; at 678 it loses on all 5. A
  consistent win on ~60-chunk test folds was still not a robust one —
  worth saying in the presentation as a lesson about small evaluations.
  (Its best C also moved from the grid edge, where the classes were
  trivially separable, to 0.1: with more data, regularisation matters.)
- **Embeddings are still the best trained model, by a smaller margin**
  (+0.033 over the baseline instead of +0.098): the representation
  matters most when data is scarce.
- **Smaller gain than the round-1 learning curve suggested** (+0.017
  where "a few points" was projected). The two sets aren't like for
  like — round 2 added 138 new opportunities and a targeted batch aimed
  at hard boundary cases — and the labels themselves set a ceiling: the
  blind review found ~26% disagreement between the pre-labels and the
  human reviewer on round-2 chunks, and the best model's accuracy (72%) is already
  close to that level of label consistency. More data alone won't push
  much further; clearer class boundaries would.

### Final model

The chosen model is refit on all 678 chunks and saved to
`artifacts/eligibility_classifier.joblib`, with a metadata file
(`eligibility_classifier.json`) recording the embedding model it
expects and its CV score. Its expected quality is the CV estimate
(0.740 macro-F1). The product embeds each chunk with the same
`bge-base-en-v1.5` model, and the classifier returns a label plus
probabilities, so low-confidence labels can go to human review. Details:
`workflow.MD`, "Final model artifact".

### Why the baseline scores low — known limitations

The densest error cluster is `NONE` ↔ `DISCIPLINE`. Once the heading
artifacts were removed, what's left comes from two things bag-of-words
TF-IDF structurally can't handle, not from labeling or tuning:

1. **Arts vocabulary in non-constraint sentences.** Project and delivery
   descriptions ("you will work with … arts, cultural or creative
   organisations", "we welcome experimental forms … art and high
   culture") are `NONE`, but they're full of the same words as real
   `DISCIPLINE` constraints. TF-IDF counts words; it can't tell "the
   project involves X" from "the applicant must be X".
2. **Discipline terms too rare to learn.** Real `DISCIPLINE` chunks
   name specific practices ("early music", "dancers and circus
   artists", "costume designers", "translators") that each appear once
   or twice in round 1's 292 chunks. TF-IDF has no notion that "dancers",
   "performers" and "choreographic" are related, so an unseen term
   carries no signal and the chunk falls to `NONE`.

Both are the motivation for the sentence-embedding classifier (and its results bear the diagnosis out — see the table):
embeddings put related practices near each other and encode sentence
structure better than word counts. Deliberately not patched with
hand-built TF-IDF extras — bigrams were already in the grid search and
lost to unigrams, and a hand-curated discipline lexicon would be effort
spent on a model the embedding classifier is expected to replace.

### Would more annotated data help? — learning curve

Last cell of the notebook: each fold's model retrained on 25/50/75/100% of
its training *opportunities* (5 random draws per share), scored on the
untouched test fold.

| Training chunks (avg) | ~143 | ~277 | ~407 | ~542 |
|---|---|---|---|---|
| TF-IDF + LogReg | 0.50 | 0.61 | 0.67 | 0.71 |
| Embeddings + LogReg | 0.61 | 0.68 | 0.72 | 0.74 |

*(On the final 678-row set. On round 1's 292 rows the same curve read
0.50 → 0.61 → 0.70 → 0.72 for embeddings and 0.29 → 0.43 → 0.55 → 0.63
for TF-IDF — which is what motivated round 2.)*

- **Embeddings need far less data than TF-IDF:** with half the chunks
  (~277) they match TF-IDF trained on all of them (0.68 vs 0.71 is
  within one fold's spread), and the gap is widest at the smallest
  size. The pretrained model already knows the language; TF-IDF only
  knows words it has seen. Good presentation point.
- **The embeddings curve is flattening** (+0.07, +0.04, +0.02 per
  quarter): the model is close to what this label set can support —
  see "What round 2 changed".

### Why model 4 is in the comparison — key presentation point

> **1. It answers the obvious question about RQ1: "why not just call an
> LLM?"** Any NLP project today gets asked this. Without model 4 the
> answer is an argument; with it, it's a measurement: **a local model
> that costs nothing per call and always gives the same answer gets
> within ~0.03 macro-F1 of a hosted LLM** (0.740 vs 0.767), and beats
> it on 3 of the 5 folds — and the LLM needed no training data to get
> there.
>
> **2. It turns design decisions into a measured trade-off.** 
> Model 4 puts a number on what those principles cost: **give up ~0.03
> F1, get determinism, zero per-call cost and local execution.** A
> stated preference becomes an evidence-based choice.



### Embedding runtime

Embeddings run on `fastembed` (ONNX Runtime), not `sentence-transformers`
(PyTorch): PyTorch has no build for the Intel-Mac dev machine on Python
3.13, and downgrading Python would have pinned the whole project to
NumPy 1.x and a frozen 2024 torch. Same model weights, same vectors,
smaller deployment footprint, reusable for matching/RAG. Full decision
record, including the alternatives rejected: `workflow.MD`,
"Embedding runtime: fastembed, not PyTorch".
