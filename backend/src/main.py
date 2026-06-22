from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent
load_dotenv(ROOT_DIR / ".env", override=False)
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.jobs import (  # noqa: E402
    run_export_daily_author_viewpoints_job,
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
    export_daily_parser = subparsers.add_parser(
        "export-daily-author-viewpoints",
        help="Export one day of author stock viewpoints to CSV for content production.",
    )
    export_daily_parser.add_argument(
        "--date",
        help="Date in YYYY-MM-DD. Defaults to the latest date that has exportable stock viewpoints.",
    )
    export_daily_parser.add_argument(
        "--platform",
        help="Optional platform filter, for example x or xiaohongshu.",
    )
    export_daily_parser.add_argument(
        "--output",
        help="Optional output .csv path. Defaults to data/runtime/exports/daily-author-viewpoints-<date>.csv.",
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
    public_api_parser = subparsers.add_parser(
        "public-api",
        help="Run the public HTTP API service.",
    )
    public_api_parser.add_argument("--host", default="127.0.0.1", help="Bind host. Defaults to 127.0.0.1.")
    public_api_parser.add_argument("--port", type=int, default=8010, help="Bind port. Defaults to 8010.")
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
    public_rebuild_parser = subparsers.add_parser(
        "public-rebuild-timelines",
        help="Rebuild public Supabase timelines for stock or crypto.",
    )
    public_rebuild_parser.add_argument(
        "--domain",
        choices=("stock", "crypto"),
        default="stock",
        help="Analysis domain to rebuild. Defaults to stock.",
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
    public_reanalyze_recent_parser = subparsers.add_parser(
        "public-reanalyze-recent",
        help="Clear public analysis outputs and force reanalysis for recent Shanghai natural days.",
    )
    public_reanalyze_recent_parser.add_argument(
        "--days",
        type=int,
        default=3,
        help="Number of Shanghai natural days to reanalyze, including today. Defaults to 3.",
    )
    public_reanalyze_recent_parser.add_argument(
        "--domain",
        choices=("stock", "crypto"),
        default="stock",
        help="Analysis domain to reanalyze. Defaults to stock.",
    )
    public_reanalyze_recent_parser.add_argument(
        "--clear-analysis",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Clear existing public analysis and materialized timeline outputs before reanalysis.",
    )
    normalize_crypto_parser = subparsers.add_parser(
        "normalize-crypto-assets",
        help="Rebuild crypto asset materialized timelines from existing crypto analyses.",
    )
    normalize_crypto_parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Recent Shanghai natural days to rebuild. Defaults to 30.",
    )
    public_market_top_risk_parser = subparsers.add_parser(
        "public-sync-market-top-risk",
        help="Fetch public market data, compute US top-risk snapshots, and sync them to Supabase.",
    )
    public_market_top_risk_parser.add_argument(
        "--history-limit",
        type=int,
        default=90,
        help="Number of recent weekly snapshots to upsert. Defaults to 90.",
    )
    public_stock_narrative_parser = subparsers.add_parser(
        "public-generate-stock-narrative",
        help="Generate the public stock narrative brief from approved stock accounts.",
    )
    public_stock_narrative_parser.add_argument(
        "--date",
        help="Brief date in YYYY-MM-DD. Defaults to the latest available stock viewpoint date.",
    )
    public_stock_narrative_parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate even if a successful brief already exists for the date.",
    )
    public_stock_blogger_parser = subparsers.add_parser(
        "public-rebuild-stock-blogger-scores",
        help="Rebuild public stock blogger gold ranking scores.",
    )
    public_stock_blogger_parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="Recent Shanghai natural days to score. Defaults to 90.",
    )
    public_stock_blogger_parser.add_argument(
        "--no-refresh-market",
        action="store_true",
        help="Use existing market-data cache without refreshing stock or benchmark candles.",
    )
    public_stock_news_tracking_parser = subparsers.add_parser(
        "public-analyze-stock-news-tracking",
        help="Analyze pending tracked stock news events.",
    )
    public_stock_news_tracking_parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum pending tracked news events to analyze. Defaults to 5.",
    )
    public_stock_news_tracking_prices_parser = subparsers.add_parser(
        "public-refresh-stock-news-tracking-prices",
        help="Refresh prices and returns for tracked stock news mappings.",
    )
    public_stock_news_tracking_prices_parser.add_argument(
        "--delay-seconds",
        type=float,
        default=0.25,
        help="Delay between symbols. Defaults to 0.25.",
    )
    subparsers.add_parser(
        "public-ensure-stock-blogger-accounts",
        help="Ensure default stock blogger score accounts exist and are approved for stock.",
    )
    public_crypto_asset_brief_parser = subparsers.add_parser(
        "public-generate-crypto-asset-briefs",
        help="Generate crypto asset narrative briefs for recent visible assets.",
    )
    public_crypto_asset_brief_parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Recent Shanghai natural days to scan for assets. Defaults to 30.",
    )
    public_crypto_asset_brief_parser.add_argument(
        "--limit",
        type=int,
        help="Maximum assets to process in this run.",
    )
    public_crypto_asset_brief_parser.add_argument(
        "--asset-key",
        action="append",
        default=[],
        help="Asset key to process. Can be passed multiple times.",
    )
    public_crypto_asset_brief_parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate even if a successful brief already exists for the asset.",
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
    if args.command == "export-daily-author-viewpoints":
        return run_export_daily_author_viewpoints_job(
            date_key=args.date,
            output_path=args.output,
            platform=args.platform,
        )
    if args.command == "public-worker":
        from packages.public_app.worker import run_worker  # noqa: PLC0415

        return run_worker(once=args.once)
    if args.command == "public-api":
        import uvicorn  # noqa: PLC0415

        uvicorn.run("packages.public_app.api:create_app", factory=True, host=args.host, port=args.port)
        return 0
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

        return rebuild_public_timelines_once(domain=args.domain)
    if args.command == "public-refresh-market-data":
        from packages.public_app.worker import refresh_market_data_once  # noqa: PLC0415

        return refresh_market_data_once(
            security_keys=args.key,
            query=args.query,
            limit=args.limit,
            days=args.days,
            delay_seconds=args.delay_seconds,
        )
    if args.command == "public-reanalyze-recent":
        from packages.public_app.worker import reanalyze_recent_public_content_once  # noqa: PLC0415

        return reanalyze_recent_public_content_once(
            days=args.days,
            clear_analysis=args.clear_analysis,
            domain=args.domain,
        )
    if args.command == "normalize-crypto-assets":
        from packages.public_app.worker import rebuild_public_timelines_once  # noqa: PLC0415

        return rebuild_public_timelines_once(domain="crypto", days=args.days)
    if args.command == "public-sync-market-top-risk":
        from packages.public_app.market_top_risk import sync_market_top_risk_once  # noqa: PLC0415

        return sync_market_top_risk_once(history_limit=args.history_limit)
    if args.command == "public-generate-stock-narrative":
        from packages.public_app.stock_narrative import generate_stock_narrative_once  # noqa: PLC0415

        return generate_stock_narrative_once(brief_date=args.date, force=args.force)
    if args.command == "public-rebuild-stock-blogger-scores":
        from packages.public_app.stock_blogger_scoring import rebuild_stock_blogger_scores_once  # noqa: PLC0415

        return rebuild_stock_blogger_scores_once(days=args.days, refresh_market=not args.no_refresh_market)
    if args.command == "public-ensure-stock-blogger-accounts":
        from packages.public_app.stock_blogger_scoring import ensure_stock_blogger_accounts_once  # noqa: PLC0415

        return ensure_stock_blogger_accounts_once()
    if args.command == "public-analyze-stock-news-tracking":
        from packages.public_app.stock_news_tracking import analyze_pending_stock_news_tracking_once  # noqa: PLC0415

        return analyze_pending_stock_news_tracking_once(limit=args.limit)
    if args.command == "public-refresh-stock-news-tracking-prices":
        from packages.public_app.stock_news_tracking import refresh_stock_news_tracking_prices_once  # noqa: PLC0415

        return refresh_stock_news_tracking_prices_once(delay_seconds=args.delay_seconds)
    if args.command == "public-generate-crypto-asset-briefs":
        from packages.public_app.crypto_asset_narrative import generate_crypto_asset_briefs_once  # noqa: PLC0415

        return generate_crypto_asset_briefs_once(
            days=args.days,
            limit=args.limit,
            asset_keys=args.asset_key,
            force=args.force,
        )
    raise ValueError(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
