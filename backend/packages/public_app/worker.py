from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from packages.ai.pipeline import run_analysis_with_store
from packages.common.paths import ensure_runtime_dirs, get_paths
from packages.common.postgres_database import PostgresInsightStore, postgres_connection
from packages.common.time_utils import SHANGHAI_TZ, now_iso
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
)


DEFAULT_CRAWL_TIMES = ("04:00", "10:00", "16:00", "22:00")
WORKER_LOCK_KEY = "jibai_public_x_worker"


def _crawl_times() -> list[str]:
    raw = os.getenv("PUBLIC_WORKER_CRAWL_TIMES", ",".join(DEFAULT_CRAWL_TIMES))
    values = [item.strip() for item in raw.split(",") if item.strip()]
    return values or list(DEFAULT_CRAWL_TIMES)


def _poll_seconds() -> int:
    return max(5, int(os.getenv("PUBLIC_WORKER_POLL_SECONDS", "30")))


def _account_pause_seconds() -> float:
    return max(0.0, float(os.getenv("PUBLIC_WORKER_ACCOUNT_DELAY_SECONDS", "5")))


def _try_acquire_worker_lock(conn: Any) -> bool:
    row = conn.execute("SELECT pg_try_advisory_lock(hashtext(%s)) AS locked", (WORKER_LOCK_KEY,)).fetchone()
    return bool(row and row["locked"])


def _release_worker_lock(conn: Any) -> None:
    conn.execute("SELECT pg_advisory_unlock(hashtext(%s))", (WORKER_LOCK_KEY,))


def _base_x_config(accounts: list[AccountTarget]) -> WatchlistConfig:
    return WatchlistConfig(
        enabled=bool(accounts),
        headless=os.getenv("PUBLIC_WORKER_HEADLESS", "true").lower() != "false",
        page_wait_sec=float(os.getenv("PUBLIC_WORKER_PAGE_WAIT_SECONDS", "6")),
        inter_account_delay_sec=_account_pause_seconds(),
        inter_account_delay_jitter_sec=0,
        exclude_old_posts=True,
        max_post_age_days=5,
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
            if result.error:
                crawl_errors.append(f"[x {account.username}] {result.error}")
            if job.kind == "initial_backfill" and result.status == "success":
                mark_backfill_completed(conn, account.id)
            if index < len(accounts) - 1:
                time.sleep(_account_pause_seconds())

        notes = store.list_all_content_items(platform="x")
        summary = run_analysis_with_store(
            store=store,
            paths=paths,
            notes=notes,
            crawl_results=crawl_results,
            crawl_errors=crawl_errors,
        )
        mark_job_succeeded(
            conn,
            job.id,
            (
                f"accounts={len(accounts)} new_notes={total_new_notes} "
                f"crawl_errors={len(crawl_errors)} "
                f"total_errors={len(summary.snapshot.errors)}"
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


def run_worker(*, once: bool = False) -> int:
    if once:
        processed = process_pending_jobs(max_jobs=1)
        print(f"[public-worker] processed_jobs={processed}")
        return 0

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
    print(
        "[public-worker] started. crawl_times="
        + ", ".join(_crawl_times())
        + f"; poll={_poll_seconds()}s; account_delay={_account_pause_seconds()}s"
    )
    scheduler.start()
    return 0
