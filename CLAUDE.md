# OpenArt — Project Context for Claude Code

This file orients any Claude Code session working in this repo. Read it
before making structural decisions, adding dependencies, or proposing
scope changes.

## What this is

A data science project with product potential, so to be implemented professionally, in a secure and accessible way: a system that helps artists discover new opportunities, check eligibility for, and apply to open calls (residencies, grants, commissions). The graded ML core is an eligibility-classification pipeline (RQ1). RAG and an agentic layer complete the project and form the product.

**This must ship as a deployed, working MVP to pass the exam** — not a
notebook demo of RQ1 alone. RQ1 is the graded ML deliverable, but the
full artist-facing product (semantic matching, RAG, application agent)
has to run end-to-end in the deployed app.

## Research questions

- **RQ1 (core, fully built):** Can NLP automatically identify
  eligibility requirements in art open calls?


**Schema — one row per opportunity:**

```
opportunity_id, title, organisation, description, requirements_text,
discipline, opportunity_type, country, city, deadline, funding,
application_fee, career_stage, source_url
```

Keep raw (untouched source text) and processed (normalized fields)
data separate, for reproducibility.

**Eligibility label taxonomy** (sentence/span-level, on
`requirements_text`):

```
RESIDENCE, NATIONALITY, AGE, DISCIPLINE, CAREER_STAGE, EDUCATION,
STUDENT_STATUS, OTHER_ELIGIBILITY, NONE
```

Target 200–300 hand-annotated spans. Single-label per chunk unless
multi-label is trivial to support — don't let annotation scheme
complexity eat the timeline.

## Modeling conventions

Follow the same conventions used across this author's other ML work
(Tunisair delay prediction, King County EDA) — don't introduce a
different stack for novelty's sake:

- `sklearn.Pipeline` + `ColumnTransformer` for mixed feature types
- `GridSearchCV` for hyperparameter search
- Class imbalance: `class_weight='balanced'` (or explicit resampling
  if that proves insufficient) — check imbalance before assuming it's
  needed
- Baseline first, always: TF-IDF + Logistic Regression before anything
  fancier
- Model comparison: baseline → Linear SVM → sentence-embedding
  classifier → (optionally) Gradient Boosting
- Evaluation: accuracy, precision, recall, F1, confusion matrix —
  report all of them, not just accuracy
- Prefer simple, defensible modeling choices over engineering
  complexity the timeline can't afford

**Eligibility engine** (downstream of the classifier): plain Python
rule matching between an extracted artist profile and extracted
opportunity constraints. Output is `ELIGIBLE` / `NOT ELIGIBLE` +
stated reason. This must stay deterministic and auditable — do not
replace this gating logic with an LLM call. That's a considered design
decision (see architecture doc), not a placeholder waiting to be
upgraded.

## Architecture — what's core (graded) vs. supporting (MVP)

| Stage | Status | Notes |
|---|---|---|
| Discovery & cleaning | Supporting | Primary-source ingestion, dedup, normalization |
| EDA | Supporting | Full exploratory pass on the collected corpus |
| Eligibility NLP | **Core (RQ1)** | The graded deliverable — full pipeline |
| Semantic matching | Supporting | Embeddings + filters only, no training |
| RAG (artist knowledge base) | Supporting, deployed | CV/statement/portfolio chunked + embedded; must work end-to-end in the shipped app, not just illustrative |
| Application agent | Supporting, deployed | Drafts applications against real opportunities in the corpus; must run end-to-end in the shipped app, gated by the human-in-the-loop review below |

RAG and the application agent are exam-required MVP features, not
optional demos — don't scope them down to a couple of illustrative
opportunities or a notebook walkthrough. RQ1 stays the only piece that
needs to be *graded* as ML work; everything else needs to actually run.

## Non-negotiable product/design principles

- **Human-in-the-loop is structural, not cosmetic.** Any draft
  application must go through an explicit review-and-confirm step.
  Never wire up auto-submission to an external site or auto-send of a
  message on the user's behalf.

  ## Documentation
  Every workflow, architecture and implementation (except for the obvious) has to be documented in a dedicated file called workflow.MD