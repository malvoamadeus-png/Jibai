from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb


@dataclass(slots=True)
class PublicXAccount:
    id: str
    username: str
    display_name: str
    profile_url: str


@dataclass(slots=True)
class CrawlJob:
    id: str
    kind: str
    account_id: str | None


def enqueue_scheduled_crawl(conn: Connection[dict[str, Any]], dedupe_key: str) -> str:
    row = conn.execute(
        """
        INSERT INTO crawl_jobs (kind, status, dedupe_key, metadata_json)
        VALUES ('scheduled_crawl', 'pending', %s, %s)
        ON CONFLICT(dedupe_key) DO UPDATE SET updated_at = crawl_jobs.updated_at
        RETURNING id
        """,
        (dedupe_key, Jsonb({"source": "worker-scheduler"})),
    ).fetchone()
    if row is None:
        raise RuntimeError("Failed to enqueue scheduled crawl.")
    return str(row["id"])


def claim_next_job(conn: Connection[dict[str, Any]]) -> CrawlJob | None:
    row = conn.execute(
        """
        UPDATE crawl_jobs
        SET status = 'running',
            locked_at = now(),
            started_at = now(),
            updated_at = now()
        WHERE id = (
          SELECT id
          FROM crawl_jobs
          WHERE status = 'pending'
            AND run_after <= now()
          ORDER BY run_after ASC, created_at ASC
          LIMIT 1
          FOR UPDATE SKIP LOCKED
        )
        RETURNING id, kind, account_id
        """
    ).fetchone()
    if row is None:
        return None
    return CrawlJob(id=str(row["id"]), kind=str(row["kind"]), account_id=None if row["account_id"] is None else str(row["account_id"]))


def mark_job_succeeded(conn: Connection[dict[str, Any]], job_id: str, summary: str) -> None:
    conn.execute(
        """
        UPDATE crawl_jobs
        SET status = 'succeeded',
            finished_at = now(),
            summary = %s,
            error_text = NULL,
            updated_at = now()
        WHERE id = %s
        """,
        (summary, job_id),
    )


def mark_job_failed(conn: Connection[dict[str, Any]], job_id: str, error_text: str) -> None:
    conn.execute(
        """
        UPDATE crawl_jobs
        SET status = 'failed',
            finished_at = now(),
            error_text = %s,
            updated_at = now()
        WHERE id = %s
        """,
        (error_text[:4000], job_id),
    )


def mark_backfill_completed(conn: Connection[dict[str, Any]], account_id: str) -> None:
    conn.execute(
        """
        UPDATE x_accounts
        SET backfill_completed_at = COALESCE(backfill_completed_at, now()),
            updated_at = now()
        WHERE id = %s
        """,
        (account_id,),
    )


def list_accounts_for_job(conn: Connection[dict[str, Any]], job: CrawlJob) -> list[PublicXAccount]:
    if job.account_id:
        rows = conn.execute(
            """
            SELECT id, username, display_name, profile_url
            FROM x_accounts
            WHERE id = %s
              AND status = 'approved'
            LIMIT 1
            """,
            (job.account_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT a.id, a.username, a.display_name, a.profile_url
            FROM x_accounts a
            WHERE a.status = 'approved'
              AND EXISTS (
                SELECT 1
                FROM user_subscriptions s
                WHERE s.account_id = a.id
              )
            ORDER BY a.approved_at NULLS LAST, a.created_at ASC
            LIMIT 100
            """
        ).fetchall()
    return [
        PublicXAccount(
            id=str(row["id"]),
            username=str(row["username"]),
            display_name=str(row["display_name"] or row["username"]),
            profile_url=str(row["profile_url"] or f"https://x.com/{row['username']}"),
        )
        for row in rows
    ]


def list_seen_note_ids(conn: Connection[dict[str, Any]], account_id: str) -> set[str]:
    rows = conn.execute(
        """
        SELECT external_content_id
        FROM content_items
        WHERE account_id = %s
          AND platform = 'x'
        """,
        (account_id,),
    ).fetchall()
    return {str(row["external_content_id"]) for row in rows}
