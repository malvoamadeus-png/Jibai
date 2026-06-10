from __future__ import annotations

import sqlite3
from pathlib import Path

from packages.common.database import InsightStore, init_db
from packages.common.daily_author_viewpoint_export import export_daily_author_viewpoints, resolve_latest_export_date
from packages.common.models import AuthorDayRecord
from packages.common.paths import get_paths


def test_export_daily_author_viewpoints_writes_expected_csv(tmp_path: Path) -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    store = InsightStore(conn)
    conn.execute(
        """
        INSERT INTO security_entities (security_key, display_name, ticker, market, aliases_json)
        VALUES ('amd', 'AMD', 'AMD', 'NASDAQ', '[]')
        """
    )

    store.upsert_author_daily_summary(
        AuthorDayRecord(
            platform="x",
            date="2026-06-08",
            account_name="alice",
            profile_url="https://example.com/alice",
            author_nickname="Alice",
            status="has_update_today",
            note_count_today=2,
            summary_text="Alice 今天看多 AMD。",
            viewpoints=[
                {
                    "entity_type": "stock",
                    "entity_key": "amd",
                    "entity_name": "AMD",
                    "stance": "strong_bullish",
                    "direction": "positive",
                    "conviction": "strong",
                    "logic": "AI 服务器需求继续上修。",
                },
                {
                    "entity_type": "theme",
                    "entity_key": "ai",
                    "entity_name": "AI",
                    "stance": "bullish",
                    "direction": "positive",
                    "conviction": "medium",
                    "logic": "主题观点不应导出。",
                },
                {
                    "entity_type": "stock",
                    "entity_key": "nvda",
                    "entity_name": "NVIDIA",
                    "stance": "mention_only",
                    "direction": "unknown",
                    "conviction": "unknown",
                    "logic": "仅提及也不应导出。",
                },
            ],
            updated_at="2026-06-08T10:00:00Z",
        )
    )
    store.upsert_author_daily_summary(
        AuthorDayRecord(
            platform="x",
            date="2026-06-07",
            account_name="bob",
            profile_url="https://example.com/bob",
            author_nickname="",
            status="has_update_today",
            note_count_today=1,
            summary_text="Bob 昨天看空 TSLA。",
            viewpoints=[
                {
                    "entity_type": "stock",
                    "entity_key": "tsla",
                    "entity_name": "Tesla",
                    "stance": "bearish",
                    "direction": "negative",
                    "conviction": "medium",
                    "logic": "估值太高。",
                }
            ],
            updated_at="2026-06-07T10:00:00Z",
        )
    )

    result = export_daily_author_viewpoints(
        conn,
        paths=get_paths(),
        date_key="2026-06-08",
        output_path=str(tmp_path / "daily.xlsx"),
    )

    assert result.date == "2026-06-08"
    assert result.row_count == 1
    assert result.output_path.exists()

    content = result.output_path.read_text(encoding="utf-8-sig")

    assert "平台" not in content
    assert "Alice" in content
    assert "AMD" in content
    assert "看多" in content
    assert "强" in content
    assert "AI 服务器需求继续上修" in content
    assert "NVIDIA" not in content
    assert "主题观点不应导出" not in content


def test_resolve_latest_export_date_skips_days_without_exportable_stock_viewpoints() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    store = InsightStore(conn)

    store.upsert_author_daily_summary(
        AuthorDayRecord(
            platform="x",
            date="2026-06-08",
            account_name="alice",
            profile_url="https://example.com/alice",
            status="has_update_today",
            note_count_today=1,
            summary_text="只有提及。",
            viewpoints=[
                {
                    "entity_type": "stock",
                    "entity_key": "amd",
                    "entity_name": "AMD",
                    "stance": "mention_only",
                    "direction": "unknown",
                    "conviction": "unknown",
                    "logic": "",
                }
            ],
            updated_at="2026-06-08T10:00:00Z",
        )
    )
    store.upsert_author_daily_summary(
        AuthorDayRecord(
            platform="x",
            date="2026-06-07",
            account_name="alice",
            profile_url="https://example.com/alice",
            status="has_update_today",
            note_count_today=1,
            summary_text="有明确观点。",
            viewpoints=[
                {
                    "entity_type": "stock",
                    "entity_key": "tsla",
                    "entity_name": "Tesla",
                    "stance": "bearish",
                    "direction": "negative",
                    "conviction": "medium",
                    "logic": "估值承压。",
                }
            ],
            updated_at="2026-06-07T10:00:00Z",
        )
    )

    assert resolve_latest_export_date(conn) == "2026-06-07"
