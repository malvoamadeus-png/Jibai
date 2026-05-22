from __future__ import annotations

import os
import re
import sys
import time
import urllib.parse
from datetime import datetime
from dataclasses import dataclass

import requests

from packages.common.time_utils import SHANGHAI_TZ


DEFAULT_BACKEND = "browser"
DEFAULT_TIMEOUT_SECONDS = 180
_SEARCH_ENGINES = ("yahoo", "duckduckgo_html", "duckduckgo", "bing")
_STATUS_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.|mobile\.)?(?:x\.com|twitter\.com)/(?P<username>[A-Za-z0-9_]{1,15})/status/(?P<tweet_id>\d+)",
    re.IGNORECASE,
)
_DDG_RESULTS_JS = """() => {
  const anchors = Array.from(document.querySelectorAll("a[href]"));
  return anchors.slice(0, 250).map((anchor) => {
    const href = anchor.href || anchor.getAttribute("href") || "";
    const title = (anchor.textContent || "").replace(/\\s+/g, " ").trim();
    const container = anchor.closest("article, .result, .web-result, .links_main, .result__body, .nrn-react-div");
    const snippet = container
      ? (container.textContent || "").replace(/\\s+/g, " ").trim()
      : "";
    return { href, title, snippet };
  });
}"""
_FXTWITTER_API_ROOT = "https://api.fxtwitter.com"
_FXTWITTER_HEADERS = {"User-Agent": "jibai-public-x-search/1.0"}


@dataclass(frozen=True, slots=True)
class XSearchTweet:
    url: str
    author: str
    author_name: str
    text: str
    created_at: str
    tweet_id: str
    likes: int
    retweets: int
    replies: int
    views: int
    title: str
    snippet: str
    query_variant: str


@dataclass(frozen=True, slots=True)
class XSearchResult:
    query: str
    backend: str
    search_queries: list[str]
    tweets: list[XSearchTweet]
    warning: str | None = None


@dataclass(frozen=True, slots=True)
class NormalizedTweetUrl:
    username: str
    tweet_id: str
    canonical_url: str


@dataclass(frozen=True, slots=True)
class SearchUrlCandidate:
    url: str
    title: str
    snippet: str
    query_variant: str


def _timeout_seconds() -> int:
    try:
        return max(30, int(os.getenv("PUBLIC_X_SEARCH_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))))
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS


def _resolve_backend_name(backend: str | None = None) -> tuple[str, str | None]:
    raw_value = str(backend or os.getenv("PUBLIC_X_SEARCH_BACKEND", DEFAULT_BACKEND)).strip().lower()
    if raw_value and raw_value != DEFAULT_BACKEND:
        warning = f"PUBLIC_X_SEARCH_BACKEND={raw_value} is no longer supported; falling back to browser"
        print(f"[public-x-search] {warning}", file=sys.stderr)
        return DEFAULT_BACKEND, warning
    return DEFAULT_BACKEND, None


def _as_int(value: object) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _coerce_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return str(value.get("text") or "").strip()
    return ""


def _fetch_tweet_detail(username: str, tweet_id: str) -> dict[str, object]:
    response = requests.get(
        f"{_FXTWITTER_API_ROOT}/{username}/status/{tweet_id}",
        headers=_FXTWITTER_HEADERS,
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        return {}
    tweet = payload.get("tweet")
    return tweet if isinstance(tweet, dict) else {}


def _parse_created_at(value: str | None) -> str:
    if not value:
        return ""
    raw = value.strip()
    if not raw:
        return ""
    try:
        dt = datetime.strptime(raw, "%a %b %d %H:%M:%S %z %Y")
    except ValueError:
        return raw
    return dt.astimezone(SHANGHAI_TZ).isoformat(timespec="seconds")


def _normalize_status_url(value: str) -> NormalizedTweetUrl | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    parsed = urllib.parse.urlparse(raw)
    candidate = raw
    if "duckduckgo.com" in parsed.netloc:
        qs = urllib.parse.parse_qs(parsed.query)
        unwrapped = (
            qs.get("uddg", [None])[0]
            or qs.get("u", [None])[0]
            or qs.get("url", [None])[0]
        )
        if not unwrapped:
            return None
        candidate = urllib.parse.unquote(unwrapped)
    match = _STATUS_URL_RE.search(candidate)
    if match is None:
        return None
    username = match.group("username")
    tweet_id = match.group("tweet_id")
    lowered_candidate = candidate.lower()
    if username.lower() == "status" and (
        "://x.com/status/status/" in lowered_candidate or "://twitter.com/status/status/" in lowered_candidate
    ):
        return None
    return NormalizedTweetUrl(
        username=username,
        tweet_id=tweet_id,
        canonical_url=f"https://x.com/{username}/status/{tweet_id}",
    )


def _build_search_queries(query: str) -> list[str]:
    cleaned = " ".join(str(query or "").split())
    if not cleaned:
        return []
    variants: list[str] = []
    account_match = re.fullmatch(r"@?([A-Za-z0-9_]{1,15})", cleaned)
    if account_match is not None:
        username = account_match.group(1)
        variants.append(f"site:x.com/{username}/status {cleaned}")
        variants.append(f"site:twitter.com/{username}/status {cleaned}")
        variants.append(f"x.com/{username}/status {cleaned}")
        variants.append(f"twitter.com/{username}/status {cleaned}")
    variants.append(f"site:x.com/status {cleaned}")
    variants.append(f"site:twitter.com/status {cleaned}")
    variants.append(f"x.com/status {cleaned}")
    variants.append(f"twitter.com/status {cleaned}")
    seen: set[str] = set()
    output: list[str] = []
    for item in variants:
        normalized = " ".join(item.split())
        if normalized and normalized not in seen:
            output.append(normalized)
            seen.add(normalized)
    return output


def _remaining_timeout_ms(deadline: float) -> int:
    return max(1_000, int((deadline - time.monotonic()) * 1000))


def _search_engine_urls(search_query: str) -> list[tuple[str, str]]:
    return [
        ("yahoo", "https://search.yahoo.com/search?" + urllib.parse.urlencode({"p": search_query})),
        ("duckduckgo_html", "https://duckduckgo.com/html/?" + urllib.parse.urlencode({"q": search_query, "kl": "us-en"})),
        ("duckduckgo", "https://duckduckgo.com/?" + urllib.parse.urlencode({"q": search_query, "kl": "us-en"})),
        ("bing", "https://www.bing.com/search?" + urllib.parse.urlencode({"q": search_query})),
    ]


def _search_page_failure_reason(engine_name: str, page_url: str, page_title: str, body_text: str) -> str | None:
    url_lower = str(page_url or "").lower()
    title_lower = str(page_title or "").lower()
    body_lower = str(body_text or "").lower()

    if engine_name.startswith("duckduckgo"):
        if "duckduckgo.com/static-pages/418.html" in url_lower or "unexpected error" in body_lower:
            return "DuckDuckGo returned an error page"
    if engine_name == "bing" and ("solve the challenge below" in body_lower or "one last step" in body_lower):
        return "Bing presented a bot challenge"
    if "unusual traffic" in body_lower or "confirm you’re not a robot" in body_lower or "confirm you're not a robot" in body_lower:
        return f"{engine_name} presented a bot challenge"
    if "just a moment" in title_lower or "just a moment" in body_lower:
        return f"{engine_name} returned an interstitial page"
    return None


def _browser_search_candidates(
    search_query: str,
    *,
    limit: int,
    deadline: float,
) -> list[SearchUrlCandidate]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise RuntimeError(f"x search runtime unavailable: playwright import failed: {exc}") from exc

    browser = None
    context = None
    playwright = None
    try:
        playwright = sync_playwright().start()
        try:
            browser = playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
        except Exception as exc:
            raise RuntimeError(
                "x search runtime unavailable: Playwright Chromium is not installed or failed to launch: "
                f"{exc}"
            ) from exc
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            viewport={"width": 1440, "height": 960},
        )
        page = context.new_page()
        try:
            page.route(
                "**/*",
                lambda route: route.abort()
                if route.request.resource_type in {"image", "media", "font"}
                else route.continue_(),
            )
        except Exception:
            pass

        engine_failures: list[str] = []
        for engine_name, search_url in _search_engine_urls(search_query):
            if time.monotonic() >= deadline:
                break
            try:
                page.goto(
                    search_url,
                    wait_until="domcontentloaded",
                    timeout=min(_remaining_timeout_ms(deadline), 20_000),
                )
            except Exception as exc:
                engine_failures.append(f"{engine_name}: failed to open search page: {exc}")
                continue

            page.wait_for_timeout(2_500)
            page_title = ""
            body_text = ""
            try:
                page_title = page.title()
            except Exception:
                page_title = ""
            try:
                body_text = page.locator("body").inner_text()
            except Exception:
                body_text = ""
            failure_reason = _search_page_failure_reason(engine_name, page.url, page_title, body_text)
            if failure_reason:
                engine_failures.append(f"{engine_name}: {failure_reason}")
                continue

            try:
                raw_items = page.evaluate(_DDG_RESULTS_JS) or []
            except Exception as exc:
                engine_failures.append(f"{engine_name}: failed to parse search results: {exc}")
                continue

            candidates: list[SearchUrlCandidate] = []
            seen_urls: set[str] = set()
            for raw in raw_items:
                if not isinstance(raw, dict):
                    continue
                normalized = _normalize_status_url(str(raw.get("href") or ""))
                if normalized is None or normalized.canonical_url in seen_urls:
                    continue
                seen_urls.add(normalized.canonical_url)
                candidates.append(
                    SearchUrlCandidate(
                        url=normalized.canonical_url,
                        title=str(raw.get("title") or "").strip(),
                        snippet=str(raw.get("snippet") or "").strip(),
                        query_variant=search_query,
                    )
                )
                if len(candidates) >= limit:
                    break
            if candidates:
                return candidates
            engine_failures.append(f"{engine_name}: returned 0 tweet status urls")

        failure_hint = "; ".join(engine_failures[:4]) or "all search engines returned 0 tweet status urls"
        raise RuntimeError(f"x search engines failed for query={search_query}: {failure_hint}")
    finally:
        try:
            if context is not None:
                context.close()
        except Exception:
            pass
        try:
            if browser is not None:
                browser.close()
        except Exception:
            pass
        try:
            if playwright is not None:
                playwright.stop()
        except Exception:
            pass


def _tweet_from_fxtwitter(candidate: SearchUrlCandidate) -> XSearchTweet:
    normalized = _normalize_status_url(candidate.url)
    if normalized is None:
        raise RuntimeError(f"x search returned an invalid status url: {candidate.url}")
    payload = _fetch_tweet_detail(normalized.username, normalized.tweet_id)
    if not payload:
        raise RuntimeError(f"FxTwitter returned an empty payload for {normalized.canonical_url}")

    author_payload = payload.get("author") if isinstance(payload.get("author"), dict) else {}
    screen_name = str(author_payload.get("screen_name") or normalized.username).strip().lstrip("@")
    author = f"@{screen_name}" if screen_name else f"@{normalized.username}"
    author_name = str(author_payload.get("name") or screen_name or normalized.username).strip()
    raw_created_at = str(payload.get("created_at") or "").strip()
    created_at = _parse_created_at(raw_created_at)
    text = _coerce_text(payload.get("text") or payload.get("raw_text"))
    return XSearchTweet(
        url=normalized.canonical_url,
        author=author,
        author_name=author_name,
        text=text,
        created_at=created_at,
        tweet_id=str(payload.get("id") or normalized.tweet_id),
        likes=_as_int(payload.get("likes")),
        retweets=_as_int(payload.get("reposts") or payload.get("retweets")),
        replies=_as_int(payload.get("replies")),
        views=_as_int(payload.get("views")),
        title=candidate.title,
        snippet=candidate.snippet,
        query_variant=candidate.query_variant,
    )


def search_x_posts(query: str, *, limit: int = 20, backend: str | None = None) -> XSearchResult:
    cleaned_query = " ".join(str(query or "").split())
    if not cleaned_query:
        raise RuntimeError("x search query is empty")

    safe_backend, backend_warning = _resolve_backend_name(backend)
    safe_limit = max(1, min(int(limit), 50))
    search_queries = _build_search_queries(cleaned_query)
    if not search_queries:
        raise RuntimeError("x search query did not produce any browser search variants")

    deadline = time.monotonic() + _timeout_seconds()
    url_candidates: list[SearchUrlCandidate] = []
    seen_urls: set[str] = set()
    query_failures: list[str] = []
    for search_query in search_queries:
        if time.monotonic() >= deadline:
            raise RuntimeError("x search timed out before the browser search completed")
        try:
            candidates = _browser_search_candidates(
                search_query,
                limit=max(safe_limit * 3, 12),
                deadline=deadline,
            )
        except Exception as exc:
            query_failures.append(f"{search_query}: {exc}")
            continue
        for candidate in candidates:
            if candidate.url in seen_urls:
                continue
            seen_urls.add(candidate.url)
            url_candidates.append(candidate)
            if len(url_candidates) >= safe_limit * 3:
                break
        if len(url_candidates) >= safe_limit * 3:
            break

    if not url_candidates:
        failure_hint = f" failures={'; '.join(query_failures[:2])}" if query_failures else ""
        raise RuntimeError(f"x search returned 0 tweet status urls for query={cleaned_query}.{failure_hint}".rstrip("."))

    tweets: list[XSearchTweet] = []
    detail_failures: list[str] = []
    for candidate in url_candidates:
        if time.monotonic() >= deadline:
            detail_failures.append("detail fetch timed out")
            break
        try:
            tweets.append(_tweet_from_fxtwitter(candidate))
        except Exception as exc:
            detail_failures.append(f"{candidate.url}: {exc}")
            continue
        if len(tweets) >= safe_limit:
            break

    if not tweets:
        detail_hint = "; ".join(detail_failures[:2]) or "unknown detail error"
        raise RuntimeError(f"x search found tweet urls but failed to fetch tweet details: {detail_hint}")

    warning_parts: list[str] = []
    if backend_warning:
        warning_parts.append(backend_warning)
    if query_failures:
        warning_parts.append(f"search query failures={len(query_failures)}")
    if detail_failures:
        warning_parts.append(f"tweet detail failures={len(detail_failures)}")

    return XSearchResult(
        query=cleaned_query,
        backend=safe_backend,
        search_queries=search_queries,
        tweets=tweets,
        warning="; ".join(warning_parts) or None,
    )
