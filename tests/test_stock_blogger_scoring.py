from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zipfile import ZipFile

import pytest

from packages.common.market_data import build_market_data_target
from packages.common.paths import get_paths
from packages.common.security_aliases import load_security_aliases, resolve_security_identity
from tools.stock_blogger_scoring.config import load_config
from tools.stock_blogger_scoring.market import benchmark_kind_for_market, fetch_a_share_benchmark_candles, score_event, score_events
from tools.stock_blogger_scoring.models import Candle, HorizonScore, ScoringConfig, ScoringRunResult, SignalEvent, StockSignalMention
from tools.stock_blogger_scoring.report import write_excel, write_html
from tools.stock_blogger_scoring.scoring import aggregate_author_scores, build_signal_events


def _mention(
    tweet_id: str,
    published_at: str,
    *,
    direction: str = "positive",
    conviction: str = "medium",
    stock: str = "AMD",
    ticker: str | None = None,
    market: str = "NASDAQ",
    security_key: str | None = None,
) -> StockSignalMention:
    ticker = ticker or stock
    return StockSignalMention(
        tweet_id=tweet_id,
        author="@labubu_trader",
        author_name="Labubu",
        published_at=published_at,
        tweet_url=f"https://x.com/labubu_trader/status/{tweet_id}",
        raw_text=f"{stock} looks good",
        stock_name=stock,
        ticker_or_code=ticker,
        market_hint=market,
        direction=direction,
        signal_type="logic_based",
        judgment_type="direct",
        conviction=conviction,
        evidence_type="guidance",
        time_horizon="medium_term",
        confidence=0.9,
        logic=f"{stock} demand improves -> bullish",
        evidence="demand improves",
        security_key=security_key or ticker.lower(),
        display_name=stock,
        ticker=ticker,
        market=market,
        normalized_status="canonical",
    )


def _event(direction: str = "positive", published_at: str = "2026-05-20T09:00:00-04:00") -> SignalEvent:
    return build_signal_events([_mention("1", published_at, direction=direction)])[0]


def test_default_config_uses_initial_three_accounts() -> None:
    config = load_config()
    assert config.accounts == ["labubu_trader", "hicagr", "xiaomustock"]
    assert config.horizon_weights == {"1d": 0.20, "5d": 0.35, "20d": 0.45}
    assert config.score_scales == {"1d": 0.05, "5d": 0.10, "20d": 0.20}
    assert config.a_share_benchmark_symbol == "000688"
    assert config.a_share_benchmark_fallback_symbol == "588000"
    assert config.a_share_benchmark_extra_symbols == []


def test_load_config_accepts_legacy_score_caps(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text('{"score_caps":{"1d":0.02}}', encoding="utf-8")

    config = load_config(config_path)

    assert config.score_scales == {"1d": 0.02}


def test_builtin_security_aliases_cover_hunan_yuneng_and_marvell() -> None:
    aliases = load_security_aliases(get_paths())

    hunan = resolve_security_identity("湖南裕能", "湖南裕能", aliases)
    marvell = resolve_security_identity("Marvell Technology", "Marvell Technology", aliases)

    assert hunan is not None
    assert hunan.security_key == "301358.sz"
    assert hunan.ticker == "301358"
    assert hunan.market == "SZSE"
    assert marvell is not None
    assert marvell.security_key == "marvell"
    assert marvell.ticker == "MRVL"
    assert marvell.market == "NASDAQ"


def test_market_data_target_supports_hk_suffix() -> None:
    target = build_market_data_target(ticker="0700", market="HK", security_key="tencent")

    assert target is not None
    assert target["provider"] == "yahoo"
    assert target["symbol"] == "0700.HK"


def test_market_data_target_treats_theme_market_hint_as_us_ticker() -> None:
    target = build_market_data_target(ticker="MRVL", market="AI networking/optics", security_key="marvell")

    assert target is not None
    assert target["provider"] == "yahoo"
    assert target["symbol"] == "MRVL"
    assert target["market"] == "US"


def test_benchmark_kind_uses_a_share_only_for_mainland_markets() -> None:
    assert benchmark_kind_for_market("SZSE") == "a_share"
    assert benchmark_kind_for_market("SSE") == "a_share"
    assert benchmark_kind_for_market("TWSE") == "global"
    assert benchmark_kind_for_market("HK") == "global"
    assert benchmark_kind_for_market("NASDAQ") == "global"


def test_a_share_benchmark_tries_star_market_fallbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_eastmoney(*, ticker: str, market: str, days: int):
        calls.append(f"{market}:{ticker}")
        return {"sourceLabel": "EastMoney", "message": "no candles", "candles": []}

    def fake_yahoo(*, symbol: str, days: int):
        calls.append(symbol)
        if symbol == "588000.SS":
            return {
                "sourceLabel": "Yahoo Finance",
                "message": None,
                "candles": [
                    {"date": "2026-05-20", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 100},
                    {"date": "2026-05-21", "open": 1, "high": 1.1, "low": 1, "close": 1.1, "volume": 100},
                ],
            }
        return {"sourceLabel": "Yahoo Finance", "message": "no candles", "candles": []}

    monkeypatch.setattr("tools.stock_blogger_scoring.market.fetch_eastmoney_daily", fake_eastmoney)
    monkeypatch.setattr("tools.stock_blogger_scoring.market.fetch_yahoo_daily", fake_yahoo)

    symbol, candles, payload = fetch_a_share_benchmark_candles(ScoringConfig(price_days=30))

    assert "SSE:000688" in calls
    assert "000688.SZ" not in calls
    assert symbol == "588000.SS"
    assert len(candles) == 2
    assert payload["sourceSymbol"] == "588000.SS"


def test_signal_events_merge_same_author_stock_day_and_keep_cross_day_separate() -> None:
    mentions = [
        _mention("1", "2026-05-20T09:00:00-04:00", conviction="medium"),
        _mention("2", "2026-05-20T11:00:00-04:00", conviction="strong"),
        _mention("3", "2026-05-21T09:00:00-04:00", conviction="weak"),
    ]

    events = build_signal_events(mentions)

    assert len(events) == 2
    assert events[0].tweet_ids == ["1", "2"]
    assert events[0].conviction == "strong"
    assert events[0].metadata["merged_mention_count"] == 2
    assert events[1].tweet_ids == ["3"]


def test_signal_events_mark_same_day_opposite_directions_unscored() -> None:
    mentions = [
        _mention("1", "2026-05-20T09:00:00-04:00", direction="positive"),
        _mention("2", "2026-05-20T11:00:00-04:00", direction="negative"),
    ]

    events = build_signal_events(mentions)

    assert len(events) == 1
    assert events[0].status == "unscored"
    assert events[0].direction == "mixed"
    assert events[0].status_reason == "mixed_same_day"


def test_score_event_uses_open_anchor_and_nasdaq_excess_return() -> None:
    config = ScoringConfig(horizons=(1,))
    event = _event("positive", "2026-05-20T09:00:00-04:00")
    stock = [
        Candle("2026-05-20", open=100, high=112, low=99, close=110),
        Candle("2026-05-21", open=111, high=115, low=109, close=114),
    ]
    benchmark = [
        Candle("2026-05-20", open=100, high=103, low=99, close=102),
        Candle("2026-05-21", open=102, high=104, low=101, close=103),
    ]

    scored = score_event(event, stock, "^IXIC", benchmark, config)
    horizon = scored.horizon_scores["1d"]

    assert scored.anchor_price_kind == "same_day_open"
    assert scored.anchor_price == 100
    assert horizon.target_date == "2026-05-20"
    assert horizon.stock_return == pytest.approx(0.10)
    assert horizon.benchmark_return == pytest.approx(0.02)
    assert horizon.directional_excess == pytest.approx(0.08)
    assert not hasattr(horizon, "hit")
    assert horizon.score == pytest.approx(160)


def test_score_event_inverts_excess_return_for_negative_direction() -> None:
    config = ScoringConfig(horizons=(1,))
    event = _event("negative", "2026-05-20T09:00:00-04:00")
    stock = [Candle("2026-05-20", open=100, high=101, low=94, close=95)]
    benchmark = [Candle("2026-05-20", open=100, high=101, low=99, close=100)]

    horizon = score_event(event, stock, "^IXIC", benchmark, config).horizon_scores["1d"]

    assert horizon.stock_return == pytest.approx(-0.05)
    assert horizon.excess_return == pytest.approx(-0.05)
    assert horizon.directional_excess == pytest.approx(0.05)
    assert horizon.score == pytest.approx(100)


def test_score_event_does_not_cap_large_excess_return() -> None:
    config = ScoringConfig(horizons=(1,))
    event = _event("positive", "2026-05-20T09:00:00-04:00")
    stock = [Candle("2026-05-20", open=100, high=121, low=99, close=120)]
    benchmark = [Candle("2026-05-20", open=100, high=101, low=99, close=100)]

    horizon = score_event(event, stock, "^IXIC", benchmark, config).horizon_scores["1d"]

    assert horizon.directional_excess == pytest.approx(0.20)
    assert horizon.score == pytest.approx(400)


def test_score_events_selects_a_share_and_global_benchmarks(monkeypatch: pytest.MonkeyPatch) -> None:
    config = ScoringConfig(horizons=(1,))
    a_event = build_signal_events([
        _mention(
            "a",
            "2026-05-20T09:00:00+08:00",
            stock="湖南裕能",
            ticker="301358",
            market="SZSE",
            security_key="301358.sz",
        )
    ])[0]
    hk_event = build_signal_events([
        _mention(
            "h",
            "2026-05-20T09:00:00+08:00",
            stock="Tencent",
            ticker="0700",
            market="HK",
            security_key="tencent",
        )
    ])[0]

    stock_candles = [Candle("2026-05-20", open=100, high=111, low=99, close=110)]
    global_benchmark = [Candle("2026-05-20", open=100, high=102, low=99, close=101)]
    a_benchmark = [Candle("2026-05-20", open=100, high=103, low=99, close=102)]

    monkeypatch.setattr(
        "tools.stock_blogger_scoring.market.fetch_stock_candles",
        lambda _event, *, days: (stock_candles, {"sourceLabel": "test", "sourceSymbol": _event.ticker, "message": None}),
    )
    monkeypatch.setattr(
        "tools.stock_blogger_scoring.market.fetch_global_benchmark_candles",
        lambda _config: ("^IXIC", global_benchmark, {"sourceLabel": "Yahoo Finance", "message": None}),
    )
    monkeypatch.setattr(
        "tools.stock_blogger_scoring.market.fetch_a_share_benchmark_candles",
        lambda _config: ("588000.SS", a_benchmark, {"sourceLabel": "Yahoo Finance", "message": None}),
    )

    scored, market_summary = score_events([a_event, hk_event], config=config)

    assert scored[0].benchmark_symbol == "588000.SS"
    assert scored[1].benchmark_symbol == "^IXIC"
    assert scored[0].horizon_scores["1d"].benchmark_return == pytest.approx(0.02)
    assert scored[1].horizon_scores["1d"].benchmark_return == pytest.approx(0.01)
    assert market_summary["a_share_benchmark_symbol"] == "588000.SS"


def test_aggregate_author_scores_counts_pending_without_confidence_factor() -> None:
    config = ScoringConfig(horizons=(1,), min_ranked_events=2, full_confidence_events=4)
    event_a = _event("positive", "2026-05-20T09:00:00-04:00")
    event_a.horizon_scores = {"1d": HorizonScore(horizon="1d", status="scored", directional_excess=0.04, score=80)}
    event_b = _event("positive", "2026-05-21T09:00:00-04:00")
    event_b.event_id = "event-b"
    event_b.horizon_scores = {"1d": HorizonScore(horizon="1d", status="pending")}

    rows = aggregate_author_scores([event_a, event_b], config)

    assert len(rows) == 1
    assert rows[0].score_by_horizon["1d"] == pytest.approx(80)
    assert rows[0].matured_count_by_horizon["1d"] == 1
    assert rows[0].scored_day_count_by_horizon["1d"] == 1
    assert rows[0].scored_day_count == 1
    assert rows[0].pending_count_by_horizon["1d"] == 1
    assert rows[0].overall_score == pytest.approx(80)


def test_aggregate_author_scores_normalizes_multiple_events_by_day() -> None:
    config = ScoringConfig(horizons=(1,))
    day_1 = _event("positive", "2026-05-20T09:00:00-04:00")
    day_1.horizon_scores = {"1d": HorizonScore(horizon="1d", status="scored", score=100)}
    day_2_a = _event("positive", "2026-05-21T09:00:00-04:00")
    day_2_a.event_id = "day-2-a"
    day_2_a.security_key = "amd"
    day_2_a.horizon_scores = {"1d": HorizonScore(horizon="1d", status="scored", score=100)}
    day_2_b = _event("positive", "2026-05-21T10:00:00-04:00")
    day_2_b.event_id = "day-2-b"
    day_2_b.security_key = "nvda"
    day_2_b.horizon_scores = {"1d": HorizonScore(horizon="1d", status="scored", score=100)}

    row = aggregate_author_scores([day_1, day_2_a, day_2_b], config)[0]

    assert row.score_by_horizon["1d"] == pytest.approx(100)
    assert row.scored_day_count_by_horizon["1d"] == 2
    assert row.matured_count_by_horizon["1d"] == 3


def test_aggregate_author_scores_averages_same_day_events_before_period_score() -> None:
    config = ScoringConfig(horizons=(1,))
    event_a = _event("positive", "2026-05-20T09:00:00-04:00")
    event_a.event_id = "event-a"
    event_a.horizon_scores = {"1d": HorizonScore(horizon="1d", status="scored", score=100)}
    event_b = _event("positive", "2026-05-20T10:00:00-04:00")
    event_b.event_id = "event-b"
    event_b.security_key = "nvda"
    event_b.horizon_scores = {"1d": HorizonScore(horizon="1d", status="scored", score=0)}

    row = aggregate_author_scores([event_a, event_b], config)[0]

    assert row.score_by_horizon["1d"] == pytest.approx(50)
    assert row.overall_score == pytest.approx(50)


def test_aggregate_author_scores_overall_uses_horizon_weights_only() -> None:
    config = ScoringConfig(horizons=(1, 5, 20), full_confidence_events=999)
    event = _event("positive", "2026-05-20T09:00:00-04:00")
    event.horizon_scores = {
        "1d": HorizonScore(horizon="1d", status="scored", score=100),
        "5d": HorizonScore(horizon="5d", status="scored", score=200),
        "20d": HorizonScore(horizon="20d", status="scored", score=300),
    }

    row = aggregate_author_scores([event], config)[0]

    assert row.overall_score == pytest.approx(225)
    assert not hasattr(row, "confidence_factor")
    assert not hasattr(row, "raw_overall_score")


def test_report_outputs_html_and_excel(tmp_path: Path) -> None:
    config = ScoringConfig(horizons=(1,))
    event = _event("positive", "2026-05-20T09:00:00-04:00")
    event.anchor_trading_day = "2026-05-20"
    event.anchor_price = 100
    event.anchor_price_kind = "same_day_open"
    event.benchmark_symbol = "^IXIC"
    event.benchmark_anchor_price = 100
    event.horizon_scores = {
        "1d": HorizonScore(
            horizon="1d",
            status="scored",
            target_date="2026-05-20",
            target_price=110,
            benchmark_target_price=102,
            stock_return=0.10,
            benchmark_return=0.02,
            excess_return=0.08,
            directional_excess=0.08,
            score=100,
        )
    }
    author_scores = aggregate_author_scores([event], config)
    result = ScoringRunResult(
        run_dir=str(tmp_path),
        started_at=datetime.now(),
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 31),
        config=config,
        posts=[],
        mentions=[],
        events=[event],
        author_scores=author_scores,
        stock_author_scores=[],
        manifest={"market": {"benchmark_symbol": "^IXIC"}},
    )

    html_path = tmp_path / "report.html"
    excel_path = tmp_path / "audit.xlsx"
    write_html(html_path, result)
    write_excel(excel_path, result)

    assert "股票博主观点验证评分" in html_path.read_text(encoding="utf-8")
    assert "样本量校正" not in html_path.read_text(encoding="utf-8")
    assert "confidence_factor" not in html_path.read_text(encoding="utf-8")
    assert "hit_rate" not in html_path.read_text(encoding="utf-8")
    with ZipFile(excel_path) as archive:
        assert "xl/workbook.xml" in archive.namelist()
        workbook_text = "\n".join(
            archive.read(name).decode("utf-8", errors="ignore")
            for name in archive.namelist()
            if name.startswith("xl/worksheets/") or name == "xl/sharedStrings.xml"
        ).lower()
    assert "confidence_factor" not in workbook_text
    assert "hit_rate" not in workbook_text
    assert ">hit<" not in workbook_text
