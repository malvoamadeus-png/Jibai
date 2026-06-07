from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from packages.public_app.stock_blogger_scoring import (
    MentionRow,
    PriceCandle,
    aggregate_author_scores,
    build_events,
    score_events,
)


def _mention(
    *,
    account_name: str = "labubu_trader",
    security_id: str = "sec-amd",
    security_key: str = "amd",
    display_name: str = "AMD",
    direction: str = "positive",
    conviction: str = "medium",
    publish_time: str = "2026-05-20T08:00:00-04:00",
) -> MentionRow:
    return MentionRow(
        content_id=f"content-{account_name}-{security_key}-{publish_time}",
        viewpoint_id=f"view-{account_name}-{security_key}-{publish_time}",
        account_id=f"account-{account_name}",
        account_name=account_name,
        author_nickname=account_name,
        publish_time=datetime.fromisoformat(publish_time),
        security_id=security_id,
        security_key=security_key,
        display_name=display_name,
        ticker=security_key.upper(),
        market="NASDAQ",
        direction=direction,
        signal_type="logic_based",
        judgment_type="direct",
        conviction=conviction,
        evidence_type="guidance",
        time_horizon="medium_term",
        sort_order=0,
    )


def test_build_events_merges_same_author_stock_day_direction() -> None:
    events = build_events(
        [
            _mention(publish_time="2026-05-20T08:00:00-04:00"),
            _mention(publish_time="2026-05-20T10:00:00-04:00", conviction="strong"),
            _mention(publish_time="2026-05-21T08:00:00-04:00"),
        ]
    )

    assert len(events) == 2
    assert events[0].conviction == "strong"
    assert len(events[0].viewpoint_ids) == 2
    assert events[1].event_trading_day == "2026-05-21"


def test_score_events_does_not_cap_large_excess_return() -> None:
    event = build_events([_mention()])[0]
    stock = [PriceCandle("2026-05-20", open=100, close=120)]
    benchmark = [PriceCandle("2026-05-20", open=100, close=100)]

    scored = score_events(
        [event],
        {"sec-amd": stock},
        (("^IXIC", benchmark), ("588000.SS", benchmark)),
    )[0]

    assert scored.horizon_scores["1d"]["directional_excess"] == pytest.approx(0.20)
    assert scored.horizon_scores["1d"]["score"] == pytest.approx(400)
    assert "hit" not in str(scored.horizon_scores).lower()


def test_aggregate_author_scores_normalizes_by_day_before_period_score() -> None:
    day_1 = build_events([_mention(publish_time="2026-05-20T08:00:00-04:00")])[0]
    day_2_a = build_events([_mention(publish_time="2026-05-21T08:00:00-04:00")])[0]
    day_2_b = build_events([
        _mention(
            security_id="sec-nvda",
            security_key="nvda",
            display_name="NVDA",
            publish_time="2026-05-21T09:00:00-04:00",
        )
    ])[0]
    day_1.horizon_scores = {"1d": {"status": "scored", "score": 100}}
    day_2_a.horizon_scores = {"1d": {"status": "scored", "score": 100}}
    day_2_b.horizon_scores = {"1d": {"status": "scored", "score": 100}}

    row = aggregate_author_scores([day_1, day_2_a, day_2_b])[0]

    assert row.score_by_horizon["1d"] == pytest.approx(100)
    assert row.overall_score == pytest.approx(100)
    assert row.scored_day_count_by_horizon["1d"] == 2
    assert row.matured_count_by_horizon["1d"] == 3


def test_aggregate_author_scores_same_day_average_and_horizon_weights_only() -> None:
    event_a = build_events([_mention(publish_time="2026-05-20T08:00:00-04:00")])[0]
    event_b = build_events([
        _mention(
            security_id="sec-nvda",
            security_key="nvda",
            display_name="NVDA",
            publish_time="2026-05-20T09:00:00-04:00",
        )
    ])[0]
    event_a.horizon_scores = {
        "1d": {"status": "scored", "score": 100},
        "5d": {"status": "scored", "score": 200},
        "20d": {"status": "scored", "score": 300},
    }
    event_b.horizon_scores = {
        "1d": {"status": "scored", "score": 0},
        "5d": {"status": "scored", "score": 200},
        "20d": {"status": "scored", "score": 300},
    }

    row = aggregate_author_scores([event_a, event_b])[0]

    assert row.score_by_horizon["1d"] == pytest.approx(50)
    assert row.overall_score == pytest.approx(215)
    assert not hasattr(row, "confidence_factor")
    assert not hasattr(row, "raw_overall_score")
