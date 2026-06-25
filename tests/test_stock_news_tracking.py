from __future__ import annotations

from contextlib import contextmanager

from packages.public_app.stock_news_tracking import (
    DEFAULT_TRACKING_PRICE_REFRESH_LIMIT,
    MAX_TRACKED_STOCKS_PER_NEWS,
    _candidate_to_identity,
    _score_prices,
    refresh_stock_news_tracking_prices_once,
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


def test_refresh_prices_uses_security_key_when_security_id_missing(monkeypatch) -> None:
    tracked_rows = [
        {
            "row_id": "row-1",
            "tracking_id": "tracking-1",
            "security_id": None,
            "security_key": "603920.sh",
            "display_name": "Guangzhou Fangbang Electronics Co., Ltd.",
            "ticker": "603920",
            "market": "SSE",
            "selected_date": "2026-06-15",
            "event_date": "2026-06-15",
        }
    ]
    price_rows = [
        {"date_key": "2026-06-15", "close_price": 100.0},
        {"date_key": "2026-06-16", "close_price": 105.0},
        {"date_key": "2026-06-17", "close_price": 110.0},
        {"date_key": "2026-06-18", "close_price": 115.0},
    ]

    class FakeResult:
        def __init__(self, rows):
            self._rows = rows

        def fetchall(self):
            return self._rows

        def fetchone(self):
            return self._rows[0] if self._rows else None

    class FakeConn:
        def __init__(self):
            self.executed = []
            self.commits = 0
            self.rollbacks = 0

        def execute(self, sql, params=None):
            self.executed.append((sql, params))
            sql_text = " ".join(str(sql).split())
            if "FROM public.stock_news_tracking_stocks t" in sql_text and "JOIN public.stock_news_tracking n" in sql_text:
                return FakeResult(tracked_rows)
            if "FROM public.security_daily_prices p" in sql_text and "JOIN public.security_entities se" in sql_text:
                assert params == ("603920.sh",)
                return FakeResult(price_rows)
            if "UPDATE public.stock_news_tracking_stocks t" in sql_text and "SET security_id =" in sql_text:
                return FakeResult([])
            if "UPDATE public.stock_news_tracking_stocks" in sql_text and "SET price_status =" in sql_text:
                return FakeResult([])
            if "UPDATE public.stock_news_tracking_stocks" in sql_text and "SET selected_date =" in sql_text:
                return FakeResult([])
            raise AssertionError(f"Unexpected SQL: {sql_text}")

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

    class FakeStore:
        def __init__(self, conn):
            self.conn = conn
            self.writes = []

        def upsert_security_daily_prices(self, **kwargs):
            self.writes.append(kwargs)

    fake_conn = FakeConn()

    @contextmanager
    def fake_postgres_connection():
        yield fake_conn

    monkeypatch.setattr("packages.public_app.stock_news_tracking.postgres_connection", fake_postgres_connection)
    monkeypatch.setattr("packages.public_app.stock_news_tracking.PostgresInsightStore", FakeStore)
    monkeypatch.setattr(
        "packages.public_app.stock_news_tracking.fetch_security_daily",
        lambda **_kwargs: {
            "sourceLabel": "Mock",
            "sourceSymbol": "603920",
            "candles": price_rows,
        },
    )

    result = refresh_stock_news_tracking_prices_once(delay_seconds=0, limit=1)

    assert result == 0
    assert fake_conn.rollbacks == 0
    assert any("JOIN public.security_entities se" in " ".join(str(sql).split()) for sql, _ in fake_conn.executed)
    assert all("WHERE security_id =" not in " ".join(str(sql).split()) for sql, _ in fake_conn.executed)
