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
    run_reanalyze_existing_job,
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
    subparsers.add_parser(
        "reanalyze-existing",
        help="Regenerate AI viewpoint extraction for all stored content.",
    )
    public_worker_parser = subparsers.add_parser(
        "public-worker",
        help="Run the public Supabase X worker for Alibaba Cloud.",
    )
    public_worker_parser.add_argument(
        "--once",
        action="store_true",
        help="Process at most one pending public crawl job, then exit.",
    )
    subparsers.add_parser(
        "public-enqueue-scheduled",
        help="Enqueue one scheduled public X crawl job in Supabase.",
    )
    subparsers.add_parser(
        "public-worker-doctor",
        help="Print public worker queue, account, lock, and recent-job diagnostics.",
    )
    subparsers.add_parser(
        "public-import-sqlite",
        help="Import local SQLite X data into the public Supabase database.",
    )
    subparsers.add_parser(
        "public-rebuild-timelines",
        help="Normalize public Supabase stock identities, rebuild timelines, and refresh market data.",
    )
    public_refresh_market_parser = subparsers.add_parser(
        "public-refresh-market-data",
        help="Refresh public Supabase stock daily-price cache without running a crawl.",
    )
    public_refresh_market_parser.add_argument(
        "--key",
        action="append",
        default=[],
        help="Security key to refresh. Can be passed multiple times, for example --key amd.",
    )
    public_refresh_market_parser.add_argument(
        "--query",
        help="Search security key, display name, ticker, market, or aliases before refreshing.",
    )
    public_refresh_market_parser.add_argument(
        "--limit",
        type=int,
        help="Maximum securities to refresh. Defaults to PUBLIC_WORKER_MARKET_DATA_MAX_SECURITIES.",
    )
    public_refresh_market_parser.add_argument(
        "--days",
        type=int,
        help="Daily candle history window. Defaults to PUBLIC_WORKER_MARKET_DATA_DAYS, capped at 180.",
    )
    public_refresh_market_parser.add_argument(
        "--delay-seconds",
        type=float,
        help="Delay between symbols. Defaults to PUBLIC_WORKER_MARKET_DATA_DELAY_SECONDS.",
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
    if args.command == "reanalyze-existing":
        return run_reanalyze_existing_job()
    if args.command == "public-worker":
        from packages.public_app.worker import run_worker  # noqa: PLC0415

        return run_worker(once=args.once)
    if args.command == "public-enqueue-scheduled":
        from packages.public_app.worker import enqueue_scheduled_crawl  # noqa: PLC0415

        return enqueue_scheduled_crawl()
    if args.command == "public-worker-doctor":
        from packages.public_app.worker import diagnose_worker_once  # noqa: PLC0415

        return diagnose_worker_once()
    if args.command == "public-import-sqlite":
        from packages.public_app.import_sqlite import import_sqlite_x_to_supabase  # noqa: PLC0415

        return import_sqlite_x_to_supabase()
    if args.command == "public-rebuild-timelines":
        from packages.public_app.worker import rebuild_public_timelines_once  # noqa: PLC0415

        return rebuild_public_timelines_once()
    if args.command == "public-refresh-market-data":
        from packages.public_app.worker import refresh_market_data_once  # noqa: PLC0415

        return refresh_market_data_once(
            security_keys=args.key,
            query=args.query,
            limit=args.limit,
            days=args.days,
            delay_seconds=args.delay_seconds,
        )
    raise ValueError(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
