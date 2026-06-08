from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from .ai_extract import extract_mentions
    from .fetcher import fetch_posts, normalize_username
    from .jsonl import read_jsonl, write_json, write_jsonl
    from .market import attach_prices_and_build_charts, build_scores, normalize_mentions
    from .models import AuditPost, AuditResult, StockMention
    from .report import write_excel, write_html
except ImportError:
    from tools.audit.x_account_stock_audit.ai_extract import extract_mentions
    from tools.audit.x_account_stock_audit.fetcher import fetch_posts, normalize_username
    from tools.audit.x_account_stock_audit.jsonl import read_jsonl, write_json, write_jsonl
    from tools.audit.x_account_stock_audit.market import attach_prices_and_build_charts, build_scores, normalize_mentions
    from tools.audit.x_account_stock_audit.models import AuditPost, AuditResult, StockMention
    from tools.audit.x_account_stock_audit.report import write_excel, write_html


DEFAULT_PROFILE = "https://x.com/aleabitoreddit"
DEFAULT_MODEL = "gpt-5.4-mini"


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _run_dir(base: Path, username: str, start_date: date, end_date: date) -> Path:
    return base / f"{username}_{start_date.isoformat()}_{end_date.isoformat()}"


def _posts_from_jsonl(path: Path) -> list[AuditPost]:
    return [AuditPost(**row) for row in read_jsonl(path)]


def _mentions_from_jsonl(path: Path) -> list[StockMention]:
    return [StockMention(**row) for row in read_jsonl(path)]


def run(args: argparse.Namespace) -> int:
    username = normalize_username(args.profile)
    end_date = _parse_date(args.end) if args.end else date.today()
    start_date = _parse_date(args.start) if args.start else end_date - timedelta(days=int(args.days) - 1)
    output_root = Path(args.output_dir) if args.output_dir else Path(__file__).resolve().parent / "runs"
    run_dir = _run_dir(output_root, username, start_date, end_date)
    run_dir.mkdir(parents=True, exist_ok=True)

    raw_path = run_dir / "raw_statuses.jsonl"
    posts_path = run_dir / "normalized_posts.jsonl"
    mentions_path = run_dir / "stock_mentions.jsonl"
    manifest_path = run_dir / "run_manifest.json"

    existing_posts = _posts_from_jsonl(posts_path) if args.resume and posts_path.exists() else []
    posts, raw_statuses, fetch_summary = fetch_posts(
        username=username,
        start_date=start_date,
        end_date=end_date,
        max_pages=int(args.max_pages),
        existing_posts=existing_posts,
    )
    write_jsonl(raw_path, raw_statuses)
    write_jsonl(posts_path, posts)

    if args.skip_ai:
        mentions = _mentions_from_jsonl(mentions_path) if mentions_path.exists() else []
    elif args.resume and mentions_path.exists():
        mentions = _mentions_from_jsonl(mentions_path)
    else:
        mentions = extract_mentions(posts, model=args.model)
        write_jsonl(mentions_path, mentions)

    mentions = normalize_mentions(mentions)
    charts = attach_prices_and_build_charts(mentions, skip_market=args.skip_market)
    scores = build_scores(charts)

    manifest = {
        "profile_url": f"https://x.com/{username}",
        "username": username,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "model": args.model,
        "skip_ai": bool(args.skip_ai),
        "skip_market": bool(args.skip_market),
        "fetch": fetch_summary,
        "post_count": len(posts),
        "mention_count": len(mentions),
        "stock_count": len(charts),
        "outputs": {
            "raw_statuses": str(raw_path),
            "normalized_posts": str(posts_path),
            "mentions": str(mentions_path),
            "html": str(run_dir / "report.html"),
            "excel": str(run_dir / "audit.xlsx"),
        },
    }

    result = AuditResult(
        profile_url=f"https://x.com/{username}",
        username=username,
        run_dir=str(run_dir),
        started_at=datetime.now().astimezone(),
        start_date=start_date,
        end_date=end_date,
        posts=posts,
        mentions=mentions,
        charts=charts,
        scores=scores,
        manifest=manifest,
    )
    write_html(run_dir / "report.html", result)
    write_excel(run_dir / "audit.xlsx", result)
    write_json(manifest_path, manifest)

    print(f"[x-audit] posts={len(posts)} mentions={len(mentions)} stocks={len(charts)}")
    print(f"[x-audit] html={run_dir / 'report.html'}")
    print(f"[x-audit] excel={run_dir / 'audit.xlsx'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit one X account's historical stock calls.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="Fetch, analyze, price, and report.")
    run_parser.add_argument("--profile", default=DEFAULT_PROFILE)
    run_parser.add_argument("--days", type=int, default=31)
    run_parser.add_argument("--start")
    run_parser.add_argument("--end")
    run_parser.add_argument("--max-pages", type=int, default=300)
    run_parser.add_argument("--resume", action="store_true")
    run_parser.add_argument("--skip-ai", action="store_true")
    run_parser.add_argument("--skip-market", action="store_true")
    run_parser.add_argument("--output-dir")
    run_parser.add_argument("--model", default=DEFAULT_MODEL)
    run_parser.set_defaults(func=run)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
