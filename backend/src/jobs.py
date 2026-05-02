from __future__ import annotations

from pathlib import Path

from packages.ai import normalize_existing_analysis, reanalyze_existing_content, run_analysis
from packages.common import InsightStore, init_db, migrate_legacy_json_to_sqlite, sqlite_connection
from packages.common.paths import ensure_runtime_dirs, get_paths
from packages.x import load_watchlist as load_x_watchlist
from packages.x import run_once as run_x_once
from packages.xhs import load_watchlist, login_and_validate, run_once


def resolve_config_path(raw_path: str | None) -> Path:
    paths = get_paths()
    return Path(raw_path).resolve() if raw_path else paths.watchlist_path


def resolve_x_config_path(raw_path: str | None) -> Path:
    paths = get_paths()
    return Path(raw_path).resolve() if raw_path else paths.x_watchlist_path


def run_login(config_path: str | None) -> int:
    paths = get_paths()
    ensure_runtime_dirs(paths)
    cfg = load_watchlist(str(resolve_config_path(config_path)))
    return login_and_validate(cfg, paths)


def run_once_job(config_path: str | None) -> int:
    paths = get_paths()
    ensure_runtime_dirs(paths)
    cfg = load_watchlist(str(resolve_config_path(config_path)))
    if not cfg.enabled:
        print("crawl: skipped (xiaohongshu disabled in config)")
        return 0
    if not paths.insight_db_path.exists():
        migrate_legacy_json_to_sqlite(paths)

    print("stage: 获取账号内容（小红书）", flush=True)
    crawl_summary = run_once(cfg, paths)
    print(
        "stage:",
        f"抓取完成：账号 {len(crawl_summary.account_results)} 个，新增内容 {len(crawl_summary.new_notes)} 条，错误 {len(crawl_summary.errors)} 个",
        flush=True,
    )
    with sqlite_connection(paths) as conn:
        init_db(conn)
        store = InsightStore(conn)
        for note in crawl_summary.new_notes:
            store.upsert_content_item(note)
        notes = store.list_all_content_items()
    print(f"stage: AI分析中（待处理内容 {len(notes)} 条）", flush=True)
    analysis_summary = run_analysis(
        paths=paths,
        notes=notes,
        crawl_results=crawl_summary.account_results,
        crawl_errors=crawl_summary.errors,
    )
    print(
        "crawl:",
        f"accounts={len(crawl_summary.account_results)}",
        f"new_notes={len(crawl_summary.new_notes)}",
        f"errors={len(crawl_summary.errors)}",
    )
    print(
        "analysis:",
        f"run_id={analysis_summary.snapshot.run_id}",
        f"author_days={len(analysis_summary.snapshot.author_summaries)}",
        f"stock_days={len(analysis_summary.snapshot.stock_views)}",
        f"theme_days={len(analysis_summary.snapshot.theme_views)}",
        f"errors={len(analysis_summary.snapshot.errors)}",
    )
    print(
        "result:",
        f"新增内容 {len(crawl_summary.new_notes)} 条，AI新增分析 {len(analysis_summary.snapshot.note_extracts)} 条，",
        f"作者日 {len(analysis_summary.snapshot.author_summaries)} 个，",
        f"股票日 {len(analysis_summary.snapshot.stock_views)} 个，",
        f"Theme日 {len(analysis_summary.snapshot.theme_views)} 个，",
        f"错误 {len(analysis_summary.snapshot.errors)} 个",
        flush=True,
    )
    return 1 if crawl_summary.exit_code or analysis_summary.exit_code else 0


def run_once_x_job(config_path: str | None) -> int:
    paths = get_paths()
    ensure_runtime_dirs(paths)
    resolved_config = resolve_x_config_path(config_path)
    if not resolved_config.exists():
        print(f"x crawl: skipped (missing config: {resolved_config})")
        return 0
    cfg = load_x_watchlist(str(resolved_config))
    if not cfg.enabled:
        print("x crawl: skipped (platform disabled in config)")
        return 0
    if not paths.insight_db_path.exists():
        migrate_legacy_json_to_sqlite(paths)

    print("stage: 获取账号内容（X）", flush=True)
    crawl_summary = run_x_once(cfg, paths)
    print(
        "stage:",
        f"抓取完成：账号 {len(crawl_summary.account_results)} 个，新增内容 {len(crawl_summary.new_notes)} 条，错误 {len(crawl_summary.errors)} 个",
        flush=True,
    )
    with sqlite_connection(paths) as conn:
        init_db(conn)
        store = InsightStore(conn)
        for note in crawl_summary.new_notes:
            store.upsert_content_item(note)
        notes = store.list_all_content_items()
    print(f"stage: AI分析中（待处理内容 {len(notes)} 条）", flush=True)
    analysis_summary = run_analysis(
        paths=paths,
        notes=notes,
        crawl_results=crawl_summary.account_results,
        crawl_errors=crawl_summary.errors,
    )
    print(
        "x crawl:",
        f"accounts={len(crawl_summary.account_results)}",
        f"new_notes={len(crawl_summary.new_notes)}",
        f"errors={len(crawl_summary.errors)}",
    )
    print(
        "analysis:",
        f"run_id={analysis_summary.snapshot.run_id}",
        f"author_days={len(analysis_summary.snapshot.author_summaries)}",
        f"stock_days={len(analysis_summary.snapshot.stock_views)}",
        f"theme_days={len(analysis_summary.snapshot.theme_views)}",
        f"errors={len(analysis_summary.snapshot.errors)}",
    )
    print(
        "result:",
        f"新增内容 {len(crawl_summary.new_notes)} 条，AI新增分析 {len(analysis_summary.snapshot.note_extracts)} 条，",
        f"作者日 {len(analysis_summary.snapshot.author_summaries)} 个，",
        f"股票日 {len(analysis_summary.snapshot.stock_views)} 个，",
        f"Theme日 {len(analysis_summary.snapshot.theme_views)} 个，",
        f"错误 {len(analysis_summary.snapshot.errors)} 个",
        flush=True,
    )
    return 1 if crawl_summary.exit_code or analysis_summary.exit_code else 0


def run_migration_job() -> int:
    paths = get_paths()
    ensure_runtime_dirs(paths)
    summary = migrate_legacy_json_to_sqlite(paths)
    print(
        "migration:",
        f"notes={summary.migrated_notes}",
        f"extracts={summary.migrated_extracts}",
        f"author_days={summary.migrated_author_days}",
        f"stock_days={summary.migrated_stock_days}",
        f"db={paths.insight_db_path}",
    )
    return 0


def run_normalize_securities_job() -> int:
    paths = get_paths()
    ensure_runtime_dirs(paths)
    summary, normalized_extracts = normalize_existing_analysis(paths)
    print(
        "normalize-securities:",
        f"normalized_extracts={normalized_extracts}",
        f"run_id={summary.snapshot.run_id}",
        f"author_days={len(summary.snapshot.author_summaries)}",
        f"stock_days={len(summary.snapshot.stock_views)}",
        f"theme_days={len(summary.snapshot.theme_views)}",
        f"errors={len(summary.snapshot.errors)}",
    )
    return 1 if summary.exit_code else 0


def run_reanalyze_existing_job() -> int:
    paths = get_paths()
    ensure_runtime_dirs(paths)
    if not paths.insight_db_path.exists():
        migrate_legacy_json_to_sqlite(paths)
    summary = reanalyze_existing_content(paths)
    print(
        "reanalyze-existing:",
        f"run_id={summary.snapshot.run_id}",
        f"processed_notes={len(summary.snapshot.processed_note_ids)}",
        f"reanalyzed_notes={len(summary.snapshot.note_extracts)}",
        f"author_days={len(summary.snapshot.author_summaries)}",
        f"stock_days={len(summary.snapshot.stock_views)}",
        f"theme_days={len(summary.snapshot.theme_views)}",
        f"errors={len(summary.snapshot.errors)}",
    )
    return 1 if summary.exit_code else 0
