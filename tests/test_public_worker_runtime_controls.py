from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime

from packages.public_app.crypto_asset_narrative import generate_crypto_asset_briefs_once
from packages.public_app.jobs import CrawlJob, PublicXAccount, _stock_blogger_score_accounts
from packages.public_app.worker import (
    _account_timeout_seconds,
    _crawl_times,
    _timeout_result,
    enqueue_scheduled_crawl_job,
    process_pending_jobs,
)


def test_enqueue_scheduled_crawl_job_skips_disabled_crypto(monkeypatch) -> None:
    monkeypatch.setattr("packages.public_app.worker._domain_pipeline_enabled", lambda _domain: False)
    monkeypatch.setattr(
        "packages.public_app.worker.insert_scheduled_crawl_job",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not enqueue")),
    )

    assert enqueue_scheduled_crawl_job("crypto") is None


def test_default_crawl_times_are_hourly(monkeypatch) -> None:
    monkeypatch.delenv("PUBLIC_WORKER_CRAWL_TIMES", raising=False)

    assert _crawl_times() == [f"{hour:02d}:00" for hour in range(24)]


def test_scheduled_crawl_dedupes_same_domain_minute(monkeypatch) -> None:
    class FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return cls(2026, 6, 10, 8, 0, 12, tzinfo=tz)

    class FakeConn:
        pass

    inserted: list[tuple[str, str]] = []

    @contextmanager
    def fake_postgres_connection():
        yield FakeConn()

    def fake_insert(_conn, dedupe_key: str, *, domain: str) -> str:
        inserted.append((dedupe_key, domain))
        return f"job-{len(inserted)}"

    monkeypatch.setattr("packages.public_app.worker.datetime", FakeDateTime)
    monkeypatch.setattr("packages.public_app.worker.postgres_connection", fake_postgres_connection)
    monkeypatch.setattr("packages.public_app.worker.insert_scheduled_crawl_job", fake_insert)

    assert enqueue_scheduled_crawl_job("stock") == "job-1"
    assert enqueue_scheduled_crawl_job("stock") == "job-2"
    assert inserted == [
        ("scheduled_crawl:stock:202606100800", "stock"),
        ("scheduled_crawl:stock:202606100800", "stock"),
    ]


def test_stock_blogger_score_accounts_are_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("PUBLIC_STOCK_BLOGGER_SCORE_ENABLED", raising=False)
    monkeypatch.setenv("PUBLIC_STOCK_BLOGGER_SCORE_ACCOUNTS", "labubu_trader,hicagr,xiaomustock")

    assert _stock_blogger_score_accounts() == []

    monkeypatch.setenv("PUBLIC_STOCK_BLOGGER_SCORE_ENABLED", "true")

    assert _stock_blogger_score_accounts() == ["labubu_trader", "hicagr", "xiaomustock"]


def test_account_timeout_seconds_use_job_specific_defaults(monkeypatch) -> None:
    monkeypatch.delenv("PUBLIC_WORKER_ACCOUNT_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("PUBLIC_WORKER_BACKFILL_ACCOUNT_TIMEOUT_SECONDS", raising=False)

    assert _account_timeout_seconds("scheduled_crawl") == 180
    assert _account_timeout_seconds("initial_backfill") == 600

    monkeypatch.setenv("PUBLIC_WORKER_ACCOUNT_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("PUBLIC_WORKER_BACKFILL_ACCOUNT_TIMEOUT_SECONDS", "90")

    assert _account_timeout_seconds("manual_crawl") == 45
    assert _account_timeout_seconds("initial_backfill") == 90


def test_timeout_result_marks_account_failed() -> None:
    result = _timeout_result(
        account=PublicXAccount(
            id="account-1",
            username="stuck_account",
            display_name="Stuck Account",
            profile_url="https://x.com/stuck_account",
        ),
        run_at="2026-06-08T20:00:00+08:00",
        timeout_seconds=30,
    )

    assert result.status == "failed"
    assert result.account_name == "stuck_account"
    assert result.error is not None
    assert "X_ACCOUNT_TIMEOUT" in result.error


def test_process_pending_jobs_marks_disabled_crypto_job_skipped(monkeypatch) -> None:
    class FakeConn:
        def commit(self) -> None:
            return None

    connections = iter([FakeConn(), FakeConn(), FakeConn()])
    skipped: list[tuple[str, str]] = []

    @contextmanager
    def fake_postgres_connection():
        yield next(connections)

    monkeypatch.setattr("packages.public_app.worker.postgres_connection", fake_postgres_connection)
    monkeypatch.setattr("packages.public_app.worker._try_acquire_worker_lock", lambda _conn: True)
    monkeypatch.setattr("packages.public_app.worker._release_worker_lock", lambda _conn: None)
    monkeypatch.setattr("packages.public_app.worker.requeue_stale_running_jobs", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(
        "packages.public_app.worker.claim_next_job",
        lambda _conn: CrawlJob(id="job-1", kind="manual_crawl", account_id=None, domain="crypto"),
    )
    monkeypatch.setattr("packages.public_app.worker._domain_pipeline_enabled", lambda _domain: False)
    monkeypatch.setattr(
        "packages.public_app.worker.mark_job_succeeded",
        lambda _conn, job_id, summary: skipped.append((job_id, summary)),
    )
    monkeypatch.setattr(
        "packages.public_app.worker._process_job",
        lambda _job: (_ for _ in ()).throw(AssertionError("disabled crypto job should not execute")),
    )

    assert process_pending_jobs(max_jobs=1) == 1
    assert skipped == [("job-1", "加密板块已关闭，任务已跳过。")]


def test_generate_crypto_asset_briefs_once_skips_when_pipeline_disabled(monkeypatch) -> None:
    class FakeConn:
        pass

    @contextmanager
    def fake_postgres_connection():
        yield FakeConn()

    monkeypatch.setattr(
        "packages.public_app.crypto_asset_narrative.postgres_connection",
        fake_postgres_connection,
    )
    monkeypatch.setattr(
        "packages.public_app.crypto_asset_narrative.is_domain_pipeline_enabled",
        lambda _conn, _domain: False,
    )
    monkeypatch.setattr(
        "packages.public_app.crypto_asset_narrative._model_settings",
        lambda: (_ for _ in ()).throw(AssertionError("disabled crypto brief should skip before loading model settings")),
    )

    assert generate_crypto_asset_briefs_once(force=True) == 0
