from __future__ import annotations

import sys
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright


TIMELINE_JS = """() => {
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
    const statsEls = item.querySelectorAll(".tweet-stat");
    for (const stat of statsEls) {
      const value = parseInt(stat.textContent.replace(/,/g, "").trim()) || 0;
      if (stat.querySelector(".icon-comment")) replies = value;
      else if (stat.querySelector(".icon-retweet")) retweets = value;
      else if (stat.querySelector(".icon-heart")) likes = value;
      else if (stat.querySelector(".icon-stats")) views = value;
    }

    const mediaImgs = item.querySelectorAll(".attachments img.still-image");
    const media = [];
    for (const img of mediaImgs) {
      const src = img.getAttribute("src") || "";
      if (!src.startsWith("/pic/")) continue;
      const decoded = decodeURIComponent(src.replace("/pic/", ""));
      if (decoded.startsWith("media/")) {
        media.push("https://pbs.twimg.com/media/" + decoded.slice(6));
      }
    }

    const retweetBanner = item.querySelector(".retweet-header");
    const retweetedBy = retweetBanner
      ? retweetBanner.textContent.trim().replace(/ retweeted$/, "").trim()
      : null;
    const pinnedMarker = item.querySelector(".pinned, .pinned-tweet, .tweet-pinned, .icon-pin");
    const headerText = item.querySelector(".timeline-item-header, .tweet-header, .pinned")?.textContent || "";
    const itemText = item.textContent || "";
    const isPinned = Boolean(pinnedMarker)
      || /(^|\\s)pinned(\\s|$)/i.test(headerText)
      || /^\\s*pinned\\s+/i.test(itemText);

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
      retweeted_by: retweetedBy,
      is_pinned: isPinned
    });
  }
  return results;
}"""

CURSOR_JS = """() => {
  const moreLink = document.querySelector("a.show-more[href*='cursor'], .show-more a[href*='cursor']");
  if (!moreLink) return null;
  const href = moreLink.getAttribute("href");
  const match = href ? href.match(/[?&]cursor=([^&#]+)/) : null;
  return match ? decodeURIComponent(match[1]) : null;
}"""

BOT_PROTECTION_MARKERS = (
    ("anubis", "blocked by Anubis bot protection"),
    ("x cancelled | verifying your request", "blocked by XCancel request verification"),
    ("verifying your request", "request verification required"),
    ("performing security verification", "security verification required"),
    ("uses a security service to protect against malicious bots", "security verification required"),
    ("website verifies you are not a bot", "security verification required"),
    ("verifies you are not a bot", "security verification required"),
    ("verify you are human", "human verification required"),
    ("checking if the site connection is secure", "security verification required"),
    ("antibot", "anti-bot verification required"),
    ("access denied", "access denied"),
    ("captcha", "captcha required"),
    ("cloudflare", "blocked by Cloudflare"),
    ("ddos-guard", "blocked by DDoS-Guard"),
    ("rate limit", "rate limited"),
    ("too many requests", "rate limited"),
)
BLOCKED_RESOURCE_TYPES = {"font", "image", "media"}

TimelineFetchStatus = Literal[
    "success",
    "runtime_failed",
    "fetch_failed",
    "parse_failed",
    "parse_empty",
]


@dataclass(frozen=True)
class TimelinePageResult:
    items: list[dict[str, Any]]
    next_cursor: str | None
    status: TimelineFetchStatus
    url: str
    error: str | None = None


def _launch_browser(playwright: Playwright, *, headless: bool) -> Browser:
    return playwright.chromium.launch(
        headless=headless,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-blink-features=AutomationControlled",
        ],
    )


def _new_context(browser: Browser) -> BrowserContext:
    return browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        locale="en-US",
        viewport={"width": 1280, "height": 900},
    )


def _safe_goto(page: Page, url: str) -> str | None:
    try:
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        return None
    except Exception as exc:
        return str(exc)


def _block_heavy_resources(page: Page) -> None:
    try:
        page.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in BLOCKED_RESOURCE_TYPES
            else route.continue_(),
        )
    except Exception:
        pass


def _write_debug_snapshot(page: Page, target_dir: Path, prefix: str) -> None:
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(target_dir / f"{prefix}.png"), full_page=True)
        (target_dir / f"{prefix}.html").write_text(page.content(), encoding="utf-8")
    except Exception as exc:
        print(f"[x-browser] failed to write debug snapshot {prefix}: {exc}", file=sys.stderr)


def _detect_blocked_page(page: Page) -> str | None:
    try:
        content = page.content().lower()
    except Exception:
        return None
    for marker, reason in BOT_PROTECTION_MARKERS:
        if marker in content:
            return reason
    return None


def _evaluate_timeline(page: Page) -> tuple[list[dict[str, Any]], str | None]:
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            tweets = page.evaluate(TIMELINE_JS) or []
            next_cursor = page.evaluate(CURSOR_JS)
            return tweets, next_cursor
        except Exception as exc:
            last_error = exc
            if "execution context was destroyed" not in str(exc).lower() or attempt == 1:
                break
            try:
                page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass
            time.sleep(0.5)
    assert last_error is not None
    raise last_error


def fetch_timeline_page(
    *,
    username: str,
    nitter_instance: str,
    cursor: str | None,
    wait_sec: float,
    headless: bool,
    debug_dir: Path | None = None,
    debug_prefix: str | None = None,
) -> TimelinePageResult:
    if cursor:
        url = f"https://{nitter_instance}/{username}?cursor={urllib.parse.quote(cursor, safe='')}"
    else:
        url = f"https://{nitter_instance}/{username}"

    playwright = sync_playwright().start()
    browser = None
    context = None
    try:
        try:
            browser = _launch_browser(playwright, headless=headless)
        except Exception as exc:
            return TimelinePageResult(
                items=[],
                next_cursor=None,
                status="runtime_failed",
                url=url,
                error=str(exc),
            )
        context = _new_context(browser)
        page = context.new_page()
        _block_heavy_resources(page)
        navigation_error = _safe_goto(page, url)
        time.sleep(wait_sec)
        try:
            tweets, next_cursor = _evaluate_timeline(page)
        except Exception as exc:
            blocked_reason = _detect_blocked_page(page)
            if blocked_reason:
                if debug_dir and debug_prefix:
                    _write_debug_snapshot(page, debug_dir, debug_prefix)
                return TimelinePageResult(
                    items=[],
                    next_cursor=None,
                    status="fetch_failed",
                    url=url,
                    error=blocked_reason,
                )
            if debug_dir and debug_prefix:
                _write_debug_snapshot(page, debug_dir, debug_prefix)
            return TimelinePageResult(
                items=[],
                next_cursor=None,
                status="parse_failed",
                url=url,
                error=str(exc),
            )

        if debug_dir and debug_prefix and not tweets:
            _write_debug_snapshot(page, debug_dir, debug_prefix)

        if tweets:
            return TimelinePageResult(
                items=tweets,
                next_cursor=next_cursor,
                status="success",
                url=url,
            )
        blocked_reason = _detect_blocked_page(page)
        if blocked_reason:
            return TimelinePageResult(
                items=[],
                next_cursor=None,
                status="fetch_failed",
                url=url,
                error=blocked_reason,
            )
        if navigation_error:
            return TimelinePageResult(
                items=[],
                next_cursor=None,
                status="fetch_failed",
                url=url,
                error=navigation_error,
            )
        return TimelinePageResult(
            items=[],
            next_cursor=next_cursor,
            status="parse_empty",
            url=url,
        )
    except Exception as exc:
        print(
            f"[x-browser] failed on {nitter_instance}/{username}: {exc}",
            file=sys.stderr,
        )
        return TimelinePageResult(
            items=[],
            next_cursor=None,
            status="fetch_failed",
            url=url,
            error=str(exc),
        )
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
            playwright.stop()
        except Exception:
            pass
