from __future__ import annotations

import datetime as dt

from packages.public_app import market_top_risk


def test_build_market_top_risk_snapshots_continues_when_fred_unavailable(monkeypatch) -> None:
    start = dt.date(2025, 1, 3)
    monkeypatch.setattr(market_top_risk, "START_DATE", start)
    monkeypatch.setattr(
        market_top_risk,
        "_fetch_fred_series",
        lambda _series_id: (_ for _ in ()).throw(RuntimeError("fred timeout")),
    )

    weeks = market_top_risk._all_week_ends(start, dt.date.today())

    def fake_nasdaq_price(symbol: str, _assetclass: str, _end_date: dt.date) -> dict[dt.date, float]:
        base = {
            "NDX": 10000.0,
            "SPY": 500.0,
            "RSP": 500.0,
            "QQQ": 400.0,
            "QQEW": 400.0,
        }[symbol]
        drift = {
            "NDX": 20.0,
            "SPY": 1.1,
            "RSP": 0.7,
            "QQQ": 1.0,
            "QQEW": 0.6,
        }[symbol]
        return {week: base + (idx * drift) for idx, week in enumerate(weeks)}

    monkeypatch.setattr(market_top_risk, "_fetch_nasdaq_price", fake_nasdaq_price)

    snapshots = market_top_risk.build_market_top_risk_snapshots(history_limit=3)

    assert len(snapshots) == 3
    assert snapshots[-1].week == weeks[-1].isoformat()
    assert snapshots[-1].nasdaq100 is not None
    assert snapshots[-1].breadth_weakness_score is not None
    assert snapshots[-1].breakage_score is None
    assert snapshots[-1].signals["nfci_13w_chg_pctl"]["value"] is None
