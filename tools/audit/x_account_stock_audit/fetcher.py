from __future__ import annotations

import re
import time
from datetime import date, datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

from packages.x.fxtwitter import fetch_user_statuses

from .models import AuditPost


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{1,15}$")


def normalize_username(raw: str) -> str:
    value = raw.strip()
    if value.startswith("@"):
        value = value[1:]
    if "://" in value:
        from urllib.parse import urlparse

        parsed = urlparse(value)
        value = parsed.path.strip("/").split("/", 1)[0]
    value = value.strip()
    if not USERNAME_RE.fullmatch(value):
        raise ValueError(f"Invalid X username/profile: {raw}")
    return value


def parse_fxtwitter_created_at(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw.strip(), "%a %b %d %H:%M:%S %z %Y").astimezone(SHANGHAI_TZ)
    except ValueError:
        return None


def _status_text(payload: dict[str, Any]) -> str:
    value = payload.get("text") or payload.get("raw_text") or ""
    if isinstance(value, dict):
        value = value.get("text") or ""
    return str(value or "").strip()


def _count(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def is_pure_retweet(payload: dict[str, Any]) -> bool:
    text = _status_text(payload)
    if text.startswith("RT @"):
        return True
    author = payload.get("author") if isinstance(payload.get("author"), dict) else {}
    retweeted_by = str(payload.get("retweeted_by") or payload.get("retweetedBy") or "").strip()
    return bool(retweeted_by and not text and not author)


def post_from_status(payload: dict[str, Any], username: str) -> AuditPost | None:
    author = payload.get("author") if isinstance(payload.get("author"), dict) else {}
    screen_name = str(author.get("screen_name") or "").strip().lstrip("@")
    if screen_name.casefold() != username.casefold():
        return None
    if is_pure_retweet(payload):
        return None

    tweet_id = str(payload.get("id") or "").strip()
    published_dt = parse_fxtwitter_created_at(str(payload.get("created_at") or ""))
    text = _status_text(payload)
    if not tweet_id or published_dt is None or not text:
        return None

    return AuditPost(
        tweet_id=tweet_id,
        author=f"@{screen_name}",
        author_name=str(author.get("name") or screen_name).strip(),
        text=text,
        published_at=published_dt.isoformat(timespec="seconds"),
        url=str(payload.get("url") or f"https://x.com/{username}/status/{tweet_id}"),
        likes=_count(payload.get("likes")),
        retweets=_count(payload.get("reposts") or payload.get("retweets")),
        replies=_count(payload.get("replies")),
        views=_count(payload.get("views")),
        raw=payload,
    )


def fetch_posts(
    *,
    username: str,
    start_date: date,
    end_date: date,
    max_pages: int = 300,
    page_pause_sec: float = 0.2,
    fetch_statuses: Callable[..., tuple[list[dict[str, Any]], dict[str, Any] | None]] = fetch_user_statuses,
    existing_posts: list[AuditPost] | None = None,
) -> tuple[list[AuditPost], list[dict[str, Any]], dict[str, Any]]:
    seen_ids = {post.tweet_id for post in existing_posts or []}
    posts: list[AuditPost] = list(existing_posts or [])
    raw_statuses: list[dict[str, Any]] = []
    cursor: str | None = None
    pages_fetched = 0
    stopped_reason = "max_pages"

    for page in range(1, max_pages + 1):
        raw_page, cursor_payload = fetch_statuses(username, count=20, cursor=cursor)
        pages_fetched = page
        if not raw_page:
            stopped_reason = "empty_page"
            break

        raw_statuses.extend(raw_page)
        page_dates: list[date] = []
        for raw_status in raw_page:
            published_dt = parse_fxtwitter_created_at(str(raw_status.get("created_at") or ""))
            if published_dt:
                page_dates.append(published_dt.date())

            post = post_from_status(raw_status, username)
            if post is None:
                continue
            post_date = datetime.fromisoformat(post.published_at).date()
            if post_date < start_date or post_date > end_date:
                continue
            if post.tweet_id in seen_ids:
                continue
            seen_ids.add(post.tweet_id)
            posts.append(post)

        if page_dates and max(page_dates) < start_date:
            stopped_reason = "before_start_date"
            break

        next_cursor = (cursor_payload or {}).get("bottom")
        if not next_cursor:
            stopped_reason = "no_cursor"
            break
        cursor = str(next_cursor)
        if page_pause_sec > 0:
            time.sleep(page_pause_sec)

    posts.sort(key=lambda item: item.published_at)
    return posts, raw_statuses, {
        "pages_fetched": pages_fetched,
        "stopped_reason": stopped_reason,
        "post_count": len(posts),
    }

