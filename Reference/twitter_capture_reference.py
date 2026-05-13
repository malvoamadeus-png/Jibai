from __future__ import annotations

import argparse
import re
import sys
import time
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

import requests


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,15}$")
RESERVED_PATHS = {
    "home",
    "explore",
    "i",
    "search",
    "messages",
    "notifications",
    "settings",
    "tos",
    "privacy",
    "compose",
}

DEFAULT_NITTER_INSTANCES = (
    "nitter.tiekoetter.com",
    "nitter.catsarch.com",
    "xcancel.com",
)

BOT_PROTECTION_MARKERS = (
    ("verifying your request", "request verification required"),
    ("performing security verification", "security verification required"),
    ("verify you are human", "human verification required"),
    ("captcha", "captcha required"),
    ("cloudflare", "blocked by Cloudflare"),
    ("ddos-guard", "blocked by DDoS-Guard"),
    ("access denied", "access denied"),
    ("too many requests", "rate limited"),
    ("rate limit", "rate limited"),
)

TimelineStatus = Literal[
    "success",
    "runtime_failed",
    "fetch_failed",
    "parse_failed",
    "parse_empty",
]


@dataclass(slots=True)
class TweetCandidate:
    tweet_id: str
    author_username: str
    author_display_name: str
    text: str
    created_at_raw: str | None = None
    reply_count: int = 0
    retweet_count: int = 0
    like_count: int = 0
    view_count: int = 0
    media_urls: list[str] = field(default_factory=list)
    is_pinned: bool = False
    source: str = "unknown"


@dataclass(slots=True)
class TimelineAttempt:
    source: str
    page: int
    status: TimelineStatus
    url: str
    error: str | None = None


@dataclass(slots=True)
class CaptureRecord:
    platform: str
    tweet_id: str
    author_username: str
    author_display_name: str
    url: str
    text: str
    created_at: str | None
    reply_count: int
    retweet_count: int
    like_count: int
    bookmark_count: int
    view_count: int
    media_urls: list[str]
    metadata: dict[str, Any]


def normalize_username(value: str) -> str:
    raw = value.strip()
    if not raw:
        raise ValueError("username is empty")
    if raw.startswith("@"):
        raw = raw[1:]
    if "://" not in raw and "/" not in raw:
        username = raw
    else:
        if "://" not in raw:
            raw = "https://" + raw.lstrip("/")
        parsed = urllib.parse.urlparse(raw)
        host = parsed.netloc.lower()
        if host not in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
            raise ValueError("profile URL must point to x.com or twitter.com")
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) != 1:
            raise ValueError("profile URL must be a direct user profile URL")
        username = parts[0].lstrip("@")
    if username.lower() in RESERVED_PATHS or not USERNAME_PATTERN.fullmatch(username):
        raise ValueError(f"invalid Twitter/X username: {username!r}")
    return username


def _request_json(url: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
    response = requests.get(
        url,
        params=params,
        headers={"User-Agent": "public-x-capture-reference/1.0"},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return str(value.get("text") or "").strip()
    return ""


def _media_urls(payload: dict[str, Any]) -> list[str]:
    media = payload.get("media")
    items: list[Any] = []
    if isinstance(media, dict) and isinstance(media.get("all"), list):
        items = media["all"]
    elif isinstance(media, list):
        items = media

    urls: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or item.get("thumbnail_url") or "").strip()
        if url and url not in urls:
            urls.append(url)
    return urls


def parse_twitter_created_at(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip()
    try:
        return datetime.strptime(raw, "%a %b %d %H:%M:%S %z %Y").isoformat()
    except ValueError:
        return None


def fxtwitter_statuses(
    username: str,
    *,
    count: int = 20,
    cursor: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    params: dict[str, Any] = {"count": max(1, min(count, 100))}
    if cursor:
        params["cursor"] = cursor
    url = f"https://api.fxtwitter.com/2/profile/{username}/statuses"
    response = requests.get(
        url,
        params=params,
        headers={"User-Agent": "public-x-capture-reference/1.0"},
        timeout=20,
    )
    if response.status_code == 204:
        return [], None
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        return [], None
    results = payload.get("results")
    cursor_payload = payload.get("cursor")
    return (
        [item for item in results if isinstance(item, dict)] if isinstance(results, list) else [],
        cursor_payload if isinstance(cursor_payload, dict) else None,
    )


def candidate_from_fxtwitter(payload: dict[str, Any]) -> TweetCandidate | None:
    tweet_id = str(payload.get("id") or "").strip()
    author = payload.get("author") if isinstance(payload.get("author"), dict) else {}
    username = str(author.get("screen_name") or "").strip().lstrip("@")
    if not tweet_id or not username:
        return None
    return TweetCandidate(
        tweet_id=tweet_id,
        author_username=username,
        author_display_name=str(author.get("name") or username).strip(),
        text=_text(payload.get("text") or payload.get("raw_text")),
        created_at_raw=str(payload.get("created_at") or "").strip() or None,
        reply_count=_int(payload.get("replies")),
        retweet_count=_int(payload.get("reposts") or payload.get("retweets")),
        like_count=_int(payload.get("likes")),
        view_count=_int(payload.get("views")),
        media_urls=_media_urls(payload),
        source="fxtwitter",
    )


def collect_from_fxtwitter(
    username: str,
    *,
    limit: int,
    max_pages: int,
) -> tuple[list[TweetCandidate], list[TimelineAttempt]]:
    target = username.lower()
    cursor: str | None = None
    seen: set[str] = set()
    candidates: list[TweetCandidate] = []
    attempts: list[TimelineAttempt] = []

    for page in range(1, max_pages + 1):
        url = f"https://api.fxtwitter.com/2/profile/{username}/statuses"
        try:
            statuses, cursor_payload = fxtwitter_statuses(
                username,
                count=max(20, min(100, limit - len(candidates))),
                cursor=cursor,
            )
        except Exception as exc:
            attempts.append(TimelineAttempt("fxtwitter", page, "fetch_failed", url, str(exc)))
            break
        if not statuses:
            attempts.append(TimelineAttempt("fxtwitter", page, "parse_empty", url, "empty response"))
            break
        attempts.append(TimelineAttempt("fxtwitter", page, "success", url))
        for status in statuses:
            candidate = candidate_from_fxtwitter(status)
            if not candidate:
                continue
            if candidate.author_username.lower() != target:
                continue
            if candidate.tweet_id in seen:
                continue
            seen.add(candidate.tweet_id)
            candidates.append(candidate)
            if len(candidates) >= limit:
                return candidates, attempts
        cursor = str(cursor_payload.get("bottom")) if cursor_payload and cursor_payload.get("bottom") else None
        if not cursor:
            break
        time.sleep(0.2)
    return candidates, attempts


def fetch_tweet_detail(username: str, tweet_id: str) -> dict[str, Any]:
    payload = _request_json(f"https://api.fxtwitter.com/{username}/status/{tweet_id}")
    tweet = payload.get("tweet")
    return tweet if isinstance(tweet, dict) else {}


def detail_to_record(username: str, candidate: TweetCandidate) -> CaptureRecord:
    try:
        detail = fetch_tweet_detail(username, candidate.tweet_id)
    except Exception:
        detail = {}
    author = detail.get("author") if isinstance(detail.get("author"), dict) else {}
    text = _text(detail.get("text") or detail.get("raw_text")) or candidate.text
    created_at = parse_twitter_created_at(str(detail.get("created_at") or candidate.created_at_raw or ""))
    media_urls = _media_urls(detail) or list(candidate.media_urls)
    return CaptureRecord(
        platform="x",
        tweet_id=candidate.tweet_id,
        author_username=str(author.get("screen_name") or candidate.author_username).lstrip("@"),
        author_display_name=str(author.get("name") or candidate.author_display_name),
        url=str(detail.get("url") or f"https://x.com/{username}/status/{candidate.tweet_id}"),
        text=text,
        created_at=created_at,
        reply_count=_int(detail.get("replies") or candidate.reply_count),
        retweet_count=_int(detail.get("retweets") or candidate.retweet_count),
        like_count=_int(detail.get("likes") or candidate.like_count),
        bookmark_count=_int(detail.get("bookmarks")),
        view_count=_int(detail.get("views") or candidate.view_count),
        media_urls=media_urls,
        metadata={"source": candidate.source, "is_pinned": candidate.is_pinned},
    )


def nitter_timeline_page(
    username: str,
    *,
    instance: str,
    cursor: str | None = None,
    wait_seconds: float = 5.0,
    headless: bool = True,
) -> tuple[list[TweetCandidate], str | None, TimelineAttempt]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        url = _nitter_url(instance, username, cursor)
        return [], None, TimelineAttempt(instance, 1, "runtime_failed", url, str(exc))

    url = _nitter_url(instance, username, cursor)
    with sync_playwright() as playwright:
        browser = None
        context = None
        try:
            browser = playwright.chromium.launch(
                headless=headless,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                viewport={"width": 1280, "height": 900},
            )
            page = context.new_page()
            page.route(
                "**/*",
                lambda route: route.abort()
                if route.request.resource_type in {"font", "image", "media"}
                else route.continue_(),
            )
            navigation_error = None
            try:
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
            except Exception as exc:
                navigation_error = str(exc)
            time.sleep(wait_seconds)
            blocked = _blocked_reason(page.content())
            if blocked:
                return [], None, TimelineAttempt(instance, 1, "fetch_failed", url, blocked)
            try:
                raw_items = page.evaluate(NITTER_TIMELINE_JS) or []
                next_cursor = page.evaluate(NITTER_CURSOR_JS)
            except Exception as exc:
                return [], None, TimelineAttempt(instance, 1, "parse_failed", url, str(exc))
            candidates = [item for item in (_candidate_from_nitter(item) for item in raw_items) if item]
            if candidates:
                return candidates, next_cursor, TimelineAttempt(instance, 1, "success", url)
            return [], next_cursor, TimelineAttempt(
                instance,
                1,
                "fetch_failed" if navigation_error else "parse_empty",
                url,
                navigation_error,
            )
        except Exception as exc:
            return [], None, TimelineAttempt(instance, 1, "fetch_failed", url, str(exc))
        finally:
            if context:
                context.close()
            if browser:
                browser.close()


def _nitter_url(instance: str, username: str, cursor: str | None) -> str:
    base = f"https://{instance.strip().removeprefix('https://').removeprefix('http://').rstrip('/')}/{username}"
    if not cursor:
        return base
    return base + "?cursor=" + urllib.parse.quote(cursor, safe="")


def _blocked_reason(html: str) -> str | None:
    lower = html.lower()
    for marker, reason in BOT_PROTECTION_MARKERS:
        if marker in lower:
            return reason
    return None


def _candidate_from_nitter(payload: dict[str, Any]) -> TweetCandidate | None:
    tweet_id = str(payload.get("tweet_id") or "").strip()
    author = str(payload.get("author") or "").strip().lstrip("@")
    if not tweet_id or not author:
        return None
    return TweetCandidate(
        tweet_id=tweet_id,
        author_username=author,
        author_display_name=str(payload.get("author_name") or author).strip(),
        text=str(payload.get("text") or "").strip(),
        reply_count=_int(payload.get("replies")),
        retweet_count=_int(payload.get("retweets")),
        like_count=_int(payload.get("likes")),
        view_count=_int(payload.get("views")),
        media_urls=[url for url in payload.get("media", []) if isinstance(url, str)],
        is_pinned=bool(payload.get("is_pinned")),
        source="nitter",
    )


NITTER_TIMELINE_JS = """() => {
  const items = document.querySelectorAll(".timeline-item");
  const results = [];
  for (const item of items) {
    const link = item.querySelector("a.tweet-link");
    const href = link ? link.getAttribute("href") : "";
    const match = href ? href.match(/status\\/(\\d+)/) : null;
    const tweetId = match ? match[1] : "";
    const fullname = item.querySelector("a.fullname");
    const username = item.querySelector("a.username");
    const dateEl = item.querySelector(".tweet-date a");
    const content = item.querySelector(".tweet-content");
    let replies = 0;
    let retweets = 0;
    let likes = 0;
    let views = 0;
    for (const stat of item.querySelectorAll(".tweet-stat")) {
      const value = parseInt(stat.textContent.replace(/,/g, "").trim()) || 0;
      if (stat.querySelector(".icon-comment")) replies = value;
      else if (stat.querySelector(".icon-retweet")) retweets = value;
      else if (stat.querySelector(".icon-heart")) likes = value;
      else if (stat.querySelector(".icon-stats")) views = value;
    }
    const media = [];
    for (const img of item.querySelectorAll(".attachments img.still-image")) {
      const src = img.getAttribute("src") || "";
      if (!src.startsWith("/pic/")) continue;
      const decoded = decodeURIComponent(src.replace("/pic/", ""));
      if (decoded.startsWith("media/")) {
        media.push("https://pbs.twimg.com/media/" + decoded.slice(6));
      }
    }
    const pinnedMarker = item.querySelector(".pinned, .pinned-tweet, .tweet-pinned, .icon-pin");
    const itemText = item.textContent || "";
    results.push({
      tweet_id: tweetId,
      author_name: fullname ? fullname.textContent.trim() : "",
      author: username ? username.textContent.trim() : "",
      time_ago: dateEl ? dateEl.textContent.trim() : "",
      text: content ? content.textContent.trim() : "",
      replies,
      retweets,
      likes,
      views,
      media,
      is_pinned: Boolean(pinnedMarker) || /^\\s*pinned\\s+/i.test(itemText)
    });
  }
  return results;
}"""


NITTER_CURSOR_JS = """() => {
  const link = document.querySelector("a.show-more[href*='cursor'], .show-more a[href*='cursor']");
  if (!link) return null;
  const href = link.getAttribute("href");
  const match = href ? href.match(/[?&]cursor=([^&#]+)/) : null;
  return match ? decodeURIComponent(match[1]) : null;
}"""


def capture_recent(username_or_url: str, *, limit: int = 10, max_pages: int = 3) -> tuple[list[CaptureRecord], list[TimelineAttempt]]:
    username = normalize_username(username_or_url)
    candidates, attempts = collect_from_fxtwitter(username, limit=limit, max_pages=max_pages)
    if not candidates:
        seen: set[str] = set()
        candidates = []
        for instance in DEFAULT_NITTER_INSTANCES:
            cursor: str | None = None
            for page in range(1, max_pages + 1):
                page_candidates, cursor, attempt = nitter_timeline_page(username, instance=instance, cursor=cursor)
                attempt.page = page
                attempts.append(attempt)
                for candidate in page_candidates:
                    if candidate.author_username.lower() == username.lower() and candidate.tweet_id not in seen:
                        seen.add(candidate.tweet_id)
                        candidates.append(candidate)
                        if len(candidates) >= limit:
                            break
                if len(candidates) >= limit or not cursor:
                    break
                time.sleep(0.8)
            if candidates:
                break
    records = [detail_to_record(username, candidate) for candidate in candidates[:limit]]
    return records, attempts


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture recent public Twitter/X posts.")
    parser.add_argument("username_or_url")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--max-pages", type=int, default=3)
    args = parser.parse_args()
    records, attempts = capture_recent(args.username_or_url, limit=args.limit, max_pages=args.max_pages)
    for attempt in attempts:
        print(f"[attempt] {attempt.source} page={attempt.page} status={attempt.status} error={attempt.error or '-'}", file=sys.stderr)
    for record in records:
        print(record)
    return 0 if records else 1


if __name__ == "__main__":
    raise SystemExit(main())
