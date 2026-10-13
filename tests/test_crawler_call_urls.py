# sources.yaml `call_urls`: known call pages are discovered directly, with no fetch or LLM call
from datetime import datetime, timezone

from src.collectors.crawler import crawl_source, known_call_urls
from src.collectors.ids import make_id

SOURCE = {
    "name": "example_org",
    "listing_url": None,
    "call_urls": [
        {"url": "https://example.org/open-call-2027", "title": "Open Call 2027"},
        {"url": "https://example.org/residency-2027"},
    ],
}


def test_call_urls_become_discovered():
    found = known_call_urls(SOURCE, set(), datetime.now(timezone.utc))
    assert [d.url for d in found] == [c["url"] for c in SOURCE["call_urls"]]
    assert found[0].title_guess == "Open Call 2027"
    assert found[1].title_guess == ""
    assert found[0].id == make_id("https://example.org/open-call-2027", "example_org")


def test_already_seen_call_urls_are_skipped():
    seen = {make_id("https://example.org/open-call-2027", "example_org")}
    found = known_call_urls(SOURCE, seen, datetime.now(timezone.utc))
    assert [d.url for d in found] == ["https://example.org/residency-2027"]


def test_source_without_listing_page_needs_no_client():
    # client=None: proves nothing is fetched or classified when there is no listing page
    found = crawl_source(None, SOURCE, set(), {})
    assert len(found) == 2


def test_failing_listing_page_keeps_call_urls(monkeypatch):
    import requests

    def refuse(*args, **kwargs):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(requests, "get", refuse)
    source = {**SOURCE, "listing_url": "https://example.org/open-calls"}
    assert len(crawl_source(None, source, set(), {})) == 2
