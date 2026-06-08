from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from .ai_extract import extract_mentions
    from .config import dump_example_config, load_config, normalize_account
    from .fetcher import fetch_posts, validate_username
    from .io import read_jsonl, to_jsonable, write_json, write_jsonl
    from .market import normalize_mentions, score_events
    from .models import BloggerPost, ScoringConfig, ScoringRunResult, StockSignalMention
    from .report import write_excel, write_html
    from .scoring import aggregate_author_scores, aggregate_stock_author_scores, build_signal_events
except ImportError:
    from tools.stock_blogger_scoring.ai_extract import extract_mentions
    from tools.stock_blogger_scoring.config import dump_example_config, load_config, normalize_account
    from tools.stock_blogger_scoring.fetcher import fetch_posts, validate_username
    from tools.stock_blogger_scoring.io import read_jsonl, to_jsonable, write_json, write_jsonl
    from tools.stock_blogger_scoring.market import normalize_mentions, score_events
    from tools.stock_blogger_scoring.models import BloggerPost, ScoringConfig, ScoringRunResult, StockSignalMention
    from tools.stock_blogger_scoring.report import write_excel, write_html
    from tools.stock_blogger_scoring.scoring import aggregate_author_scores, aggregate_stock_author_scores, build_signal_events


DEFAULT_MODEL = "gpt-5.4-mini"


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _posts_from_jsonl(path: Path) -> list[BloggerPost]:
    return [BloggerPost(**row) for row in read_jsonl(path)]


def _mentions_from_jsonl(path: Path) -> list[StockSignalMention]:
    return [StockSignalMention(**row) for row in read_jsonl(path)]


def _run_dir(base: Path, config: ScoringConfig, start_date: date, end_date: date) -> Path:
    account_slug = "-".join(account.lower() for account in config.accounts[:4])
    return base / f"{start_date.isoformat()}_{end_date.isoformat()}_{account_slug}"


def _config_from_args(args: argparse.Namespace) -> ScoringConfig:
    config = load_config(Path(args.config) if args.config else None)
    accounts = [normalize_account(item) for item in args.accounts] if args.accounts else config.accounts
    overrides: dict[str, Any] = {
        "accounts": [validate_username(item) for item in accounts],
    }
    if args.days is not None:
        overrides["history_days"] = int(args.days)
    if args.price_days is not None:
        overrides["price_days"] = int(args.price_days)
    return replace(config, **overrides)


def _flatten_forward_returns(result: ScoringRunResult) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in result.events:
        for label, horizon_score in event.horizon_scores.items():
            rows.append(
                {
                    "event_id": event.event_id,
                    "author": event.author,
                    "security_key": event.security_key,
                    "display_name": event.display_name,
                    "direction": event.direction,
                    "horizon": label,
                    "status": horizon_score.status,
                    "anchor_trading_day": event.anchor_trading_day,
                    "anchor_price": event.anchor_price,
                    "anchor_price_kind": event.anchor_price_kind,
                    "target_date": horizon_score.target_date,
                    "target_price": horizon_score.target_price,
                    "benchmark_symbol": event.benchmark_symbol,
                    "benchmark_anchor_price": event.benchmark_anchor_price,
                    "benchmark_target_price": horizon_score.benchmark_target_price,
                    "stock_return": horizon_score.stock_return,
                    "benchmark_return": horizon_score.benchmark_return,
                    "excess_return": horizon_score.excess_return,
                    "directional_excess": horizon_score.directional_excess,
                    "score": horizon_score.score,
                    "message": horizon_score.message,
                }
            )
    return rows


def run(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    end_date = _parse_date(args.end) if args.end else date.today()
    start_date = _parse_date(args.start) if args.start else end_date - timedelta(days=config.history_days - 1)
    output_root = Path(args.output_dir) if args.output_dir else ROOT / "data" / "runtime" / "stock_blogger_scoring"
    run_dir = _run_dir(output_root, config, start_date, end_date)
    run_dir.mkdir(parents=True, exist_ok=True)

    all_posts: list[BloggerPost] = []
    raw_status_count = 0
    fetch_summary: dict[str, Any] = {}
    for account in config.accounts:
        posts_path = run_dir / f"posts_{account}.jsonl"
        raw_path = run_dir / f"raw_statuses_{account}.jsonl"
        existing_posts = _posts_from_jsonl(posts_path) if args.resume and posts_path.exists() else []
        posts, raw_statuses, summary = fetch_posts(
            username=account,
            start_date=start_date,
            end_date=end_date,
            max_pages=int(args.max_pages),
            existing_posts=existing_posts,
        )
        write_jsonl(posts_path, posts)
        write_jsonl(raw_path, raw_statuses)
        all_posts.extend(posts)
        raw_status_count += len(raw_statuses)
        fetch_summary[account] = summary
        print(f"[stock-blogger-scoring] fetched @{account} posts={len(posts)} pages={summary.get('pages_fetched')} reason={summary.get('stopped_reason')}")

    all_posts.sort(key=lambda item: (item.author.casefold(), item.published_at, item.tweet_id))
    posts_path = run_dir / "normalized_posts.jsonl"
    mentions_path = run_dir / "stock_signal_mentions.jsonl"
    events_path = run_dir / "signal_events.jsonl"
    returns_path = run_dir / "forward_returns.jsonl"
    author_scores_path = run_dir / "author_scores.json"
    stock_author_scores_path = run_dir / "stock_author_scores.json"
    manifest_path = run_dir / "manifest.json"
    html_path = run_dir / "report.html"
    excel_path = run_dir / "audit.xlsx"
    write_jsonl(posts_path, all_posts)

    if args.skip_ai:
        mentions = _mentions_from_jsonl(mentions_path) if mentions_path.exists() else []
    elif args.resume and mentions_path.exists():
        mentions = _mentions_from_jsonl(mentions_path)
    else:
        mentions = extract_mentions(all_posts, model=args.model)
        write_jsonl(mentions_path, mentions)

    mentions = normalize_mentions(mentions)
    write_jsonl(mentions_path, mentions)
    events = build_signal_events(mentions)
    events, market_summary = score_events(events, config=config, skip_market=bool(args.skip_market))
    author_scores = aggregate_author_scores(events, config)
    stock_author_scores = aggregate_stock_author_scores(events, config)

    manifest = {
        "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "model": args.model,
        "skip_ai": bool(args.skip_ai),
        "skip_market": bool(args.skip_market),
        "config": to_jsonable(config),
        "fetch": fetch_summary,
        "raw_status_count": raw_status_count,
        "post_count": len(all_posts),
        "mention_count": len(mentions),
        "event_count": len(events),
        "author_score_count": len(author_scores),
        "market": market_summary,
        "outputs": {
            "normalized_posts": str(posts_path),
            "mentions": str(mentions_path),
            "events": str(events_path),
            "forward_returns": str(returns_path),
            "author_scores": str(author_scores_path),
            "stock_author_scores": str(stock_author_scores_path),
            "html": str(html_path),
            "excel": str(excel_path),
        },
    }

    result = ScoringRunResult(
        run_dir=str(run_dir),
        started_at=datetime.now().astimezone(),
        start_date=start_date,
        end_date=end_date,
        config=config,
        posts=all_posts,
        mentions=mentions,
        events=events,
        author_scores=author_scores,
        stock_author_scores=stock_author_scores,
        manifest=manifest,
    )
    write_jsonl(events_path, events)
    write_jsonl(returns_path, _flatten_forward_returns(result))
    write_json(author_scores_path, author_scores)
    write_json(stock_author_scores_path, stock_author_scores)
    write_html(html_path, result)
    write_excel(excel_path, result)
    write_json(manifest_path, manifest)

    print(f"[stock-blogger-scoring] posts={len(all_posts)} mentions={len(mentions)} events={len(events)} authors={len(author_scores)}")
    print(f"[stock-blogger-scoring] html={html_path}")
    print(f"[stock-blogger-scoring] excel={excel_path}")
    return 0


def init_config(args: argparse.Namespace) -> int:
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_example_config(), encoding="utf-8")
    print(f"[stock-blogger-scoring] wrote config example: {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Score X stock bloggers by forward excess returns.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Fetch, extract, score, and report.")
    run_parser.add_argument("--config", help="Optional JSON config path.")
    run_parser.add_argument("--accounts", nargs="*", help="X usernames or @handles. Defaults to @labubu_trader @hicagr @xiaomustock.")
    run_parser.add_argument("--days", type=int, help="Content history window in natural days.")
    run_parser.add_argument("--price-days", type=int, help="Daily price history window.")
    run_parser.add_argument("--start")
    run_parser.add_argument("--end")
    run_parser.add_argument("--max-pages", type=int, default=300)
    run_parser.add_argument("--resume", action="store_true")
    run_parser.add_argument("--skip-ai", action="store_true")
    run_parser.add_argument("--skip-market", action="store_true")
    run_parser.add_argument("--output-dir")
    run_parser.add_argument("--model", default=DEFAULT_MODEL)
    run_parser.set_defaults(func=run)

    init_parser = subparsers.add_parser("init-config", help="Write an example scoring config.")
    init_parser.add_argument("--output", default=str(ROOT / "data" / "config" / "stock_blogger_scoring.example.json"))
    init_parser.set_defaults(func=init_config)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
