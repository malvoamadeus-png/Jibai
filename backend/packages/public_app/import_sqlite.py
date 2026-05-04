from __future__ import annotations

from packages.ai.pipeline import run_analysis_with_store
from packages.common.database import InsightStore, init_db, sqlite_connection
from packages.common.paths import ensure_runtime_dirs, get_paths
from packages.common.postgres_database import PostgresInsightStore, postgres_connection


def import_sqlite_x_to_supabase() -> int:
    paths = get_paths()
    ensure_runtime_dirs(paths)

    with sqlite_connection(paths) as sqlite_conn:
        init_db(sqlite_conn)
        sqlite_store = InsightStore(sqlite_conn)
        notes = sqlite_store.list_all_content_items(platform="x")
        extracts = sqlite_store.get_analysis_map(platform="x")

    with postgres_connection() as pg_conn:
        pg_store = PostgresInsightStore(pg_conn)
        for note in notes:
            pg_store.upsert_content_item(note)
        for extract in extracts.values():
            pg_store.replace_content_analysis(extract)
        imported_notes = pg_store.list_all_content_items(platform="x")
        summary = run_analysis_with_store(
            store=pg_store,
            paths=paths,
            notes=imported_notes,
            crawl_results=[],
            crawl_errors=[],
        )

    print(
        "public-import-sqlite:",
        f"notes={len(notes)}",
        f"extracts={len(extracts)}",
        f"analysis_errors={len(summary.snapshot.errors)}",
    )
    return 0
