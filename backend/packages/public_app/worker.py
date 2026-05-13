from __future__ import annotations

import os
import re
import time
from datetime import datetime, timedelta
from typing import Any

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from packages.ai.pipeline import (
    LIGHT_MARKET_DATA_MAX_SECURITIES,
    LIGHT_MARKET_DATA_WINDOW_DAYS,
    MARKET_DATA_WINDOW_DAYS,
    refresh_security_market_data,
    run_analysis_with_store,
)
from packages.common.models import CrawlAccountResult, RawNoteRecord
from packages.common.paths import ensure_runtime_dirs, get_paths
from packages.common.postgres_database import PostgresInsightStore, postgres_connection
from packages.common.settings import load_settings
from packages.common.time_utils import SHANGHAI_TZ, note_date_key, now_iso, today_date_key
from packages.x.config import AccountTarget, WatchlistConfig
from packages.x.service import crawl_account_once

from .jobs import (
    CrawlJob,
    PublicXAccount,
    claim_next_job,
    enqueue_scheduled_crawl as insert_scheduled_crawl_job,
    list_accounts_for_job,
    list_seen_note_ids,
    mark_backfill_completed,
    mark_job_failed,
    mark_job_succeeded,
    requeue_stale_running_jobs,
)
from .market_top_risk import sync_market_top_risk_once


DEFAULT_CRAWL_TIMES = ("04:00", "10:00", "16:00", "22:00")
WORKER_LOCK_KEY = "jibai_public_x_worker"
_MARKET_ERROR_RE = re.compile(r"^\[market ([^\]]+)\]\s*(.*)$")


def _crawl_times() -> list[str]:
    raw = os.getenv("PUBLIC_WORKER_CRAWL_TIMES", ",".join(DEFAULT_CRAWL_TIMES))
    values = [item.strip() for item in raw.split(",") if item.strip()]
    return values or list(DEFAULT_CRAWL_TIMES)


def _top_risk_sync_time() -> str:
    return os.getenv("PUBLIC_WORKER_TOP_RISK_SYNC_TIME", "05:20").strip() or "05:20"


def _top_risk_history_limit() -> int:
    return max(1, _env_int("PUBLIC_WORKER_TOP_RISK_HISTORY_LIMIT", 90))


def _poll_seconds() -> int:
    return max(5, int(os.getenv("PUBLIC_WORKER_POLL_SECONDS", "30")))


def _account_pause_seconds() -> float:
    return max(0.0, float(os.getenv("PUBLIC_WORKER_ACCOUNT_DELAY_SECONDS", "5")))


def _light_market_data_days() -> int:
    return max(1, int(os.getenv("PUBLIC_WORKER_LIGHT_MARKET_DATA_DAYS", str(LIGHT_MARKET_DATA_WINDOW_DAYS))))


def _light_market_data_max_securities() -> int:
    return max(
        0,
        int(os.getenv("PUBLIC_WORKER_LIGHT_MARKET_DATA_MAX_SECURITIES", str(LIGHT_MARKET_DATA_MAX_SECURITIES))),
    )


def _analysis_window_days() -> int:
    return max(1, _env_int("PUBLIC_WORKER_ANALYSIS_WINDOW_DAYS", 3))


def _recent_window(days: int) -> tuple[str, str]:
    safe_days = max(1, int(days))
    end_date = today_date_key()
    start_date = (datetime.now(SHANGHAI_TZ).date() - timedelta(days=safe_days - 1)).isoformat()
    return start_date, end_date


def _filter_recent_notes(notes: list[RawNoteRecord], *, days: int) -> tuple[list[RawNoteRecord], str, str]:
    start_date, end_date = _recent_window(days)
    return (
        [
            note
            for note in notes
            if start_date <= note_date_key(note.publish_time, note.fetched_at) <= end_date
        ],
        start_date,
        end_date,
    )


def _nitter_instances() -> list[str] | None:
    raw = os.getenv("PUBLIC_WORKER_NITTER_INSTANCES", "").strip()
    if not raw:
        return None
    values = [item.strip().removeprefix("https://").removeprefix("http://").rstrip("/") for item in raw.split(",")]
    return [item for item in values if item]


def _try_acquire_worker_lock(conn: Any) -> bool:
    row = conn.execute("SELECT pg_try_advisory_lock(hashtext(%s)) AS locked", (WORKER_LOCK_KEY,)).fetchone()
    return bool(row and row["locked"])


def _release_worker_lock(conn: Any) -> None:
    conn.execute("SELECT pg_advisory_unlock(hashtext(%s))", (WORKER_LOCK_KEY,))


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _stale_running_job_minutes() -> int:
    return max(5, _env_int("PUBLIC_WORKER_STALE_JOB_MINUTES", 180))


def _clean_error_text(value: str) -> str:
    cleaned = " ".join(value.strip().split())
    if " for url:" in cleaned:
        cleaned = cleaned.split(" for url:", 1)[0].strip()
    return cleaned


def _market_error_sample(errors: list[str], *, limit: int = 3) -> str:
    labels: list[str] = []
    for error in errors:
        match = _MARKET_ERROR_RE.match(error)
        label = match.group(1) if match else error
        label = _clean_error_text(label)
        if label and label not in labels:
            labels.append(label)
        if len(labels) >= limit:
            break
    return "、".join(labels)


def _analysis_error_sample(errors: list[str]) -> str:
    for error in errors:
        if error.startswith("[x "):
            continue
        if "Missing AI API key" in error:
            return "缺少 AI API key，未生成结构化观点"
        cleaned = _clean_error_text(error)
        if cleaned:
            return cleaned[:80]
    return ""


def _build_job_summary(
    *,
    account_count: int,
    new_note_count: int,
    crawl_errors: list[str],
    crawl_warnings: list[str],
    market_prices: int,
    market_errors: list[str],
    total_errors: int,
    analysis_errors: list[str] | None = None,
) -> str:
    parts = [
        f"抓取 {account_count} 个账号",
        f"新增 {new_note_count} 条内容",
    ]
    if crawl_errors:
        parts.append(f"{len(crawl_errors)} 个账号抓取失败")
    if crawl_warnings:
        parts.append(f"{len(crawl_warnings)} 个账号有部分内容详情异常，已跳过")
    if market_prices:
        parts.append(f"写入 {market_prices} 条行情")
    if market_errors:
        sample = _market_error_sample(market_errors)
        suffix = f"（{sample}）" if sample else ""
        parts.append(f"{len(market_errors)} 个股票行情暂不可用{suffix}")

    non_crawl_errors = max(0, total_errors - len(crawl_errors))
    if non_crawl_errors:
        sample = _analysis_error_sample(analysis_errors or [])
        suffix = f"（{sample}）" if sample else ""
        parts.append(f"{non_crawl_errors} 项分析或入库异常{suffix}")
    if not crawl_errors and not crawl_warnings and not market_errors and total_errors == 0:
        parts.append("全部完成")
    return "；".join(parts) + "。"


def _base_x_config(accounts: list[AccountTarget]) -> WatchlistConfig:
    nitter_instances = _nitter_instances()
    return WatchlistConfig(
        enabled=bool(accounts),
        headless=os.getenv("PUBLIC_WORKER_HEADLESS", "true").lower() != "false",
        page_wait_sec=float(os.getenv("PUBLIC_WORKER_PAGE_WAIT_SECONDS", "6")),
        inter_account_delay_sec=_account_pause_seconds(),
        inter_account_delay_jitter_sec=0,
        exclude_old_posts=True,
        max_post_age_days=5,
        **({"nitter_instances": nitter_instances} if nitter_instances else {}),
        accounts=accounts,
    )


def _target_for_account(account: PublicXAccount, limit: int) -> AccountTarget:
    return AccountTarget(
        name=account.username,
        profile_url=account.profile_url,
        # AccountTarget is also used by the local config path, where large
        # limits are intentionally capped. The worker passes target_limit to
        # crawl_account_once, so this value only needs to satisfy validation.
        limit=min(limit, 20),
    )


def _run_account(
    *,
    store: PostgresInsightStore,
    conn: Any,
    account: PublicXAccount,
    job_kind: str,
    run_at: str,
) -> tuple[Any, int]:
    is_backfill = job_kind == "initial_backfill"
    target_limit = 30 if is_backfill else 5
    age_days = 30 if is_backfill else 5
    target = _target_for_account(account, limit=target_limit)
    cfg = _base_x_config([target])
    result, notes, _seen = crawl_account_once(
        cfg=cfg,
        paths=get_paths(),
        account=target,
        seen_note_ids=list_seen_note_ids(conn, account.id),
        target_limit=target_limit,
        max_pages=8 if is_backfill else 3,
        max_post_age_days=age_days,
        exclude_old_posts=True,
        skip_old_pinned=is_backfill,
        run_at=run_at,
    )
    for note in notes:
        store.upsert_content_item(note)
    return result, len(notes)


def _process_job(job: CrawlJob) -> None:
    paths = get_paths()
    ensure_runtime_dirs(paths)
    run_at = now_iso()

    with postgres_connection() as conn:
        store = PostgresInsightStore(conn)
        accounts = list_accounts_for_job(conn, job)
        if not accounts:
            mark_job_succeeded(conn, job.id, "No approved subscribed X accounts to crawl.")
            return

        crawl_results = []
        crawl_errors: list[str] = []
        crawl_warnings: list[str] = []
        total_new_notes = 0
        for index, account in enumerate(accounts):
            result, new_count = _run_account(
                store=store,
                conn=conn,
                account=account,
                job_kind=job.kind,
                run_at=run_at,
            )
            crawl_results.append(result)
            total_new_notes += new_count
            if result.status == "failed" and result.error:
                crawl_errors.append(f"[x {account.username}] {result.error}")
            elif result.error:
                crawl_warnings.append(f"[x {account.username}] {result.error}")
            if job.kind == "initial_backfill" and result.status == "success":
                mark_backfill_completed(conn, account.id)
            if index < len(accounts) - 1:
                time.sleep(_account_pause_seconds())

        all_notes = store.list_all_content_items(platform="x")
        notes, _start_date, _end_date = _filter_recent_notes(
            all_notes,
            days=_analysis_window_days(),
        )
        is_backfill = job.kind == "initial_backfill"
        summary = run_analysis_with_store(
            store=store,
            paths=paths,
            notes=notes,
            crawl_results=crawl_results,
            crawl_errors=crawl_errors,
            market_data_days=None if is_backfill else _light_market_data_days(),
            market_data_max_securities=None if is_backfill else _light_market_data_max_securities(),
        )
        mark_job_succeeded(
            conn,
            job.id,
            _build_job_summary(
                account_count=len(accounts),
                new_note_count=total_new_notes,
                crawl_errors=crawl_errors,
                crawl_warnings=crawl_warnings,
                market_prices=summary.market_prices,
                market_errors=summary.market_errors,
                total_errors=len(summary.snapshot.errors),
                analysis_errors=summary.snapshot.errors,
            ),
        )


def process_pending_jobs(*, max_jobs: int | None = None) -> int:
    processed = 0
    while max_jobs is None or processed < max_jobs:
        with postgres_connection() as lock_conn:
            if not _try_acquire_worker_lock(lock_conn):
                break
            lock_conn.commit()
            try:
                with postgres_connection() as conn:
                    requeued_count = requeue_stale_running_jobs(conn, _stale_running_job_minutes())
                    if requeued_count:
                        print(f"[public-worker] requeued stale running jobs: {requeued_count}")
                    job = claim_next_job(conn)
                if job is None:
                    break
                try:
                    _process_job(job)
                except Exception as exc:
                    with postgres_connection() as conn:
                        mark_job_failed(conn, job.id, str(exc))
            finally:
                _release_worker_lock(lock_conn)
        processed += 1
    return processed


def enqueue_scheduled_crawl_job() -> str:
    dedupe_key = "scheduled_crawl:" + datetime.now(SHANGHAI_TZ).strftime("%Y%m%d%H%M")
    with postgres_connection() as conn:
        job_id = insert_scheduled_crawl_job(conn, dedupe_key)
    return job_id


def enqueue_scheduled_crawl() -> int:
    job_id = enqueue_scheduled_crawl_job()
    print(f"[public-worker] enqueued scheduled crawl job {job_id}")
    return 0


def _format_db_value(value: Any) -> str:
    if value is None:
        return "-"
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _verify_worker_database_connection() -> None:
    with postgres_connection() as conn:
        row = conn.execute("SELECT now() AS value").fetchone()
    print(f"[public-worker] database_ok db_now={_format_db_value(row['value'] if row else None)}")


def diagnose_worker_once() -> int:
    settings = load_settings()
    print(
        "[public-worker] doctor "
        f"crawl_times={','.join(_crawl_times())} "
        f"top_risk_sync_time={_top_risk_sync_time()} "
        f"poll={_poll_seconds()}s "
        f"stale_job_minutes={_stale_running_job_minutes()} "
        f"market_data_days={MARKET_DATA_WINDOW_DAYS} "
        f"light_market_data_days={_light_market_data_days()} "
        f"light_market_data_max={_light_market_data_max_securities()}"
    )
    print(
        "[public-worker] ai "
        f"provider={settings.provider} "
        f"model={settings.model} "
        f"api_key_configured={'yes' if settings.api_key else 'no'}"
    )

    try:
        with postgres_connection() as conn:
            db_now = conn.execute("SELECT now() AS value").fetchone()
            print(f"[public-worker] db_now={_format_db_value(db_now['value'] if db_now else None)}")

            account_row = conn.execute(
                """
                SELECT
                  count(*) FILTER (WHERE status = 'approved')::int AS approved_accounts,
                  count(*) FILTER (
                    WHERE status = 'approved' AND backfill_completed_at IS NULL
                  )::int AS approved_without_backfill
                FROM x_accounts
                """
            ).fetchone()
            subscription_row = conn.execute(
                """
                SELECT
                  count(DISTINCT s.account_id)::int AS subscribed_accounts,
                  count(DISTINCT a.id)::int AS approved_subscribed_accounts
                FROM user_subscriptions s
                LEFT JOIN x_accounts a ON a.id = s.account_id AND a.status = 'approved'
                """
            ).fetchone()
            print(
                "[public-worker] accounts "
                f"approved={account_row['approved_accounts'] if account_row else 0} "
                f"approved_without_backfill={account_row['approved_without_backfill'] if account_row else 0} "
                f"subscribed={subscription_row['subscribed_accounts'] if subscription_row else 0} "
                f"approved_subscribed={subscription_row['approved_subscribed_accounts'] if subscription_row else 0}"
            )

            count_rows = conn.execute(
                """
                SELECT kind, status, count(*)::int AS count
                FROM crawl_jobs
                GROUP BY kind, status
                ORDER BY kind, status
                """
            ).fetchall()
            if count_rows:
                for row in count_rows:
                    print(f"[public-worker] job_count kind={row['kind']} status={row['status']} count={row['count']}")
            else:
                print("[public-worker] job_count none")

            due_row = conn.execute(
                """
                SELECT
                  count(*)::int AS count,
                  min(run_after) AS oldest_run_after,
                  coalesce(
                    round((extract(epoch from (now() - min(run_after))) / 60)::numeric, 1),
                    0
                  ) AS oldest_due_minutes
                FROM crawl_jobs
                WHERE status = 'pending'
                  AND run_after <= now()
                """
            ).fetchone()
            running_row = conn.execute(
                """
                SELECT
                  count(*)::int AS count,
                  min(coalesce(locked_at, started_at, updated_at, created_at)) AS oldest_activity_at,
                  coalesce(
                    round(
                      (
                        extract(
                          epoch from (
                            now() - min(coalesce(locked_at, started_at, updated_at, created_at))
                          )
                        ) / 60
                      )::numeric,
                      1
                    ),
                    0
                  ) AS oldest_activity_minutes
                FROM crawl_jobs
                WHERE status = 'running'
                """
            ).fetchone()
            latest_scheduled = conn.execute(
                """
                SELECT status, created_at, run_after, finished_at
                FROM crawl_jobs
                WHERE kind = 'scheduled_crawl'
                ORDER BY created_at DESC
                LIMIT 1
                """
            ).fetchone()

            lock_row = conn.execute(
                "SELECT pg_try_advisory_lock(hashtext(%s)) AS locked",
                (WORKER_LOCK_KEY,),
            ).fetchone()
            lock_available = bool(lock_row and lock_row["locked"])
            if lock_available:
                _release_worker_lock(conn)
            print(
                "[public-worker] worker_lock "
                + ("available_now" if lock_available else "held_by_another_session")
            )
            print(
                "[public-worker] due_pending "
                f"count={due_row['count'] if due_row else 0} "
                f"oldest_run_after={_format_db_value(due_row['oldest_run_after'] if due_row else None)} "
                f"oldest_due_minutes={due_row['oldest_due_minutes'] if due_row else 0}"
            )
            print(
                "[public-worker] running "
                f"count={running_row['count'] if running_row else 0} "
                f"oldest_activity_at={_format_db_value(running_row['oldest_activity_at'] if running_row else None)} "
                f"oldest_activity_minutes={running_row['oldest_activity_minutes'] if running_row else 0}"
            )
            print(
                "[public-worker] latest_scheduled "
                f"status={latest_scheduled['status'] if latest_scheduled else '-'} "
                f"created_at={_format_db_value(latest_scheduled['created_at'] if latest_scheduled else None)} "
                f"run_after={_format_db_value(latest_scheduled['run_after'] if latest_scheduled else None)} "
                f"finished_at={_format_db_value(latest_scheduled['finished_at'] if latest_scheduled else None)}"
            )

            latest_jobs = conn.execute(
                """
                SELECT
                  id::text AS id,
                  kind,
                  status,
                  coalesce(account_id::text, '-') AS account_id,
                  created_at,
                  run_after,
                  started_at,
                  finished_at,
                  left(coalesce(nullif(error_text, ''), nullif(summary, ''), ''), 180) AS note
                FROM crawl_jobs
                ORDER BY created_at DESC
                LIMIT 10
                """
            ).fetchall()
            for row in latest_jobs:
                print(
                    "[public-worker] latest_job "
                    f"id={row['id']} "
                    f"kind={row['kind']} "
                    f"status={row['status']} "
                    f"account_id={row['account_id']} "
                    f"created_at={_format_db_value(row['created_at'])} "
                    f"run_after={_format_db_value(row['run_after'])} "
                    f"started_at={_format_db_value(row['started_at'])} "
                    f"finished_at={_format_db_value(row['finished_at'])} "
                    f"note={row['note'] or '-'}"
                )

            due_count = int(due_row["count"] if due_row else 0)
            running_count = int(running_row["count"] if running_row else 0)
            approved_subscribed = int(
                subscription_row["approved_subscribed_accounts"] if subscription_row else 0
            )
            running_minutes = float(running_row["oldest_activity_minutes"] if running_row else 0)
            stale_minutes = _stale_running_job_minutes()

            if approved_subscribed == 0:
                print("[public-worker] diagnosis no approved subscribed accounts for global crawls.")
            if running_count and running_minutes >= stale_minutes:
                print("[public-worker] diagnosis running job is stale and should be requeued on next poll.")
            if due_count:
                if lock_available:
                    print(
                        "[public-worker] diagnosis due jobs exist and no job holds the worker lock now; "
                        "if this repeats, the worker is likely not running or not polling."
                    )
                else:
                    print("[public-worker] diagnosis due jobs exist but another session holds the worker lock.")
            elif not running_count:
                print(
                    "[public-worker] diagnosis no due pending job right now; "
                    "if scheduled jobs are missing after a configured time, the long-running scheduler is not active."
                )
    except Exception as exc:
        print(f"[public-worker] doctor_error={exc}")
        return 1
    return 0


def refresh_market_data_once(
    *,
    security_keys: list[str] | None = None,
    query: str | None = None,
    limit: int | None = None,
    days: int | None = None,
    delay_seconds: float | None = None,
) -> int:
    safe_limit = max(
        1,
        min(
            int(
                limit
                if limit is not None
                else _env_int("PUBLIC_WORKER_MARKET_DATA_MAX_SECURITIES", 30)
            ),
            500,
        ),
    )
    requested_days = int(
        days
        if days is not None
        else _env_int("PUBLIC_WORKER_MARKET_DATA_DAYS", MARKET_DATA_WINDOW_DAYS)
    )
    safe_days = min(MARKET_DATA_WINDOW_DAYS, max(30, requested_days))
    safe_delay = max(
        0.0,
        float(
            delay_seconds
            if delay_seconds is not None
            else _env_float("PUBLIC_WORKER_MARKET_DATA_DELAY_SECONDS", 0.25)
        ),
    )

    with postgres_connection() as conn:
        store = PostgresInsightStore(conn)
        selected_keys = list(dict.fromkeys(security_keys or []))
        if not selected_keys:
            selected_keys = store.list_recent_security_keys(limit=safe_limit, query=query)
        print(
            "[public-worker] market_refresh "
            f"keys={','.join(selected_keys) if selected_keys else '-'} "
            f"limit={safe_limit} days={safe_days}"
        )
        if not selected_keys:
            print("[public-worker] no matching securities found")
            return 1
        written, errors = refresh_security_market_data(
            store=store,
            security_keys=selected_keys,
            max_securities=safe_limit,
            days=safe_days,
            delay_seconds=safe_delay,
        )

    print(f"[public-worker] market_prices={written} market_errors={len(errors)}")
    for error in errors[:10]:
        print(error)
    return 0 if written > 0 or not errors else 1


def _synthetic_crawl_results(notes: list[RawNoteRecord]) -> list[CrawlAccountResult]:
    account_map: dict[tuple[str, str], CrawlAccountResult] = {}
    run_at = now_iso()
    for note in notes:
        key = (note.platform, note.account_name)
        if key in account_map:
            continue
        account_map[key] = CrawlAccountResult(
            platform=note.platform,
            account_name=note.account_name,
            profile_url=note.profile_url,
            run_at=run_at,
            status="success",
            candidate_count=0,
            new_note_count=0,
            fetched_note_ids=[],
            error=None,
        )
    return sorted(account_map.values(), key=lambda item: (item.platform, item.account_name))


def rebuild_public_timelines_once() -> int:
    paths = get_paths()
    ensure_runtime_dirs(paths)
    with postgres_connection() as conn:
        store = PostgresInsightStore(conn)
        all_notes = store.list_all_content_items(platform="x")
        notes, start_date, end_date = _filter_recent_notes(
            all_notes,
            days=_analysis_window_days(),
        )
        if not notes:
            print(
                "[public-worker] no public X content found in analysis window "
                f"start={start_date} end={end_date}"
            )
            return 1
        summary = run_analysis_with_store(
            store=store,
            paths=paths,
            notes=notes,
            crawl_results=_synthetic_crawl_results(notes),
            crawl_errors=[],
        )

    print(
        "[public-worker] rebuilt_timelines "
        f"start={start_date} "
        f"end={end_date} "
        f"notes={len(notes)} "
        f"author_days={len(summary.snapshot.author_summaries)} "
        f"stock_days={len(summary.snapshot.stock_views)} "
        f"market_prices={summary.market_prices} "
        f"market_errors={len(summary.market_errors)}"
    )
    for error in summary.market_errors[:10]:
        print(error)
    return 1 if summary.exit_code else 0


def reanalyze_recent_public_content_once(*, days: int = 3, clear_analysis: bool = True) -> int:
    safe_days = max(1, int(days))
    paths = get_paths()
    ensure_runtime_dirs(paths)

    with postgres_connection() as conn:
        store = PostgresInsightStore(conn)
        all_notes = store.list_all_content_items(platform="x")
        notes, start_date, end_date = _filter_recent_notes(all_notes, days=safe_days)
        if not notes:
            if clear_analysis:
                store.clear_analysis_outputs()
            print(
                "[public-worker] no public X content in date window "
                f"start={start_date} end={end_date}"
            )
            return 1
        summary = run_analysis_with_store(
            store=store,
            paths=paths,
            notes=notes,
            crawl_results=_synthetic_crawl_results(notes),
            crawl_errors=[],
            force_reanalysis=True,
            clear_analysis_outputs=clear_analysis,
            market_data_days=_light_market_data_days(),
            market_data_max_securities=_light_market_data_max_securities(),
        )

    print(
        "[public-worker] reanalyzed_recent "
        f"start={start_date} "
        f"end={end_date} "
        f"notes={len(notes)} "
        f"reanalyzed_notes={len(summary.snapshot.note_extracts)} "
        f"author_days={len(summary.snapshot.author_summaries)} "
        f"stock_days={len(summary.snapshot.stock_views)} "
        f"market_prices={summary.market_prices} "
        f"market_errors={len(summary.market_errors)} "
        f"errors={len(summary.snapshot.errors)}"
    )
    for error in [*summary.snapshot.errors, *summary.market_errors][:10]:
        print(error)
    return 1 if summary.exit_code else 0


def run_worker(*, once: bool = False) -> int:
    if once:
        processed = process_pending_jobs(max_jobs=1)
        print(f"[public-worker] processed_jobs={processed}")
        return 0

    _verify_worker_database_connection()

    scheduler = BlockingScheduler(timezone=SHANGHAI_TZ)
    for value in _crawl_times():
        hour_text, minute_text = value.split(":", 1)
        scheduler.add_job(
            enqueue_scheduled_crawl_job,
            CronTrigger(hour=int(hour_text), minute=int(minute_text), timezone=SHANGHAI_TZ),
            id=f"public-x-{hour_text}{minute_text}",
            replace_existing=True,
        )
    scheduler.add_job(
        lambda: process_pending_jobs(max_jobs=None),
        "interval",
        seconds=_poll_seconds(),
        id="public-worker-poll",
        replace_existing=True,
    )
    top_risk_hour, top_risk_minute = _top_risk_sync_time().split(":", 1)
    scheduler.add_job(
        lambda: sync_market_top_risk_once(history_limit=_top_risk_history_limit()),
        CronTrigger(hour=int(top_risk_hour), minute=int(top_risk_minute), timezone=SHANGHAI_TZ),
        id="public-market-top-risk-sync",
        replace_existing=True,
    )
    print(
        "[public-worker] started. crawl_times="
        + ", ".join(_crawl_times())
        + f"; poll={_poll_seconds()}s; account_delay={_account_pause_seconds()}s"
        + f"; light_market_data_days={_light_market_data_days()}"
        + f"; light_market_data_max={_light_market_data_max_securities()}"
        + f"; top_risk_sync_time={_top_risk_sync_time()}"
    )
    scheduler.start()
    return 0
