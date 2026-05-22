from __future__ import annotations

import inspect

import pytest

from packages.public_app import x_search
from packages.public_app.x_search import (
    SearchUrlCandidate,
    XSearchTweet,
    _build_search_queries,
    _normalize_status_url,
    _search_page_failure_reason,
    search_x_posts,
)


def _tweet(url: str, *, query_variant: str = "site:x.com/status orbiter") -> XSearchTweet:
    return XSearchTweet(
        url=url,
        author="@orbiter_finance",
        author_name="Orbiter Finance",
        text="Orbiter bridge update",
        created_at="2026-05-21T10:00:00+08:00",
        tweet_id=url.rsplit("/", 1)[-1],
        likes=10,
        retweets=2,
        replies=1,
        views=100,
        title="Orbiter bridge update",
        snippet="Orbiter bridge update",
        query_variant=query_variant,
    )


def test_x_search_module_no_longer_depends_on_reference_path() -> None:
    source = inspect.getsource(x_search)
    assert "Reference/x-tweet-fetcher" not in source
    assert "fetch_tweet.py" not in source


def test_x_search_backend_falls_back_to_browser_with_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "packages.public_app.x_search._browser_search_candidates",
        lambda *_args, **_kwargs: [
            SearchUrlCandidate(
                url="https://x.com/orbiter_finance/status/123",
                title="Orbiter bridge update",
                snippet="Orbiter bridge update",
                query_variant="site:x.com/status orbiter",
            )
        ],
    )
    monkeypatch.setattr(
        "packages.public_app.x_search._tweet_from_fxtwitter",
        lambda candidate: _tweet(candidate.url, query_variant=candidate.query_variant),
    )

    result = search_x_posts("orbiter", backend="nitter")

    assert result.backend == "browser"
    assert result.warning is not None
    assert "falling back to browser" in result.warning
    assert result.tweets[0].url == "https://x.com/orbiter_finance/status/123"


def test_x_search_reports_runtime_error_explicitly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "packages.public_app.x_search._browser_search_candidates",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("x search runtime unavailable: Playwright Chromium is not installed")
        ),
    )

    with pytest.raises(RuntimeError, match="Playwright Chromium is not installed"):
        search_x_posts("aeon")


def test_build_search_queries_adds_non_site_account_variants() -> None:
    queries = _build_search_queries("@aeonframework")

    assert "site:x.com/aeonframework/status @aeonframework" in queries
    assert "x.com/aeonframework/status @aeonframework" in queries
    assert "site:x.com/status @aeonframework" in queries


def test_normalize_status_url_rejects_status_status_search_artifacts() -> None:
    assert _normalize_status_url("https://x.com/status/status/1956485724385018048") is None


def test_search_page_failure_reason_detects_known_search_blocks() -> None:
    assert (
        _search_page_failure_reason(
            "duckduckgo",
            "https://duckduckgo.com/static-pages/418.html?bno=84f2",
            "DuckDuckGo - Protection. Privacy. Peace of mind.",
            "Unexpected error. Please try again.",
        )
        == "DuckDuckGo returned an error page"
    )
    assert (
        _search_page_failure_reason(
            "bing",
            "https://www.bing.com/search?q=site%3Ax.com%2Fstatus+Aeon",
            "site:x.com/status Aeon - Search",
            "One last step Please solve the challenge below to continue",
        )
        == "Bing presented a bot challenge"
    )
