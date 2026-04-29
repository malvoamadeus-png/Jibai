from __future__ import annotations

import sys
from collections.abc import Callable
from threading import Lock

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from packages.common.paths import get_paths
from packages.common.runtime_settings import load_runtime_settings
from packages.common.time_utils import SHANGHAI_TZ

from .jobs import run_once_job, run_once_x_job


def start_scheduler(config_path: str | None) -> int:
    scheduler = BlockingScheduler(timezone=SHANGHAI_TZ)
    paths = get_paths()
    settings = load_runtime_settings(paths.runtime_settings_path)
    job_lock = Lock()

    def _run_xhs_job() -> None:
        with job_lock:
            exit_code = run_once_job(config_path)
        print(
            f"[scheduler] xiaohongshu run finished with exit code {exit_code}",
            file=sys.stderr,
        )

    def _run_x_job() -> None:
        with job_lock:
            exit_code = run_once_x_job(None)
        print(
            f"[scheduler] x run finished with exit code {exit_code}",
            file=sys.stderr,
        )

    def _add_daily_jobs(
        *,
        platform_id: str,
        schedule_times: list[str],
        job_func: Callable[[], None],
    ) -> None:
        for schedule_time in schedule_times:
            hour_text, minute_text = schedule_time.split(":", 1)
            hour = int(hour_text)
            minute = int(minute_text)
            scheduler.add_job(
                job_func,
                CronTrigger(hour=hour, minute=minute, timezone=SHANGHAI_TZ),
                id=f"{platform_id}-{hour:02d}{minute:02d}",
                replace_existing=True,
            )

    _add_daily_jobs(
        platform_id="xiaohongshu",
        schedule_times=settings.xiaohongshu_schedule_times,
        job_func=_run_xhs_job,
    )
    _add_daily_jobs(
        platform_id="x",
        schedule_times=settings.x_schedule_times,
        job_func=_run_x_job,
    )

    print(
        "[scheduler] started. Xiaohongshu jobs: "
        + ", ".join(settings.xiaohongshu_schedule_times)
        + "; X jobs: "
        + ", ".join(settings.x_schedule_times)
        + " Asia/Shanghai.",
        file=sys.stderr,
    )
    scheduler.start()
    return 0
