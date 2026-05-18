from __future__ import annotations

from packages.public_app.stock_narrative import (
    BriefReference,
    StockNarrativeViewpoint,
    _build_topic_baseline,
    _current_input_items,
    _find_reference_briefs,
    _previous_effective_dates,
    _select_effective_dates,
)


def _record(
    date: str,
    *,
    account: str = "author",
    direction: str = "positive",
    logic: str = "AI 数据中心算力需求上修，因此继续看好相关股票",
    evidence: tuple[str, ...] = ("多名客户上调数据中心资本开支",),
    stock: str = "示例公司",
) -> StockNarrativeViewpoint:
    return StockNarrativeViewpoint(
        date=date,
        account_name=account,
        author_nickname=account,
        direction=direction,
        signal_type="logic_based",
        judgment_type="direct",
        conviction="medium",
        evidence_type="guidance",
        logic=logic,
        evidence=evidence,
        security_key=stock.lower(),
        security_display_name=stock,
        ticker="",
        market="US",
    )


def test_selects_latest_seven_effective_dates_before_target() -> None:
    dates = [f"2026-05-{day:02d}" for day in range(1, 12)]
    assert _select_effective_dates(dates, target_date="2026-05-10") == [
        "2026-05-04",
        "2026-05-05",
        "2026-05-06",
        "2026-05-07",
        "2026-05-08",
        "2026-05-09",
        "2026-05-10",
    ]


def test_previous_effective_dates_are_non_overlapping() -> None:
    dates = [f"2026-05-{day:02d}" for day in range(1, 15)]
    assert _previous_effective_dates(dates, current_window_start="2026-05-08") == [
        "2026-05-01",
        "2026-05-02",
        "2026-05-03",
        "2026-05-04",
        "2026-05-05",
        "2026-05-06",
        "2026-05-07",
    ]


def test_find_reference_briefs_uses_latest_for_continuity_and_non_overlap_for_comparison() -> None:
    briefs = [
        BriefReference(
            id="b2",
            brief_date="2026-05-17",
            window_start="2026-05-11",
            window_end="2026-05-17",
            brief_text="昨天简报",
            sections={},
        ),
        BriefReference(
            id="b1",
            brief_date="2026-05-10",
            window_start="2026-05-04",
            window_end="2026-05-10",
            brief_text="上一非重叠周期",
            sections={},
        ),
    ]

    continuity, comparison = _find_reference_briefs(briefs, current_window_start="2026-05-11")

    assert continuity and continuity.id == "b2"
    assert comparison and comparison.id == "b1"


def test_topic_baseline_counts_recent_and_baseline_mentions() -> None:
    records = [
        _record("2026-05-01", account="a"),
        _record("2026-05-10", account="b"),
        _record("2026-05-11", account="c", direction="negative", logic="AI 服务器订单可能放缓，因此看空相关股票"),
    ]

    baseline = _build_topic_baseline(
        records,
        current_dates={"2026-05-10", "2026-05-11"},
        baseline_start="2026-05-01",
        baseline_end="2026-05-11",
    )
    ai_topic = next(item for item in baseline if item["topic"] == "AI 算力链")

    assert ai_topic["baseline_count"] == 3
    assert ai_topic["recent_7d_count"] == 2
    assert ai_topic["author_count"] == 3
    assert ai_topic["negative_count"] == 1


def test_current_input_items_keep_negative_voice_without_entity_field() -> None:
    items = _current_input_items(
        [
            _record(
                "2026-05-11",
                direction="negative",
                logic="财报指引不及预期，因此减仓",
                evidence=("公司下调全年收入指引",),
            )
        ],
        {"2026-05-11"},
    )

    assert items[0]["direction"] == "negative"
    assert "logic" in items[0]
    assert "evidence" in items[0]
    assert "security_key" not in items[0]
    assert "entity_name" not in items[0]
