from __future__ import annotations

import datetime as dt

from packages.public_app import market_top_risk


def test_parse_fred_table_data() -> None:
    raw = """
DATE        VALUE
2026-06-12  -0.503
2026-06-19  -0.503
2026-06-26  -0.504
"""

    parsed = market_top_risk._parse_fred_table_data(raw)

    assert parsed[dt.date(2026, 6, 26)] == -0.504


def test_fred_download_headers_do_not_send_browser_user_agent() -> None:
    headers = market_top_risk._download_headers("https://fred.stlouisfed.org/graph/fredgraph.csv?id=NFCI")

    assert "User-Agent" not in headers
    assert headers["Connection"] == "close"


def test_nasdaq_download_headers_send_browser_user_agent() -> None:
    headers = market_top_risk._download_headers("https://api.nasdaq.com/api/quote/SPY/historical")

    assert headers["User-Agent"] == market_top_risk.USER_AGENT
    assert headers["Origin"] == "https://www.nasdaq.com"


def test_build_market_top_risk_snapshots_continues_when_fred_unavailable(monkeypatch) -> None:
    start = dt.date(2025, 1, 3)
    monkeypatch.setattr(market_top_risk, "START_DATE", start)
    monkeypatch.setattr(
        market_top_risk,
        "_fetch_fred_series",
        lambda _series_id: (_ for _ in ()).throw(RuntimeError("fred timeout")),
    )

    days = [start + dt.timedelta(days=idx) for idx in range((dt.date.today() - start).days + 1)]

    def fake_nasdaq_price(symbol: str, _assetclass: str, _end_date: dt.date) -> dict[dt.date, float]:
        base = {
            "NDX": 10000.0,
            "SPY": 500.0,
            "RSP": 500.0,
            "QQQ": 400.0,
            "QQEW": 400.0,
            "SOXX": 300.0,
            "XLY": 220.0,
            "XLP": 80.0,
            "IWM": 210.0,
        }[symbol]
        drift = {
            "NDX": 20.0,
            "SPY": 1.1,
            "RSP": 0.7,
            "QQQ": 1.0,
            "QQEW": 0.6,
            "SOXX": 1.3,
            "XLY": 0.5,
            "XLP": 0.2,
            "IWM": 0.4,
        }[symbol]
        return {day: base + (idx * drift) for idx, day in enumerate(days)}

    def fake_yahoo_price(symbol: str, _end_date: dt.date) -> dict[dt.date, float]:
        base = {
            "588200.SS": 2.0,
            "588120.SS": 1.0,
            "588000.SS": 1.2,
            "159915.SZ": 2.5,
            "159949.SZ": 1.5,
        }[symbol]
        return {day: base + idx * 0.01 for idx, day in enumerate(days)}

    monkeypatch.setattr(market_top_risk, "_fetch_nasdaq_price", fake_nasdaq_price)
    monkeypatch.setattr(market_top_risk, "_fetch_yahoo_price", fake_yahoo_price)

    snapshots = market_top_risk.build_market_top_risk_snapshots(history_limit=3)

    assert len(snapshots) == 3
    assert snapshots[-1].week == days[-1].isoformat()
    assert snapshots[-1].nasdaq100 is not None
    assert snapshots[-1].breadth_weakness_score is not None
    assert snapshots[-1].breakage_score is not None
    assert snapshots[-1].signals["soxx_qqq_weakness_score"]["value"] is not None
    assert snapshots[-1].metrics["markets"]["us_semis"]["state"] in {
        "healthy_rally",
        "crowded_rally",
        "ordinary_pullback",
        "top_risk",
        "breakdown_confirmed",
    }


def test_build_market_top_risk_snapshots_keeps_other_fred_series_when_one_fails(monkeypatch) -> None:
    start = dt.date.today() - dt.timedelta(days=560)
    start = market_top_risk._week_end(start)
    monkeypatch.setattr(market_top_risk, "START_DATE", start)
    days = [start + dt.timedelta(days=idx) for idx in range((dt.date.today() - start).days + 1)]

    def fake_fred_series(series_id: str) -> dict[dt.date, float]:
        if series_id == "NFCI":
            raise RuntimeError("nfci timeout")
        base = 1.0 if series_id == "BAA10Y" else -0.5
        return {day: base + (idx * 0.01) for idx, day in enumerate(days)}

    def fake_nasdaq_price(symbol: str, _assetclass: str, _end_date: dt.date) -> dict[dt.date, float]:
        base = {
            "NDX": 10000.0,
            "SPY": 500.0,
            "RSP": 500.0,
            "QQQ": 400.0,
            "QQEW": 400.0,
            "SOXX": 300.0,
            "XLY": 220.0,
            "XLP": 80.0,
            "IWM": 210.0,
        }[symbol]
        return {day: base + idx for idx, day in enumerate(days)}

    def fake_yahoo_price(symbol: str, _end_date: dt.date) -> dict[dt.date, float]:
        base = {
            "588200.SS": 2.0,
            "588120.SS": 1.0,
            "588000.SS": 1.2,
            "159915.SZ": 2.5,
            "159949.SZ": 1.5,
        }[symbol]
        return {day: base + idx * 0.01 for idx, day in enumerate(days)}

    monkeypatch.setattr(market_top_risk, "_fetch_fred_series", fake_fred_series)
    monkeypatch.setattr(market_top_risk, "_fetch_nasdaq_price", fake_nasdaq_price)
    monkeypatch.setattr(market_top_risk, "_fetch_yahoo_price", fake_yahoo_price)

    snapshots = market_top_risk.build_market_top_risk_snapshots(history_limit=3)
    latest = snapshots[-1]

    assert latest.signals["china_star100_star50_weakness_score"]["value"] is not None
    assert latest.signals["china_chinext_100_50_weakness_score"]["value"] is not None
    assert latest.metrics["markets"]["china_star"]["price_symbol"] == "588200.SH"
