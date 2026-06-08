from __future__ import annotations

import sqlite3

from packages.ai.pipeline import _materialize_stock_news_timelines, _parse_event
from packages.common.database import InsightStore, init_db
from packages.common.models import EventLinkedEntity, EventRecord, NewsTimelineDay, NoteExtractRecord, RawNoteRecord


def test_parse_event_normalizes_stock_and_theme_entities() -> None:
    event = _parse_event(
        {
            "headline": "三星晶圆代工业务今年 Q3 有望扭亏",
            "event_summary": "报道称 2nm 与 HBM base die 产量改善，推动 foundry 盈利修复。",
            "event_type": "profitability_outlook",
            "event_nature": "exclusive",
            "evidence": "Expected to Return to Profit in Q3 This Year",
            "linked_entities": [
                {
                    "entity_type": "stock",
                    "entity_name": "Samsung Electronics",
                    "entity_code_or_name": "005930.KS",
                },
                {
                    "entity_type": "theme",
                    "entity_name": "HBM 产业链",
                    "entity_code_or_name": "HBM",
                },
            ],
        },
        order=0,
        aliases={},
    )

    assert event is not None
    assert event.event_type == "profitability_outlook"
    assert event.event_nature == "exclusive"
    assert [item.entity_type for item in event.linked_entities] == ["stock", "theme"]
    assert event.linked_entities[0].entity_key
    assert event.linked_entities[1].entity_key == "hbm"


def test_materialize_stock_news_timelines_groups_events_by_day() -> None:
    extract_a = NoteExtractRecord(
        platform="x",
        note_id="n1",
        account_name="alice",
        profile_url="https://example.com/alice",
        note_url="https://example.com/n1",
        note_title="News A",
        publish_time="2026-06-08T09:00:00Z",
        date="2026-06-08",
        extracted_at="2026-06-08T10:00:00Z",
        events=[
            EventRecord(
                headline="英伟达供应链需求继续走强",
                event_summary="报道提到 HBM 与先进封装需求上行。",
                event_type="supply_chain_update",
                linked_entities=[
                    EventLinkedEntity(entity_type="stock", entity_key="nvda", entity_name="NVIDIA", entity_code_or_name="NVDA"),
                    EventLinkedEntity(entity_type="theme", entity_key="hbm", entity_name="HBM", entity_code_or_name="HBM"),
                ],
            )
        ],
    )
    extract_b = NoteExtractRecord(
        platform="x",
        note_id="n2",
        account_name="bob",
        profile_url="https://example.com/bob",
        note_url="https://example.com/n2",
        note_title="News B",
        publish_time="2026-06-07T08:00:00Z",
        date="2026-06-07",
        extracted_at="2026-06-08T10:00:00Z",
        events=[
            EventRecord(
                headline="台积电先进制程产能再扩张",
                event_summary="公告显示先进封装与 2nm 进度继续推进。",
                event_type="product_update",
                linked_entities=[EventLinkedEntity(entity_type="stock", entity_key="tsm", entity_name="TSMC", entity_code_or_name="TSM")],
            )
        ],
    )

    records = _materialize_stock_news_timelines(
        store=object(),
        extracts={"x::n1": extract_a, "x::n2": extract_b},
    )

    assert [item.date for item in records] == ["2026-06-08", "2026-06-07"]
    assert records[0].event_count == 1
    assert records[0].events[0].account_name == "alice"
    assert records[0].events[0].linked_entities[1].entity_name == "HBM"


def test_sqlite_store_roundtrips_stock_events() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    store = InsightStore(conn)

    note = RawNoteRecord(
        platform="x",
        account_name="alice",
        profile_url="https://example.com/alice",
        note_id="n1",
        url="https://example.com/n1",
        title="Event note",
        fetched_at="2026-06-08T10:00:00Z",
    )
    store.upsert_content_item(note)
    extract = NoteExtractRecord(
        platform="x",
        note_id="n1",
        account_name="alice",
        profile_url="https://example.com/alice",
        note_url="https://example.com/n1",
        note_title="Event note",
        date="2026-06-08",
        extracted_at="2026-06-08T10:05:00Z",
        summary_text="主要是新闻事件",
        events=[
            EventRecord(
                headline="三星 foundry 业务接近盈亏平衡",
                event_summary="独家报道指出三季度有望转盈。",
                event_type="exclusive_report",
                event_nature="exclusive",
                evidence="Return to Profit in Q3",
                linked_entities=[
                    EventLinkedEntity(entity_type="stock", entity_key="005930.ks", entity_name="Samsung Electronics", entity_code_or_name="005930.KS"),
                    EventLinkedEntity(entity_type="theme", entity_key="2nm", entity_name="2nm", entity_code_or_name="2nm"),
                ],
            )
        ],
    )

    store.replace_content_analysis(extract)
    result = store.get_analysis_map()

    saved = result["x::n1"]
    assert saved.summary_text == "主要是新闻事件"
    assert len(saved.events) == 1
    assert saved.events[0].headline == "三星 foundry 业务接近盈亏平衡"
    assert [item.entity_type for item in saved.events[0].linked_entities] == ["stock", "theme"]


def test_stock_news_day_store_method_writes_timeline_rows() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    store = InsightStore(conn)

    record = NewsTimelineDay(
        date="2026-06-08",
        event_count=1,
        events=[],
        content_hash="hash",
        updated_at="2026-06-08T10:00:00Z",
    )
    store.upsert_stock_news_day(record)

    row = conn.execute("SELECT date_key, event_count FROM stock_news_daily_timeline").fetchone()
    assert row is not None
    assert row["date_key"] == "2026-06-08"
    assert row["event_count"] == 1


def test_sqlite_store_can_clear_analysis_for_selected_notes_only() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    store = InsightStore(conn)

    note_a = RawNoteRecord(
        platform="x",
        account_name="alice",
        profile_url="https://example.com/alice",
        note_id="n1",
        url="https://example.com/n1",
        title="Event note A",
        fetched_at="2026-06-08T10:00:00Z",
    )
    note_b = RawNoteRecord(
        platform="x",
        account_name="bob",
        profile_url="https://example.com/bob",
        note_id="n2",
        url="https://example.com/n2",
        title="Event note B",
        fetched_at="2026-06-08T10:00:00Z",
    )
    store.upsert_content_item(note_a)
    store.upsert_content_item(note_b)

    extract_a = NoteExtractRecord(
        platform="x",
        note_id="n1",
        account_name="alice",
        profile_url="https://example.com/alice",
        note_url="https://example.com/n1",
        note_title="Event note A",
        date="2026-06-08",
        extracted_at="2026-06-08T10:05:00Z",
        summary_text="A",
        events=[
            EventRecord(
                headline="A",
                linked_entities=[
                    EventLinkedEntity(
                        entity_type="stock",
                        entity_key="amd",
                        entity_name="AMD",
                        entity_code_or_name="AMD",
                    )
                ],
            )
        ],
    )
    extract_b = NoteExtractRecord(
        platform="x",
        note_id="n2",
        account_name="bob",
        profile_url="https://example.com/bob",
        note_url="https://example.com/n2",
        note_title="Event note B",
        date="2026-06-08",
        extracted_at="2026-06-08T10:05:00Z",
        summary_text="B",
    )
    store.replace_content_analysis(extract_a)
    store.replace_content_analysis(extract_b)

    cleared = store.clear_content_analysis_for_notes([note_a])

    assert cleared == 1
    result = store.get_analysis_map()
    assert "x::n1" not in result
    assert "x::n2" in result
    remaining_events = conn.execute("SELECT count(*) AS count FROM content_events").fetchone()
    assert remaining_events is not None
    assert remaining_events["count"] == 0
