"""
OpenArt — listing-page crawler.

Given a known source's listing page (data/sources.yaml), harvests links
to individual opportunities. Cheap deterministic steps do most of the
work (fetch, parse <a> tags, dedup against already-seen ids); a single
LLM call per page handles the one genuinely ambiguous judgment call:
which links are actual opportunities (vs. nav/social/legal) and whether
there's a next-page link to follow. See workflow.MD for the full design
rationale, including why sources.yaml is human-curated, not discovered.

Two cost guards keep that LLM call from being paid for repeatedly on
content it's already seen (this matters more as source count and crawl
frequency grow - see workflow.MD's "Known open items"): candidates
already in `seen_ids` are filtered out *before* classify_links() is
called, not after, so the model never re-classifies a link it's already
placed; and a hash of each page's harvested candidate set is cached
(`data/discovered/_page_hashes.json`) so a page that's byte-identical to
its last crawl - the common case for a source re-crawled often - skips
the fetch's classify_links() call entirely rather than re-asking the
same question. The hash is over the *candidate links*, not raw HTML, so
incidental page noise (CSRF tokens, "generated at" timestamps) that
changes on every request without changing the actual link set doesn't
defeat it.

Requires OPENAI_API_KEY (read from a .env file at the repo root, or the
environment) to run the classification step - fetching and
link-harvesting work without it, but classify_links() will raise
openai.AuthenticationError if no credentials are configured.

Usage: uv run python -m src.collectors.crawler
"""

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
import yaml
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(REPO_ROOT)
load_dotenv(os.path.join(REPO_ROOT, ".env"))

from src.collectors.ids import make_id  # noqa: E402
from src.collectors.jsonl import load_jsonl, load_seen_ids, write_jsonl  # noqa: E402
from src.models.discovered_url import DiscoveredUrl  # noqa: E402

SOURCES_YAML = os.path.join(REPO_ROOT, "data", "sources.yaml")
RAW_DIR = os.path.join(REPO_ROOT, "data", "raw")
DISCOVERED_DIR = os.path.join(REPO_ROOT, "data", "discovered")
PAGE_HASHES_PATH = os.path.join(DISCOVERED_DIR, "_page_hashes.json")

HEADERS = {
    "User-Agent": "OpenArt-capstone-research-bot/0.1 (student project; contact: lucatomarelli1@gmail.com)"
}

DENYLIST_SCHEMES = {"mailto", "tel", "javascript"}
DENYLIST_DOMAINS = {
    "twitter.com", "x.com", "linkedin.com", "facebook.com",
    "instagram.com", "youtube.com",
}

MODEL = "gpt-5.4-mini"  # "mini" tier: this is a schema-constrained classification
# task, not deep reasoning - picked for cost, not the flagship model.
# Verify actual billing after first real use; no live OpenAI pricing
# reference was available to confirm cost against, unlike the Claude path.
MAX_PAGES_PER_SOURCE = 10


class LinkClassification(BaseModel):
    opportunity_indices: list[int]
    next_page_index: int | None


def normalize_link(href: str, base_url: str) -> str | None:
    href = href.strip()
    if not href or href.startswith("#"):
        return None

    absolute = urljoin(base_url, href)
    parts = urlsplit(absolute)
    if parts.scheme in DENYLIST_SCHEMES:
        return None
    if any(parts.netloc.endswith(domain) for domain in DENYLIST_DOMAINS):
        return None

    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))  # drop fragment


def load_page_hashes(path: str = PAGE_HASHES_PATH) -> dict[str, str]:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_page_hashes(hashes: dict[str, str], path: str = PAGE_HASHES_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(hashes, f, indent=2, sort_keys=True)


def candidates_hash(candidates: list[tuple[str, str]]) -> str:
    """Hash the (url, anchor_text) set, not raw HTML - see module docstring."""
    canonical = "\n".join(f"{url}|{text}" for url, text in sorted(candidates))
    return hashlib.sha256(canonical.encode()).hexdigest()


def gather_candidate_links(html: str, base_url: str) -> list[tuple[str, str]]:
    """Harvest (url, anchor_text) pairs, scoped to <main> when present.

    Scoping to <main> is a cheap, generic noise filter - most modern
    sites keep header/nav/footer chrome outside it - not a site-specific
    selector. Falls back to the whole document when <main> is absent.
    """
    soup = BeautifulSoup(html, "html.parser")
    scope = soup.find("main") or soup

    seen: set[str] = set()
    candidates: list[tuple[str, str]] = []
    for a in scope.find_all("a", href=True):
        url = normalize_link(a["href"], base_url)
        if url is None or url in seen:
            continue
        text = a.get_text(strip=True)
        if not text:
            continue
        seen.add(url)
        candidates.append((url, text))
    return candidates


def classify_links(
    client: OpenAI, candidates: list[tuple[str, str]], listing_url: str
) -> LinkClassification:
    numbered = "\n".join(f"{i}: [{text}]({url})" for i, (url, text) in enumerate(candidates))

    response = client.chat.completions.parse(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are filtering links harvested from an arts/culture open-call "
                    "listing page. Given a numbered list of (anchor text, URL) pairs, "
                    "return the indices of links that point to ONE SPECIFIC open call, "
                    "grant, residency, or commission opportunity - a page about a single "
                    "named opportunity that artists could apply to.\n\n"
                    "Exclude:\n"
                    "- Links to a search/browse/catalogue page, even if labeled 'see all "
                    "open calls' or similar - that is navigation to many opportunities, "
                    "not one specific opportunity itself.\n"
                    "- General informational or procedural pages: how organizations "
                    "submit a call for listing, generic application forms/portals not "
                    "tied to one named opportunity, reference documents, legal texts, "
                    "FAQs, guides.\n"
                    "- Navigation, legal pages, social media, newsletters, or unrelated "
                    "thematic/informational pages.\n"
                    "- News or announcement articles that read as ALREADY resolved - an "
                    "artist already chosen, a work already unveiled/inaugurated - rather "
                    "than soliciting new applicants. Titles mentioning a specific place "
                    "plus 'a work for/at <location>' without 'call', 'apply', or similar "
                    "solicitation language are often this; when genuinely unsure from the "
                    "title alone, include it - the next stage reads the full page and can "
                    "reject it there with much more certainty than you can from a title.\n\n"
                    "Separately, if one of the numbered links is a 'next page' / "
                    "pagination link (e.g. 'suivant', 'next', a page number), return its "
                    "index; otherwise null."
                ),
            },
            {"role": "user", "content": f"Listing page: {listing_url}\n\nLinks:\n{numbered}"},
        ],
        response_format=LinkClassification,
    )
    return response.choices[0].message.parsed


def crawl_source(
    client: OpenAI,
    source: dict,
    seen_ids: set[str],
    page_hashes: dict[str, str],
    max_pages: int = MAX_PAGES_PER_SOURCE,
) -> list[DiscoveredUrl]:
    discovered: list[DiscoveredUrl] = []
    url = source["listing_url"]
    discovered_at = datetime.now(timezone.utc)

    for page_num in range(max_pages):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as e:
            if page_num == 0:
                raise  # first page failing means this source itself is broken - surface it
            print(f"  {source['name']}: pagination fetch failed ({e}), stopping at page {page_num}")
            break
        candidates = gather_candidate_links(resp.text, url)
        if not candidates:
            break

        content_hash = candidates_hash(candidates)
        if page_hashes.get(url) == content_hash:
            # Unchanged since the last crawl - the candidate set (including
            # any pagination link) is identical, so there's nothing new to
            # classify and nothing deeper to discover either.
            break
        page_hashes[url] = content_hash

        unseen_candidates = [
            (link_url, text)
            for link_url, text in candidates
            if make_id(link_url, source["name"]) not in seen_ids
        ]
        if not unseen_candidates:
            break  # every candidate here (incl. any pagination link) is already known

        analysis = classify_links(client, unseen_candidates, url)

        for i in analysis.opportunity_indices:
            if not (0 <= i < len(unseen_candidates)):
                continue
            link_url, text = unseen_candidates[i]
            link_id = make_id(link_url, source["name"])
            seen_ids.add(link_id)
            discovered.append(
                DiscoveredUrl(
                    id=link_id,
                    url=link_url,
                    source=source["name"],
                    title_guess=text,
                    discovered_at=discovered_at,
                )
            )

        next_url = None
        if analysis.next_page_index is not None and 0 <= analysis.next_page_index < len(unseen_candidates):
            next_url = unseen_candidates[analysis.next_page_index][0]
        if not next_url or next_url == url:
            break
        url = next_url

    return discovered


def crawl_all(
    sources_path: str = SOURCES_YAML,
    raw_dir: str = RAW_DIR,
    out_dir: str = DISCOVERED_DIR,
    only: set[str] | None = None,
) -> dict[str, int]:
    """Crawl every source in sources.yaml, or just the ones named in `only`.

    `only` exists so a single source can be tested/re-run without paying
    for (or waiting on) a full pass over every source - handy while
    validating a new source or a prompt change.
    """
    with open(sources_path, encoding="utf-8") as f:
        sources = yaml.safe_load(f) or []
    if only is not None:
        sources = [s for s in sources if s["name"] in only]

    client = OpenAI()
    seen_ids = load_seen_ids(raw_dir, out_dir)
    page_hashes = load_page_hashes()

    counts = {}
    for source in sources:
        try:
            newly_discovered = crawl_source(client, source, seen_ids, page_hashes)
        except Exception as e:
            print(f"{source['name']}: FAILED - {e}")
            counts[source["name"]] = None
            continue
        finally:
            # Saved every source, not just at the very end, so a later
            # source's failure can't discard hash updates already earned
            # (and paid for) by sources processed before it.
            save_page_hashes(page_hashes)

        out_path = os.path.join(out_dir, f"{source['name']}.jsonl")
        merged = {d.id: d for d in load_jsonl(out_path, DiscoveredUrl)}
        merged.update({d.id: d for d in newly_discovered})
        write_jsonl(list(merged.values()), out_path)

        counts[source["name"]] = len(newly_discovered)
        print(f"{source['name']}: {len(newly_discovered)} new opportunity link(s) -> {out_path}")

    return counts


if __name__ == "__main__":
    crawl_all()
