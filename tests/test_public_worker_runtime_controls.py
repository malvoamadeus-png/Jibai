from __future__ import annotations

from contextlib import contextmanager

from packages.public_app.crypto_asset_narrative import generate_crypto_asset_briefs_once
from packages.public_app.jobs import CrawlJob
from packages.public_app.worker import enqueue_scheduled_crawl_job, process_pending_jobs


def test_enqueue_scheduled_crawl_job_skips_disabled_crypto(monkeypatch) -> None:
    monkeypatch.setattr("packages.public_app.worker._domain_pipeline_enabled", lambda _domain: False)
    monkeypatch.setattr(
        "packages.public_app.worker.insert_scheduled_crawl_job",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not enqueue")),
    )

    assert enqueue_scheduled_crawl_job("crypto") is None


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
