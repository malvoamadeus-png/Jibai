from __future__ import annotations

import sys

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

    def _run_job() -> None:
        xhs_exit_code = run_once_job(config_path)
        x_exit_code = run_once_x_job(None)
        print(
            f"[scheduler] run finished with exit codes xhs={xhs_exit_code} x={x_exit_code}",
            file=sys.stderr,
        )

    for schedule_time in settings.schedule_times:
        hour_text, minute_text = schedule_time.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
        scheduler.add_job(
            _run_job,
            CronTrigger(hour=hour, minute=minute, timezone=SHANGHAI_TZ),
            id=f"xhs-ai-{hour:02d}{minute:02d}",
            replace_existing=True,
        )

    print(
        "[scheduler] started. Jobs will run every day at "
        + ", ".join(settings.schedule_times)
        + " Asia/Shanghai.",
        file=sys.stderr,
    )
    scheduler.start()
    return 0
