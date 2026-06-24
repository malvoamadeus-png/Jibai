from __future__ import annotations

from packages.public_app.stock_news_tracking import (
    DEFAULT_TRACKING_PRICE_REFRESH_LIMIT,
    MAX_TRACKED_STOCKS_PER_NEWS,
    _candidate_to_identity,
    _score_prices,
)


def test_tracking_candidate_normalizes_missing_market_from_ticker_suffix() -> None:
    candidate = _candidate_to_identity(
        {
            "company_name": "Murata Manufacturing",
            "ticker": "6981.T",
            "market": "",
            "country_or_region": "Japan",
            "benefit_layer": "self",
            "core_link": "高端 MLCC",
            "benefit_logic": "高端 MLCC 龙头直接受益涨价。",
            "confidence": "high",
        }
    )

    assert candidate is not None
    assert candidate.identity.security_key == "6981.t"
    assert candidate.identity.ticker == "6981"
    assert candidate.identity.market == "TSE"


def test_tracking_candidate_uses_market_when_ticker_has_no_suffix() -> None:
    candidate = _candidate_to_identity(
        {
            "company_name": "Samsung Electronics",
            "ticker": "005930",
            "market": "KRX",
            "country_or_region": "Korea",
            "benefit_layer": "peer",
            "core_link": "高端 MLCC",
            "benefit_logic": "高端 MLCC -> 同环节韩国厂商 -> 涨价带动盈利弹性。",
            "confidence": "medium",
        }
    )

    assert candidate is not None
    assert candidate.identity.security_key == "005930.krx"
    assert candidate.identity.market == "KRX"


def test_tracking_candidate_rejects_non_one_hop_layer() -> None:
    candidate = _candidate_to_identity(
        {
            "company_name": "Furukawa Electric",
            "ticker": "5801.T",
            "market": "TSE",
            "country_or_region": "Japan",
            "benefit_layer": "downstream_2",
            "core_link": "InP",
            "benefit_logic": "InP -> 光模块 -> 数据中心投资扩张，链条超过一跳。",
            "confidence": "medium",
        }
    )

    assert candidate is None


def test_score_prices_uses_next_trading_day_anchor_and_pending_unmatured_horizon() -> None:
    result = _score_prices(
        [
            {"date": "2026-06-16", "close": 100.0},
            {"date": "2026-06-17", "close": 105.0},
            {"date": "2026-06-18", "close": 110.0},
            {"date": "2026-06-19", "close": 115.0},
        ],
        "2026-06-15",
    )

    assert result["anchor_status"] == "next_trading_day"
    assert result["return_3d"] == 0.15
    assert result["horizon_7_status"] == "pending"
    assert result["return_since_selected"] == 0.15


def test_tracking_stock_limit_constant_is_30() -> None:
    assert MAX_TRACKED_STOCKS_PER_NEWS == 30


def test_tracking_price_refresh_default_limit_is_25() -> None:
    assert DEFAULT_TRACKING_PRICE_REFRESH_LIMIT == 25
