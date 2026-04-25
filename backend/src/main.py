from __future__ import annotations

import argparse
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.jobs import (  # noqa: E402
    run_login,
    run_migration_job,
    run_normalize_securities_job,
    run_once_job,
    run_once_x_job,
)
from src.scheduler import start_scheduler  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phase 1 Xiaohongshu + AI backend runner."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    def _add_config_argument(command_parser: argparse.ArgumentParser) -> None:
        command_parser.add_argument(
            "--config",
            help="Path to watchlist.json. Defaults to data/config/watchlist.json.",
        )

    login_parser = subparsers.add_parser("login", help="Save login state and validate it.")
    _add_config_argument(login_parser)

    run_once_parser = subparsers.add_parser(
        "run-once",
        help="Crawl once, analyze, and materialize timelines.",
    )
    _add_config_argument(run_once_parser)

    run_once_x_parser = subparsers.add_parser(
        "run-once-x",
        help="Crawl X accounts once, analyze viewpoints, and materialize timelines.",
    )
    _add_config_argument(run_once_x_parser)

    scheduler_parser = subparsers.add_parser(
        "run-scheduler",
        help="Run the configured daily scheduler from data/config/runtime_settings.json.",
    )
    _add_config_argument(scheduler_parser)
    subparsers.add_parser(
        "migrate-json-to-sqlite",
        help="Import legacy local JSON and JSONL data into SQLite.",
    )
    subparsers.add_parser(
        "normalize-securities",
        help="Normalize stored stock identities and rebuild materialized timelines.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "login":
        return run_login(args.config)
    if args.command == "run-once":
        return run_once_job(args.config)
    if args.command == "run-once-x":
        return run_once_x_job(args.config)
    if args.command == "run-scheduler":
        return start_scheduler(args.config)
    if args.command == "migrate-json-to-sqlite":
        return run_migration_job()
    if args.command == "normalize-securities":
        return run_normalize_securities_job()
    raise ValueError(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
