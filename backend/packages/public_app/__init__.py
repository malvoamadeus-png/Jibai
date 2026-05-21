from __future__ import annotations

from typing import Any

__all__ = ["enqueue_scheduled_crawl", "run_worker"]


def enqueue_scheduled_crawl(*args: Any, **kwargs: Any) -> Any:
    from .worker import enqueue_scheduled_crawl as _enqueue_scheduled_crawl

    return _enqueue_scheduled_crawl(*args, **kwargs)


def run_worker(*args: Any, **kwargs: Any) -> Any:
    from .worker import run_worker as _run_worker

    return _run_worker(*args, **kwargs)
