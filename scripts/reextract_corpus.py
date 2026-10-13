"""
OpenArt — combined re-extraction of the whole corpus (workflow.MD, "Step 3 — combined re-extraction").

Every page extraction has seen (accepted in data/raw/**, rejected in data/rejected/) is run again
through the current extract_opportunity(): linked call PDFs, the three-way requirements split,
the agent fields, and the code-side rules (individuals only, past deadline, verbatim check).
Records are cached as seen, so a normal pipeline run never redoes them; this script does.

    scan     fetch every page (no model calls): which call PDFs it links, whether it still loads.
             Also writes data/site_wide_pdfs.txt: PDFs linked from >= SITE_WIDE_MIN_PAGES pages.
    extract  re-run the real extraction on every page that still loads (paid: one mini-model
             call each), WORKERS pages at a time. --limit N for a pilot. --no-rules: only the
             published calls where the engine finds no rule at all, and the accepted pages the old
             fetch read badly (< MIN_SCOPE_CHARS of text, or broken characters), re-run even if done before (2026-10-13).
    report   compare old vs new per page -> data/refresh/report.md
    apply    write the results into data/raw/** and data/rejected/, and drop the changed ids from
             data/processed/opportunities.jsonl so the downstream stages redo them.

scan, extract and report never change data/raw, data/rejected or data/processed: only apply does
(data/ is a git repo, so apply can be undone). Every stage saves under data/refresh/ and skips
what it already did, so an interrupted run continues where it stopped and nothing is fetched or
billed twice.

Usage:
    uv run python scripts/reextract_corpus.py scan
    uv run python scripts/reextract_corpus.py extract [--limit 20] [--no-rules]
    uv run python scripts/reextract_corpus.py report
    uv run python scripts/reextract_corpus.py apply
"""

import argparse
import glob
import json
import os
import random
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(REPO_ROOT)
load_dotenv(os.path.join(REPO_ROOT, ".env"))

from src.collectors.crawler import HEADERS  # noqa: E402
from src.collectors.extraction import (MIN_SCOPE_CHARS, SITE_WIDE_MIN_PAGES, SITE_WIDE_PDFS_PATH,  # noqa: E402
                                       content_scope, deadline_has_passed, extract_opportunity,
                                       find_pdf_links, source_language)
from src.collectors.jsonl import load_jsonl, write_jsonl  # noqa: E402
from src.models.opportunity import RawOpportunity  # noqa: E402
from src.models.processed_opportunity import ProcessedOpportunity  # noqa: E402
from src.models.rejected_url import RejectedUrl  # noqa: E402

RAW_DIR = os.path.join(REPO_ROOT, "data", "raw")
REJECTED_DIR = os.path.join(REPO_ROOT, "data", "rejected")
PROCESSED_PATH = os.path.join(REPO_ROOT, "data", "processed", "opportunities.jsonl")
REFRESH_DIR = os.path.join(REPO_ROOT, "data", "refresh")
SCAN_PATH = os.path.join(REFRESH_DIR, "pdf_scan.jsonl")        # one line per page: call PDFs, or the fetch error
EXTRACT_PATH = os.path.join(REFRESH_DIR, "reextract.jsonl")    # one line per re-extracted page
REPORT_PATH = os.path.join(REFRESH_DIR, "report.md")
WORKERS = 6       # pages extracted at the same time: fetching + one model call is ~10-15 s per page
PILOT_SEED = 20261012
MOJIBAKE = ("Ã¼", "Ã¶", "Ã¤", "Ã©", "Ã¨", "â€")   # UTF-8 read as Latin-1: a page the old fetch read badly


# -- shared helpers --------------------------------------------------------------------------------

def load_pages() -> list[dict]:
    """Every page extraction has seen: {id, url, source, status, old} with old = the stored record."""
    pages = []
    for path in sorted(glob.glob(os.path.join(RAW_DIR, "*", "opportunities.jsonl"))):
        for r in load_jsonl(path, RawOpportunity):
            pages.append({"id": r.id, "url": r.source_url, "source": r.source, "status": "accepted",
                          "old": r.model_dump(mode="json")})
    for path in sorted(glob.glob(os.path.join(REJECTED_DIR, "*.jsonl"))):
        for r in load_jsonl(path, RejectedUrl):
            pages.append({"id": r.id, "url": r.url, "source": r.source, "status": "rejected",
                          "old": r.model_dump(mode="json")})
    return pages


def load_done(path: str) -> dict[str, dict]:
    """A stage's saved results, by page id (empty if the stage never ran)."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return {row["id"]: row for row in map(json.loads, f) if row}


_append_lock = threading.Lock()


def append(path: str, row: dict) -> None:
    """Saves one result right away, so an interrupted run loses nothing (thread-safe)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with _append_lock, open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_results(pages: dict) -> dict[str, dict]:
    """The saved extraction results, with the past-deadline rule applied again to every new record.

    The rule is code only, so a fix to it (e.g. after the full run, for "1 February 2015") reaches
    every result without paying for the model calls again.
    """
    results = {}
    for page_id, res in load_done(EXTRACT_PATH).items():
        if page_id not in pages:
            continue
        if res["record"]:
            record = RawOpportunity.model_validate(res["record"])
            if deadline_has_passed(record, source_language(record.source)):
                res = {**res, "record": None, "reason": f"deadline passed ({record.deadline})"}
        results[page_id] = res
    return results


def is_fetch_error(result: dict) -> bool:
    return result["record"] is None and (result["reason"] or "").startswith("fetch/extract error")


# -- stage 1: scan (free) --------------------------------------------------------------------------

def scan() -> None:
    pages = load_pages()
    done = load_done(SCAN_PATH)
    todo = [p for p in pages if p["id"] not in done]
    print(f"{len(pages)} pages, {len(done)} already scanned, {len(todo)} to go")

    for i, page in enumerate(todo, 1):
        row = {"id": page["id"], "url": page["url"], "pdfs": [], "error": None}
        if page["url"].lower().endswith(".pdf"):
            row["error"] = "page is itself a PDF"   # nothing linked to read: already handled before
        else:
            try:
                resp = requests.get(page["url"], headers=HEADERS, timeout=20)
                resp.raise_for_status()
                if "application/pdf" in resp.headers.get("Content-Type", ""):
                    row["error"] = "page is itself a PDF"
                else:
                    # same soup and scope as fetch_page(), so the scan finds exactly what extraction will
                    soup = BeautifulSoup(resp.text, "html.parser")
                    scope = content_scope(soup)
                    row["pdfs"] = find_pdf_links(soup, scope, page["url"])
            except Exception as e:
                row["error"] = f"{e.__class__.__name__}: {e}"[:200]
        append(SCAN_PATH, row)
        if row["pdfs"]:
            print(f"[{i}/{len(todo)}] {len(row['pdfs'])} PDF(s)  {page['url']}")

    done = load_done(SCAN_PATH)
    with_pdfs = [r for r in done.values() if r["pdfs"]]
    errors = Counter((r["error"] or "").split(":")[0] for r in done.values() if r["error"])
    print(f"\nScanned {len(done)} pages: {len(with_pdfs)} link call PDFs. Not scannable: {dict(errors)}")

    # site-wide PDFs: linked from many pages, so the organisation's general rules, not a call's own
    links = Counter(url for r in done.values() for url, _ in r["pdfs"])
    site_wide = sorted(url for url, n in links.items() if n >= SITE_WIDE_MIN_PAGES)
    with open(SITE_WIDE_PDFS_PATH, "w", encoding="utf-8") as f:
        f.write(f"# PDFs linked from >= {SITE_WIDE_MIN_PAGES} corpus pages: never read as a call's document.\n"
                "# Written by scripts/reextract_corpus.py scan; read by src/collectors/extraction.py.\n")
        f.writelines(f"{url}\n" for url in site_wide)
    print(f"{len(site_wide)} site-wide PDF(s) -> {SITE_WIDE_PDFS_PATH}")


# -- stage 2: extract (paid) -----------------------------------------------------------------------

def no_rules_ids() -> set[str]:
    """Published calls where the engine finds no rule at all: an empty requirements text, or only
    sentences that are not about the applicant. Profile-independent, so an empty profile is enough."""
    from src.eligibility.engine import EligibilityEngine
    from src.eligibility.profile import ArtistProfile
    from src.matching.corpus import load_opportunities

    engine = EligibilityEngine()
    return {o.id for o in load_opportunities()
            if all(item.outcome == "INFO" for item in engine.evaluate(ArtistProfile(), o).items)}


def extract(limit: int | None, no_rules: bool = False) -> None:
    from openai import OpenAI   # only this stage needs the API key

    pages = {p["id"]: p for p in load_pages()}
    scanned = load_done(SCAN_PATH)
    # every page that still loads; a page that is itself a PDF loads too (extraction reads it)
    candidates = [i for i in pages if i in scanned and scanned[i]["error"] in (None, "page is itself a PDF")]
    done = load_done(EXTRACT_PATH)
    if no_rules:
        # re-run even if done: the newer line wins in load_done(), so report/apply see the new result
        read_badly = {i for i, p in pages.items() if len(p["old"].get("source_text") or "") < MIN_SCOPE_CHARS
                      or any(m in (p["old"].get("source_text") or "") for m in MOJIBAKE)}
        wanted = no_rules_ids() | read_badly
        todo = [i for i in candidates if i in wanted and pages[i]["status"] == "accepted"]
    else:
        todo = [i for i in candidates if i not in done]
    if limit is not None and no_rules:
        todo = sorted(todo)
        random.Random(PILOT_SEED).shuffle(todo)
        todo = todo[:limit]
    elif limit is not None:
        # a pilot: a fixed random sample, half accepted and half rejected pages where possible
        rng = random.Random(PILOT_SEED)
        accepted = [i for i in todo if pages[i]["status"] == "accepted"]
        rejected = [i for i in todo if pages[i]["status"] == "rejected"]
        rng.shuffle(accepted), rng.shuffle(rejected)
        todo = accepted[:limit - limit // 2] + rejected[:limit // 2]
    print(f"{len(candidates)} pages still load, {len(done)} already re-extracted, {len(todo)} to go now")

    client = OpenAI()
    counter = Counter()

    def one(page_id: str) -> None:
        page = pages[page_id]
        row = {"id": page_id, "record": None, "reason": None, "tokens": None}
        try:
            record, reason = extract_opportunity(client, page["url"], page["source"])
            row["record"] = record.model_dump(mode="json") if record else None
            row["reason"] = reason
        except Exception as e:
            row["reason"] = f"fetch/extract error: {e}"[:300]
        append(EXTRACT_PATH, row)
        with _append_lock:
            counter["done"] += 1
            print(f"[{counter['done']}/{len(todo)}] {'accepted' if row['record'] else 'rejected'}  {page['url']}"
                  + ("" if row["record"] else f"  ({row['reason'][:80]})"))

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(one, todo))


# -- stage 3: report -------------------------------------------------------------------------------

def _short(text: str | None, n: int = 300) -> str:
    return repr(text if text is None or len(text) <= n else text[:n] + "…")


def report() -> None:
    pages = {p["id"]: p for p in load_pages()}
    results = list(load_results(pages).values())
    accepted_new = [r["record"] for r in results if r["record"]]

    groups: dict[str, list[tuple[dict, dict]]] = {
        "rejected → accepted": [], "accepted → rejected": [],
        "accepted → accepted, requirements changed": [], "accepted → accepted, requirements unchanged": [],
        "rejected → rejected": [], "errors": [],
    }
    for res in results:
        page = pages[res["id"]]
        new_ok = res["record"] is not None
        if is_fetch_error(res):
            groups["errors"].append((page, res))
        elif page["status"] == "rejected":
            groups["rejected → accepted" if new_ok else "rejected → rejected"].append((page, res))
        elif not new_ok:
            groups["accepted → rejected"].append((page, res))
        else:
            same = page["old"]["requirements_text"] == res["record"]["requirements_text"]
            groups[f"accepted → accepted, requirements {'unchanged' if same else 'changed'}"].append((page, res))

    def reason_kind(reason: str) -> str:
        for kind in ("deadline passed", "not open to individuals", "fetch/extract error"):
            if reason.startswith(kind):
                return kind
        return "other (model's own reason)"

    reasons = Counter(reason_kind(r["reason"] or "") for r in results if not r["record"])
    old_len = [len(pages[r["id"]]["old"]["requirements_text"]) for r in results
               if r["record"] and pages[r["id"]]["status"] == "accepted"]
    new_len = [len(r["record"]["requirements_text"]) for r in results
               if r["record"] and pages[r["id"]]["status"] == "accepted"]
    flagged = Counter(f.split("[")[0] for rec in accepted_new for f in rec["verbatim_flags"])
    filled = {f: sum(1 for rec in accepted_new if rec.get(f)) for f in
              ("project_requirements", "how_to_apply", "application_questions", "required_materials",
               "selection_criteria", "application_language", "submission_method", "program_dates")}

    n_acc = max(len(accepted_new), 1)
    lines = ["# Combined re-extraction: report", "",
             f"{len(results)} pages re-extracted. Nothing in data/raw, data/rejected or data/processed "
             "has been changed (that is the `apply` stage).", "",
             "| Outcome | Pages |", "|---|---|"]
    lines += [f"| {name} | {len(items)} |" for name, items in groups.items()]
    lines += ["", "**Why pages are rejected now**", "", "| Reason | Pages |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in reasons.most_common()]
    if old_len:
        lines += ["", f"**Applicant requirements length** (pages accepted before and now, n = {len(old_len)}): "
                      f"mean {sum(old_len) / len(old_len):.0f} → {sum(new_len) / len(new_len):.0f} characters."]
    lines += ["", f"**New fields filled** (of {len(accepted_new)} accepted):", ""]
    lines += [f"- {f}: {n} ({n / n_acc:.0%})" for f, n in filled.items()]
    lines += ["", f"**Verbatim flags** (field not found word for word in the page): "
                  f"{sum(1 for rec in accepted_new if rec['verbatim_flags'])} of {len(accepted_new)} records "
                  f"have one. By field: {dict(flagged.most_common())}"]

    for name, items in groups.items():
        if not items or name in ("rejected → rejected", "accepted → accepted, requirements unchanged"):
            continue   # counted above; no change to review
        lines += ["", f"## {name} ({len(items)})"]
        for page, res in items:
            new = res["record"] or {}
            old = page["old"]
            lines += ["", f"### {new.get('title') or old.get('title') or old.get('title_guess')}",
                      f"- page: {page['url']}"]
            lines += [f"- PDF: {u}" for u in new.get("document_urls", [])]
            if page["status"] == "rejected":
                lines.append(f"- old: rejected — {old['reason']}")
            else:
                lines.append(f"- old deadline: {old.get('deadline')!r}")
                lines.append(f"- old requirements ({len(old['requirements_text'])} chars): "
                             f"{_short(old['requirements_text'])}")
            if not res["record"]:
                lines.append(f"- new: rejected — {res['reason']}")
                continue
            lines.append(f"- new deadline: {new.get('deadline')!r}  open to: {new.get('open_to')}")
            lines.append(f"- new applicant requirements ({len(new['requirements_text'])} chars): "
                         f"{_short(new['requirements_text'])}")
            lines.append(f"- new project requirements: {_short(new.get('project_requirements'), 200)}")
            lines.append(f"- new description: {_short(new.get('description'), 400)}")
            if page["status"] == "accepted" and old.get("description") != new.get("description"):
                lines.append(f"- old description: {_short(old.get('description'), 200)}")
            if new.get("verbatim_flags"):
                lines.append(f"- verbatim flags: {new['verbatim_flags']}")

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines[:40]))
    print(f"\nFull report -> {REPORT_PATH}")


# -- stage 4: apply (writes data/) -----------------------------------------------------------------

def apply() -> None:
    """Writes the re-extraction into data/raw/** and data/rejected/ (see workflow.MD, Step 3 "Apply").

    - new accepted record -> data/raw/<source>/opportunities.jsonl (out of rejected if it was there)
    - new rejection       -> data/rejected/<source>.jsonl (out of raw if it was there)
    - page no longer loads -> left as it is, except an accepted record whose deadline has passed:
      it is rejected with "deadline passed" like every re-extracted one
    Every id whose raw record changed or left is dropped from data/processed, so normalize redoes it.
    """
    pages = {p["id"]: p for p in load_pages()}
    results = load_results(pages)
    now = datetime.now(timezone.utc)

    raw = {}       # source -> {id: RawOpportunity}
    rejected = {}  # source -> {id: RejectedUrl}
    for path in glob.glob(os.path.join(RAW_DIR, "*", "opportunities.jsonl")):
        source = os.path.basename(os.path.dirname(path))
        raw[source] = {r.id: r for r in load_jsonl(path, RawOpportunity)}
    for path in glob.glob(os.path.join(REJECTED_DIR, "*.jsonl")):
        source = os.path.basename(path)[:-len(".jsonl")]
        rejected[source] = {r.id: r for r in load_jsonl(path, RejectedUrl)}

    def reject(page: dict, reason: str) -> None:
        old = page["old"]
        raw.get(page["source"], {}).pop(page["id"], None)
        rejected.setdefault(page["source"], {})[page["id"]] = RejectedUrl(
            id=page["id"], url=page["url"], source=page["source"],
            title_guess=old.get("title") or old.get("title_guess") or "", reason=reason, rejected_at=now)

    changed, counts = set(), Counter()
    for page_id, page in pages.items():
        res = results.get(page_id)
        if res is None or is_fetch_error(res):
            # not re-extracted (page gone or fetch failed): only the deadline rule applies
            if page["status"] == "accepted":
                old = RawOpportunity.model_validate(page["old"])
                if deadline_has_passed(old, source_language(page["source"])):
                    reject(page, f"deadline passed ({old.deadline})")
                    changed.add(page_id)
                    counts["not re-extracted, deadline passed → rejected"] += 1
                else:
                    counts["not re-extracted, kept as it was"] += 1
            continue
        if res["record"]:
            record = RawOpportunity.model_validate(res["record"])
            rejected.get(page["source"], {}).pop(page_id, None)
            if raw.get(page["source"], {}).get(page_id) != record:   # re-running apply redoes nothing
                raw.setdefault(page["source"], {})[page_id] = record
                changed.add(page_id)
            counts["accepted"] += 1
        else:
            if page_id in raw.get(page["source"], {}):
                changed.add(page_id)
            reject(page, res["reason"])
            counts["rejected"] += 1

    for source, records in raw.items():
        write_jsonl(list(records.values()), os.path.join(RAW_DIR, source, "opportunities.jsonl"))
    for source, records in rejected.items():
        write_jsonl(list(records.values()), os.path.join(REJECTED_DIR, f"{source}.jsonl"))

    processed = load_jsonl(PROCESSED_PATH, ProcessedOpportunity)
    kept = [p for p in processed if p.id not in changed]
    write_jsonl(kept, PROCESSED_PATH)

    print(dict(counts))
    print(f"data/processed: {len(processed) - len(kept)} records dropped for reprocessing, {len(kept)} kept")
    print("Next: normalize -> canonicalize -> extract funding -> export -> extract_constraints -> "
          "build_match_index (workflow.MD, Step 3 'Apply').")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stage", choices=["scan", "extract", "report", "apply"])
    parser.add_argument("--limit", type=int, default=None, help="extract: only this many pages (a pilot)")
    parser.add_argument("--no-rules", action="store_true",
                        help="extract: only the published calls where the engine finds no rule (re-run)")
    args = parser.parse_args()
    if args.stage == "extract":
        extract(args.limit, args.no_rules)
    else:
        {"scan": scan, "report": report, "apply": apply}[args.stage]()
