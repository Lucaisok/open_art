"""
OpenArt — re-extract existing records whose page links a call PDF (linked-PDFs step 3).

Records extracted before linked PDFs were read (workflow.MD, "Linked PDFs") are cached as
seen, accepted in data/raw/** or rejected in data/rejected/, so a normal pipeline run never
looks at them again. This script redoes them, in three stages. None of them changes
data/raw or data/rejected: applying the results is a separate, later step.

    scan     fetch every accepted/rejected page (no model calls) and note which link call PDFs
    extract  re-run the real extraction on those pages only (paid: one mini-model call each)
    report   compare old vs. new outcome per page -> data/refresh/pdf_report.md

Every stage saves its results under data/refresh/ and skips what it already did, so an
interrupted run continues where it stopped and nothing is fetched or billed twice.

Usage:
    uv run python scripts/refresh_pdf_extraction.py scan
    uv run python scripts/refresh_pdf_extraction.py extract
    uv run python scripts/refresh_pdf_extraction.py report
"""

import argparse
import glob
import json
import os
import sys
from collections import Counter

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(REPO_ROOT)
load_dotenv(os.path.join(REPO_ROOT, ".env"))

from src.collectors.crawler import HEADERS  # noqa: E402
from src.collectors.extraction import extract_opportunity, find_pdf_links  # noqa: E402
from src.collectors.jsonl import load_jsonl  # noqa: E402
from src.models.opportunity import RawOpportunity  # noqa: E402
from src.models.rejected_url import RejectedUrl  # noqa: E402

RAW_DIR = os.path.join(REPO_ROOT, "data", "raw")
REJECTED_DIR = os.path.join(REPO_ROOT, "data", "rejected")
REFRESH_DIR = os.path.join(REPO_ROOT, "data", "refresh")
SCAN_PATH = os.path.join(REFRESH_DIR, "pdf_scan.jsonl")            # one line per page: its call PDFs
EXTRACT_PATH = os.path.join(REFRESH_DIR, "pdf_reextract.jsonl")    # one line per re-extracted page
REPORT_PATH = os.path.join(REFRESH_DIR, "pdf_report.md")


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


def append(path: str, row: dict) -> None:
    """Saves one result right away, so an interrupted run loses nothing."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


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
                    scope = soup.find("article") or soup.find("main") or soup
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


# -- stage 2: extract (paid) -----------------------------------------------------------------------

def extract() -> None:
    from openai import OpenAI   # only this stage needs the API key

    pages = {p["id"]: p for p in load_pages()}
    candidates = [r for r in load_done(SCAN_PATH).values() if r["pdfs"] and r["id"] in pages]
    done = load_done(EXTRACT_PATH)
    todo = [c for c in candidates if c["id"] not in done]
    print(f"{len(candidates)} pages link call PDFs, {len(done)} already re-extracted, {len(todo)} to go")

    client = OpenAI()
    for i, cand in enumerate(todo, 1):
        page = pages[cand["id"]]
        row = {"id": page["id"], "record": None, "reason": None}
        try:
            record, reason = extract_opportunity(client, page["url"], page["source"])
            row["record"] = record.model_dump(mode="json") if record else None
            row["reason"] = reason
        except Exception as e:
            row["reason"] = f"fetch/extract error: {e}"[:300]
        append(EXTRACT_PATH, row)
        print(f"[{i}/{len(todo)}] {'accepted' if row['record'] else 'rejected'}  {page['url']}")


# -- stage 3: report -------------------------------------------------------------------------------

def report() -> None:
    pages = {p["id"]: p for p in load_pages()}
    results = [r for r in load_done(EXTRACT_PATH).values() if r["id"] in pages]

    groups: dict[str, list[tuple[dict, dict]]] = {
        "rejected → accepted": [], "accepted → rejected": [],
        "accepted → accepted, requirements changed": [], "accepted → accepted, requirements unchanged": [],
        "rejected → rejected": [], "errors": [],
    }
    for res in results:
        page = pages[res["id"]]
        new_ok = res["record"] is not None
        if not new_ok and (res["reason"] or "").startswith("fetch/extract error"):
            groups["errors"].append((page, res))
        elif page["status"] == "rejected":
            groups["rejected → accepted" if new_ok else "rejected → rejected"].append((page, res))
        elif not new_ok:
            groups["accepted → rejected"].append((page, res))
        else:
            same = page["old"]["requirements_text"] == res["record"]["requirements_text"]
            key = "unchanged" if same else "changed"
            groups[f"accepted → accepted, requirements {key}"].append((page, res))

    lines = ["# Linked-PDF re-extraction: dry-run report", "",
             f"{len(results)} pages re-extracted with their linked call PDFs. "
             "Nothing in data/raw or data/rejected has been changed.", "", "| Outcome | Pages |", "|---|---|"]
    lines += [f"| {name} | {len(items)} |" for name, items in groups.items()]

    for name, items in groups.items():
        if not items or name in ("rejected → rejected", "accepted → accepted, requirements unchanged"):
            continue   # counted above; no change to review
        lines += ["", f"## {name} ({len(items)})"]
        for page, res in items:
            new = res["record"] or {}
            lines += ["", f"### {new.get('title') or page['old'].get('title') or page['old'].get('title_guess')}",
                      f"- page: {page['url']}"]
            lines += [f"- PDF: {u}" for u in new.get("document_urls", [])]
            if page["status"] == "rejected":
                lines.append(f"- old: rejected — {page['old']['reason']}")
            else:
                lines.append(f"- old deadline: {page['old'].get('deadline')!r}; requirements "
                             f"({len(page['old']['requirements_text'])} chars): "
                             f"{page['old']['requirements_text'][:300]!r}")
            if res["record"]:
                lines.append(f"- new deadline: {new.get('deadline')!r}; requirements "
                             f"({len(new['requirements_text'])} chars): {new['requirements_text'][:300]!r}")
            else:
                lines.append(f"- new: rejected — {res['reason']}")

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines[:14]))
    print(f"\nFull report -> {REPORT_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stage", choices=["scan", "extract", "report"])
    {"scan": scan, "extract": extract, "report": report}[parser.parse_args().stage]()
