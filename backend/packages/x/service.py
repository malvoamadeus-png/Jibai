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

from .browser import TimelineFetchStatus, fetch_timeline_page
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
    is_pinned: bool = False


@dataclass(slots=True)
class CrawlRunSummary:
    exit_code: int
    account_results: list[CrawlAccountResult]
    new_notes: list[RawNoteRecord]
    errors: list[str]


@dataclass(slots=True)
class TimelineAttempt:
    instance: str
    page: int
    status: TimelineFetchStatus
    url: str
    error: str | None = None


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
        is_pinned=bool(payload.get("is_pinned")),
    )


def collect_tweet_candidates(
    *,
    cfg: WatchlistConfig,
    paths: AppPaths,
    account: AccountTarget,
    limit: int | None = None,
    max_pages: int = 3,
) -> tuple[list[TweetCandidate], list[TimelineAttempt]]:
    target_author = f"@{account.username.lower()}"
    target_limit = limit or account.limit
    seen_ids: set[str] = set()
    results: list[TweetCandidate] = []
    attempts: list[TimelineAttempt] = []

    for instance_index, instance in enumerate(cfg.nitter_instances, start=1):
        cursor: str | None = None
        page = 1
        while len(results) < target_limit and page <= max_pages:
            debug_dir = paths.x_debug_dir / account.safe_name
            debug_prefix = f"{account.safe_name}-{instance_index}-{page}-{int(time.time())}"
            page_result = fetch_timeline_page(
                username=account.username,
                nitter_instance=instance,
                cursor=cursor,
                wait_sec=cfg.page_wait_sec,
                headless=cfg.headless,
                debug_dir=debug_dir,
                debug_prefix=debug_prefix,
            )
            attempts.append(
                TimelineAttempt(
                    instance=instance,
                    page=page,
                    status=page_result.status,
                    url=page_result.url,
                    error=page_result.error,
                )
            )
            raw_items = page_result.items
            cursor = page_result.next_cursor
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
                if len(results) >= target_limit:
                    break

            if not cursor or len(results) >= target_limit:
                break
            page += 1
            time.sleep(0.8)

        if results:
            return results[:target_limit], attempts

    return results[:target_limit], attempts


def _build_empty_timeline_error(attempts: list[TimelineAttempt]) -> str:
    if not attempts:
        return "X_OTHER: 其他：没有执行任何 Nitter 页面尝试。"

    status_counts = {
        status: sum(1 for attempt in attempts if attempt.status == status)
        for status in ("runtime_failed", "fetch_failed", "parse_failed", "parse_empty")
    }
    summary = (
        f"尝试 {len(attempts)} 次；"
        f"运行环境错误={status_counts['runtime_failed']}，"
        f"没抓到={status_counts['fetch_failed']}，"
        f"解析失败={status_counts['parse_failed']}，"
        f"解析为空={status_counts['parse_empty']}"
    )
    details = [
        f"{attempt.instance}/p{attempt.page}: {attempt.status}"
        + (f" ({attempt.error})" if attempt.error else "")
        for attempt in attempts[:5]
    ]
    detail_text = "；明细：" + "；".join(details) if details else ""
    blocked_attempts = [
        attempt
        for attempt in attempts
        if attempt.error
        and any(
            marker in attempt.error.lower()
            for marker in (
                "verification",
                "anti-bot",
                "captcha",
                "cloudflare",
                "ddos-guard",
                "access denied",
            )
        )
    ]

    if status_counts["runtime_failed"] == len(attempts):
        first_error = next((attempt.error for attempt in attempts if attempt.error), "")
        if "executable doesn't exist" in first_error.lower():
            return f"X_RUNTIME_FAILED: 本地抓取运行环境错误：Playwright Chromium 未安装。{summary}{detail_text}。"
        return f"X_RUNTIME_FAILED: 本地抓取运行环境错误：浏览器启动失败。{summary}{detail_text}。"
    if blocked_attempts and len(blocked_attempts) == len(attempts):
        return f"X_FETCH_FAILED: 所有公开 Nitter 镜像都被安全验证或反机器人保护拦截。{summary}{detail_text}。"
    if status_counts["fetch_failed"] == len(attempts):
        return f"X_FETCH_FAILED: 没抓到：所有公开 Nitter 镜像主页请求失败。{summary}{detail_text}。"
    if status_counts["parse_failed"] or status_counts["parse_empty"]:
        return (
            "X_PARSE_EMPTY: 解析问题：公开 Nitter 页面已返回，但没有解析到可用 tweet。"
            f"{summary}{detail_text}。"
        )
    return f"X_OTHER: 其他：未解析到 tweet，但失败类型不明确。{summary}{detail_text}。"


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
        metadata={"is_pinned": candidate.is_pinned},
    )


def _short_exception_message(exc: Exception) -> str:
    message = str(exc).strip()
    if " for url:" in message:
        message = message.split(" for url:", 1)[0].strip()
    return message or exc.__class__.__name__


def _detail_error_summary(errors: list[str]) -> str:
    if not errors:
        return ""
    sample = "；".join(errors[:3])
    return f"部分内容详情抓取失败 {len(errors)} 条，已跳过；示例：{sample}"


def crawl_account_once(
    *,
    cfg: WatchlistConfig,
    paths: AppPaths,
    account: AccountTarget,
    seen_note_ids: set[str] | None = None,
    target_limit: int | None = None,
    max_pages: int = 3,
    max_post_age_days: int | None = None,
    exclude_old_posts: bool | None = None,
    skip_old_pinned: bool = False,
    run_at: str | None = None,
) -> tuple[CrawlAccountResult, list[RawNoteRecord], set[str]]:
    fetched_at = run_at or now_iso()
    seen_ids = set(seen_note_ids or set())
    accepted_notes: list[RawNoteRecord] = []
    fetched_note_ids: list[str] = []
    account_error: str | None = None
    candidate_count = 0
    new_count = 0
    target_count = target_limit or account.limit
    scan_limit = max(target_count, target_count * 3)
    detail_errors: list[str] = []

    try:
        user_info = fetch_user_info(account.username)
        candidates, timeline_attempts = collect_tweet_candidates(
            cfg=cfg,
            paths=paths,
            account=account,
            limit=scan_limit,
            max_pages=max_pages,
        )
        candidate_count = len(candidates)
        if not candidates:
            raise RuntimeError(_build_empty_timeline_error(timeline_attempts))

        for candidate in candidates:
            fetched_note_ids.append(candidate.tweet_id)
            if candidate.tweet_id in seen_ids:
                continue

            try:
                detail = fetch_tweet_detail(account.username, candidate.tweet_id)
            except Exception as exc:
                short_message = _short_exception_message(exc)
                detail_errors.append(f"{candidate.tweet_id}: {short_message}")
                print(
                    f"[x] account {account.name} skip tweet {candidate.tweet_id}: {short_message}",
                    file=sys.stderr,
                )
                continue

            detail_author = detail.get("author") if isinstance(detail.get("author"), dict) else {}
            detail_screen_name = str(detail_author.get("screen_name") or account.username).strip()
            if detail_screen_name.lower() != account.username.lower():
                continue

            note = _build_note_record(
                account=account,
                candidate=candidate,
                detail=detail,
                user_info=user_info,
                fetched_at=fetched_at,
            )
            age_days = max_post_age_days if max_post_age_days is not None else cfg.max_post_age_days
            should_exclude_old = cfg.exclude_old_posts if exclude_old_posts is None else exclude_old_posts
            is_old = is_older_than_days(
                note.publish_time,
                days=age_days,
                reference_time=fetched_at,
            )
            if skip_old_pinned and candidate.is_pinned and is_old:
                print(
                    f"[x] account {account.name} skip old pinned post {note.note_id} "
                    f"older than {age_days} days",
                    file=sys.stderr,
                )
                continue
            if should_exclude_old and is_old:
                print(
                    f"[x] account {account.name} skip old post {note.note_id} "
                    f"older than {age_days} days",
                    file=sys.stderr,
                )
                continue

            accepted_notes.append(note)
            seen_ids.add(candidate.tweet_id)
            new_count += 1
            if len(accepted_notes) >= target_count:
                break

        if detail_errors and not accepted_notes:
            raise RuntimeError(_detail_error_summary(detail_errors))
        if detail_errors:
            account_error = _detail_error_summary(detail_errors)
        status = "success"
    except Exception as exc:
        account_error = str(exc)
        status = "failed"
        print(f"[x] account {account.name} failed: {account_error}", file=sys.stderr)

    result = CrawlAccountResult(
        platform="x",
        account_name=account.name,
        profile_url=account.profile_url,
        run_at=fetched_at,
        status=status,  # type: ignore[arg-type]
        candidate_count=candidate_count,
        new_note_count=new_count,
        fetched_note_ids=fetched_note_ids,
        error=account_error,
    )
    return result, accepted_notes, seen_ids


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

        result, account_notes, updated_seen_note_ids = crawl_account_once(
            cfg=cfg,
            paths=paths,
            account=account,
            seen_note_ids=seen_note_ids,
            run_at=run_at,
        )
        new_notes.extend(account_notes)
        fetched_note_ids = result.fetched_note_ids
        account_error = result.error
        if result.status == "success":
            bucket["seen_note_ids"] = sorted(updated_seen_note_ids)
            bucket["last_run_at"] = run_at
            bucket["last_error"] = None
        else:
            bucket["last_run_at"] = run_at
            bucket["last_error"] = account_error
            errors.append(f"[x {account.name}] {account_error}")

        results.append(
            CrawlAccountResult(
                platform=result.platform,
                account_name=result.account_name,
                profile_url=result.profile_url,
                run_at=run_at,
                status=result.status,
                candidate_count=result.candidate_count,
                new_note_count=result.new_note_count,
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
