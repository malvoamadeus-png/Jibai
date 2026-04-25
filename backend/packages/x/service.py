from __future__ import annotations

import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packages.common.io import read_json, write_json
from packages.common.models import CrawlAccountResult, RawNoteRecord
from packages.common.paths import AppPaths
from packages.common.time_utils import is_older_than_days, now_iso

from .browser import fetch_timeline_page
from .config import AccountTarget, WatchlistConfig
from .fxtwitter import fetch_tweet_detail, fetch_user_info, parse_created_at


@dataclass(slots=True)
class TweetCandidate:
    tweet_id: str
    author: str
    author_name: str
    text: str
    time_ago: str
    replies: int
    retweets: int
    likes: int
    views: int
    media: list[str]
    retweeted_by: str | None = None


@dataclass(slots=True)
class CrawlRunSummary:
    exit_code: int
    account_results: list[CrawlAccountResult]
    new_notes: list[RawNoteRecord]
    errors: list[str]


def _load_state(path: Path) -> dict[str, Any]:
    return read_json(path, default={"accounts": {}})


def _save_state(path: Path, payload: dict[str, Any]) -> None:
    write_json(path, payload)


def _ensure_state_bucket(state: dict[str, Any], account_name: str) -> dict[str, Any]:
    accounts = state.setdefault("accounts", {})
    bucket = accounts.setdefault(
        account_name,
        {"seen_note_ids": [], "last_run_at": None, "last_error": None},
    )
    bucket.setdefault("seen_note_ids", [])
    return bucket


def _account_pause_seconds(cfg: WatchlistConfig) -> float:
    return cfg.inter_account_delay_sec + random.uniform(0.0, cfg.inter_account_delay_jitter_sec)


def _build_title(text: str, fallback: str) -> str:
    compact = " ".join(text.split())
    if not compact:
        return fallback
    return compact[:80]


def _coerce_media(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    for item in value:
        if isinstance(item, str) and item and item not in cleaned:
            cleaned.append(item)
    return cleaned


def _candidate_from_payload(payload: dict[str, Any]) -> TweetCandidate | None:
    tweet_id = str(payload.get("tweet_id") or "").strip()
    author = str(payload.get("author") or "").strip()
    if not tweet_id or not author:
        return None
    return TweetCandidate(
        tweet_id=tweet_id,
        author=author,
        author_name=str(payload.get("author_name") or author).strip(),
        text=str(payload.get("text") or "").strip(),
        time_ago=str(payload.get("time_ago") or "").strip(),
        replies=int(payload.get("replies") or 0),
        retweets=int(payload.get("retweets") or 0),
        likes=int(payload.get("likes") or 0),
        views=int(payload.get("views") or 0),
        media=_coerce_media(payload.get("media")),
        retweeted_by=(
            str(payload.get("retweeted_by") or "").strip() or None
        ),
    )


def collect_tweet_candidates(
    *,
    cfg: WatchlistConfig,
    paths: AppPaths,
    account: AccountTarget,
) -> list[TweetCandidate]:
    target_author = f"@{account.username.lower()}"
    seen_ids: set[str] = set()
    results: list[TweetCandidate] = []

    for instance_index, instance in enumerate(cfg.nitter_instances, start=1):
        cursor: str | None = None
        page = 1
        max_pages = 3
        while len(results) < account.limit and page <= max_pages:
            debug_dir = paths.x_debug_dir / account.safe_name
            debug_prefix = f"{account.safe_name}-{instance_index}-{page}-{int(time.time())}"
            raw_items, cursor = fetch_timeline_page(
                username=account.username,
                nitter_instance=instance,
                cursor=cursor,
                wait_sec=cfg.page_wait_sec,
                headless=cfg.headless,
                debug_dir=debug_dir,
                debug_prefix=debug_prefix,
            )
            if not raw_items:
                break

            for raw_item in raw_items:
                candidate = _candidate_from_payload(raw_item)
                if candidate is None:
                    continue
                if candidate.author.lower() != target_author:
                    continue
                if candidate.tweet_id in seen_ids:
                    continue
                seen_ids.add(candidate.tweet_id)
                results.append(candidate)
                if len(results) >= account.limit:
                    break

            if not cursor or len(results) >= account.limit:
                break
            page += 1
            time.sleep(0.8)

        if results:
            return results[: account.limit]

    return results[: account.limit]


def _build_note_record(
    *,
    account: AccountTarget,
    candidate: TweetCandidate,
    detail: dict[str, Any],
    user_info: dict[str, Any],
    fetched_at: str,
) -> RawNoteRecord:
    author = detail.get("author") if isinstance(detail.get("author"), dict) else {}
    author_screen_name = str(
        author.get("screen_name")
        or user_info.get("screen_name")
        or account.username
    ).strip()
    author_name = str(
        author.get("name")
        or user_info.get("name")
        or candidate.author_name
        or account.name
    ).strip()

    text = str(detail.get("text") or detail.get("raw_text") or candidate.text).strip()
    created_at = parse_created_at(str(detail.get("created_at") or ""))
    url = str(detail.get("url") or f"https://x.com/{account.username}/status/{candidate.tweet_id}")
    likes = int(detail.get("likes") or candidate.likes or 0)
    replies = int(detail.get("replies") or candidate.replies or 0)
    retweets = int(detail.get("retweets") or candidate.retweets or 0)
    bookmarks = int(detail.get("bookmarks") or 0)

    media_urls: list[str] = []
    media_payload = detail.get("media")
    if isinstance(media_payload, dict):
        all_media = media_payload.get("all")
        if isinstance(all_media, list):
            for item in all_media:
                if not isinstance(item, dict):
                    continue
                media_url = str(item.get("url") or "").strip()
                if media_url and media_url not in media_urls:
                    media_urls.append(media_url)
    if not media_urls:
        media_urls = list(candidate.media)

    title = _build_title(text, fallback=f"Tweet {candidate.tweet_id}")
    if media_urls and text:
        desc = f"{text}\n\n[media] " + " ".join(media_urls[:4])
    elif media_urls:
        desc = "[media] " + " ".join(media_urls[:4])
    else:
        desc = text

    return RawNoteRecord(
        platform="x",
        account_name=account.name,
        profile_url=account.profile_url,
        note_id=candidate.tweet_id,
        url=url,
        title=title,
        desc=desc,
        author_id=str(author.get("id") or ""),
        author_nickname=author_name or author_screen_name,
        note_type="tweet",
        publish_time=created_at,
        last_update_time=None,
        like_count=likes,
        collect_count=bookmarks,
        comment_count=replies,
        share_count=retweets,
        fetched_at=fetched_at,
    )


def run_once(cfg: WatchlistConfig, paths: AppPaths) -> CrawlRunSummary:
    state = _load_state(paths.x_state_path)
    run_at = now_iso()
    results: list[CrawlAccountResult] = []
    new_notes: list[RawNoteRecord] = []
    errors: list[str] = []

    for index, account in enumerate(cfg.accounts):
        bucket = _ensure_state_bucket(state, account.name)
        seen_note_ids = set(bucket.get("seen_note_ids") or [])
        fetched_note_ids: list[str] = []
        account_error: str | None = None
        candidate_count = 0
        new_count = 0

        try:
            user_info = fetch_user_info(account.username)
            candidates = collect_tweet_candidates(cfg=cfg, paths=paths, account=account)
            candidate_count = len(candidates)
            if not candidates:
                raise RuntimeError(
                    "Could not resolve any tweets from public Nitter pages. "
                    "Try again later or adjust nitter_instances."
                )

            for candidate in candidates:
                fetched_note_ids.append(candidate.tweet_id)
                detail = fetch_tweet_detail(account.username, candidate.tweet_id)
                detail_author = detail.get("author") if isinstance(detail.get("author"), dict) else {}
                detail_screen_name = str(detail_author.get("screen_name") or account.username).strip()
                if detail_screen_name.lower() != account.username.lower():
                    continue
                if candidate.tweet_id in seen_note_ids:
                    continue

                note = _build_note_record(
                    account=account,
                    candidate=candidate,
                    detail=detail,
                    user_info=user_info,
                    fetched_at=run_at,
                )
                if cfg.exclude_old_posts and is_older_than_days(
                    note.publish_time,
                    days=cfg.max_post_age_days,
                    reference_time=run_at,
                ):
                    print(
                        f"[x] account {account.name} skip old post {note.note_id} "
                        f"older than {cfg.max_post_age_days} days",
                        file=sys.stderr,
                    )
                    continue
                new_notes.append(note)
                seen_note_ids.add(candidate.tweet_id)
                new_count += 1

            bucket["seen_note_ids"] = sorted(seen_note_ids)
            bucket["last_run_at"] = run_at
            bucket["last_error"] = None
            status = "success"
        except Exception as exc:
            account_error = str(exc)
            bucket["last_run_at"] = run_at
            bucket["last_error"] = account_error
            status = "failed"
            errors.append(f"[x {account.name}] {account_error}")
            print(f"[x] account {account.name} failed: {account_error}", file=sys.stderr)

        results.append(
            CrawlAccountResult(
                platform="x",
                account_name=account.name,
                profile_url=account.profile_url,
                run_at=run_at,
                status=status,  # type: ignore[arg-type]
                candidate_count=candidate_count,
                new_note_count=new_count,
                fetched_note_ids=fetched_note_ids,
                error=account_error,
            )
        )

        _save_state(paths.x_state_path, state)

        if index < len(cfg.accounts) - 1:
            time.sleep(_account_pause_seconds(cfg))

    exit_code = 0 if not errors else 1
    return CrawlRunSummary(
        exit_code=exit_code,
        account_results=results,
        new_notes=new_notes,
        errors=errors,
    )
