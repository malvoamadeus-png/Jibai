from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import math
import sys
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from packages.public_app import market_top_risk as risk  # noqa: E402


OUTPUT_DIR = risk.CACHE_DIR.parent / "event_review"
WINDOW_START = dt.date(2025, 10, 1)
MARKET_PROXIES = {
    "SPY": "US large cap",
    "QQQ": "US growth / Nasdaq",
    "IWM": "US small cap",
    "FXI": "China large cap",
    "MCHI": "China broad",
    "KWEB": "China internet",
    "ACWI": "Global equities",
    "EFA": "Developed ex-US",
    "EEM": "Emerging markets",
}
SIGNAL_COLUMNS = [
    "breadth_weakness_score",
    "rsp_spy_13w_rel_pctl",
    "qqew_qqq_13w_rel_pctl",
    "breakage_score",
    "nfci_13w_chg_pctl",
    "anfci_pctl",
    "credit_baa10y_pctl",
    "hyg_shy_weakness_score",
    "vix_vix3m_20d_pctl",
    "xly_xlp_weakness_score",
    "iwm_spy_weakness_score",
    "dfii10_13w_chg_pctl",
    "dtwexbgs_13w_return_pctl",
]


@dataclass
class DrawdownEpisode:
    symbol: str
    label: str
    peak_week: dt.date
    trough_week: dt.date
    peak_value: float
    trough_value: float
    drawdown: float
    rebound_to_latest: float


def _nasdaq_window(symbol: str, from_date: dt.date, to_date: dt.date) -> dict[dt.date, float]:
    params = urllib.parse.urlencode(
        {
            "assetclass": "etf",
            "fromdate": from_date.isoformat(),
            "todate": to_date.isoformat(),
            "limit": "9999",
        }
    )
    url = f"https://api.nasdaq.com/api/quote/{symbol}/historical?{params}"
    raw = risk._download_url(url).decode("utf-8")
    payload = json.loads(raw)
    rows = (((payload.get("data") or {}).get("tradesTable") or {}).get("rows") or [])
    out: dict[dt.date, float] = {}
    for row in rows:
        day = risk._parse_date(str(row.get("date") or ""))
        close = risk._parse_float(row.get("close"))
        if day and close is not None:
            out[day] = close
    if not out:
        raise RuntimeError(f"No Nasdaq window data parsed for {symbol}")
    return dict(sorted(out.items()))


def _daily_ratio_moving_average(
    numerator: dict[dt.date, float],
    denominator: dict[dt.date, float],
    *,
    window: int,
) -> dict[dt.date, float]:
    values: list[tuple[dt.date, float]] = []
    for day in sorted(set(numerator) & set(denominator)):
        denom = denominator.get(day)
        if denom in (None, 0):
            continue
        values.append((day, numerator[day] / denom))
    out: dict[dt.date, float] = {}
    trailing: list[float] = []
    for day, value in values:
        trailing.append(value)
        if len(trailing) > window:
            trailing.pop(0)
        if len(trailing) == window:
            out[day] = sum(trailing) / window
    return out


def _trailing_return(values: list[float | None], lag: int) -> list[float | None]:
    out: list[float | None] = []
    for idx, value in enumerate(values):
        prev = values[idx - lag] if idx >= lag else None
        if value is None or prev in (None, 0):
            out.append(None)
        else:
            out.append(value / prev - 1)
    return out


def _add(rows: list[dict[str, object]], key: str, values: Iterable[object]) -> None:
    for row, value in zip(rows, values):
        row[key] = value


def _build_indicator_rows() -> list[dict[str, object]]:
    end = dt.date.today()
    weeks = risk._all_week_ends(risk.START_DATE, end)
    rows: list[dict[str, object]] = [{"week": week} for week in weeks]

    for key, series_id in {
        **risk.FRED_SERIES,
        "VIXCLS": "VIXCLS",
        "VXVCLS": "VXVCLS",
        "DFII10": "DFII10",
        "DTWEXBGS": "DTWEXBGS",
    }.items():
        series = risk._fetch_fred_series(series_id)
        _add(rows, key.lower(), risk._weekly_asof(series, weeks, max_stale_days=risk.FRED_CACHE_MAX_STALE_DAYS))

    price_symbols = {
        **risk.NASDAQ_PRICE_SERIES,
        "HYG": ("etf", "px_hyg"),
        "SHY": ("etf", "px_shy"),
        "XLY": ("etf", "px_xly"),
        "XLP": ("etf", "px_xlp"),
        "IWM": ("etf", "px_iwm"),
    }
    for symbol, (assetclass, row_key) in price_symbols.items():
        series = risk._fetch_nasdaq_price(symbol, assetclass, end)
        _add(rows, row_key, risk._weekly_asof(series, weeks, max_stale_days=14))

    vix_ma = _daily_ratio_moving_average(
        risk._fetch_fred_series("VIXCLS"),
        risk._fetch_fred_series("VXVCLS"),
        window=20,
    )
    _add(rows, "vix_vix3m_20d", risk._weekly_asof(vix_ma, weeks, max_stale_days=21))

    feature_inputs = {
        "credit_baa10y_pctl": [risk._parse_float(row.get("baa10y")) for row in rows],
        "nfci_13w_chg_pctl": risk._trailing_change([risk._parse_float(row.get("nfci")) for row in rows], 13),
        "anfci_pctl": [risk._parse_float(row.get("anfci")) for row in rows],
        "rsp_spy_13w_rel_pctl": risk._rel_return(rows, "RSP", "SPY"),
        "qqew_qqq_13w_rel_pctl": risk._rel_return(rows, "QQEW", "QQQ"),
        "hyg_shy_13w_rel_pctl": risk._rel_return(rows, "HYG", "SHY"),
        "xly_xlp_13w_rel_pctl": risk._rel_return(rows, "XLY", "XLP"),
        "iwm_spy_13w_rel_pctl": risk._rel_return(rows, "IWM", "SPY"),
        "vix_vix3m_20d_pctl": [risk._parse_float(row.get("vix_vix3m_20d")) for row in rows],
        "dfii10_13w_chg_pctl": risk._trailing_change([risk._parse_float(row.get("dfii10")) for row in rows], 13),
        "dtwexbgs_13w_return_pctl": _trailing_return([risk._parse_float(row.get("dtwexbgs")) for row in rows], 13),
    }
    for name, values in feature_inputs.items():
        raw_name = name[:-5] if name.endswith("_pctl") else f"{name}_raw"
        _add(rows, raw_name, values)
        _add(rows, name, risk._expanding_percentile(values))

    for row in rows:
        rsp = risk._parse_float(row.get("rsp_spy_13w_rel_pctl"))
        qqew = risk._parse_float(row.get("qqew_qqq_13w_rel_pctl"))
        breakage = [
            risk._parse_float(row.get("credit_baa10y_pctl")),
            risk._parse_float(row.get("nfci_13w_chg_pctl")),
            risk._parse_float(row.get("anfci_pctl")),
        ]
        row["breadth_weakness_score"] = risk._mean([None if rsp is None else 1 - rsp, None if qqew is None else 1 - qqew])
        row["breakage_score"] = risk._mean(breakage)
        for src, dest in [
            ("hyg_shy_13w_rel_pctl", "hyg_shy_weakness_score"),
            ("xly_xlp_13w_rel_pctl", "xly_xlp_weakness_score"),
            ("iwm_spy_13w_rel_pctl", "iwm_spy_weakness_score"),
        ]:
            value = risk._parse_float(row.get(src))
            row[dest] = None if value is None else 1 - value

    return rows


def _signal_active(name: str, value: float | None) -> bool:
    if value is None:
        return False
    if name in {"rsp_spy_13w_rel_pctl", "qqew_qqq_13w_rel_pctl"}:
        return value <= 0.20
    return value >= 0.80 if name not in {"breadth_weakness_score", "breakage_score"} else value >= 0.70


def _signal_watch(name: str, value: float | None) -> bool:
    if value is None:
        return False
    if name in {"rsp_spy_13w_rel_pctl", "qqew_qqq_13w_rel_pctl"}:
        return value <= 0.30
    return value >= 0.70 if name not in {"breadth_weakness_score", "breakage_score"} else value >= 0.60


def _weekly_market_prices() -> dict[str, list[tuple[dt.date, float]]]:
    end = dt.date.today()
    weeks = risk._all_week_ends(WINDOW_START, end)
    out: dict[str, list[tuple[dt.date, float]]] = {}
    for symbol in MARKET_PROXIES:
        series = _nasdaq_window(symbol, WINDOW_START, end)
        values = risk._weekly_asof(series, weeks, max_stale_days=14)
        out[symbol] = [(week, value) for week, value in zip(weeks, values) if value is not None]
    return out


def _max_drawdown_episode(symbol: str, label: str, weekly: list[tuple[dt.date, float]]) -> DrawdownEpisode | None:
    if not weekly:
        return None
    peak_week, peak_value = weekly[0]
    best: DrawdownEpisode | None = None
    latest_value = weekly[-1][1]
    for week, value in weekly:
        if value > peak_value:
            peak_week, peak_value = week, value
        drawdown = value / peak_value - 1
        if best is None or drawdown < best.drawdown:
            best = DrawdownEpisode(
                symbol=symbol,
                label=label,
                peak_week=peak_week,
                trough_week=week,
                peak_value=peak_value,
                trough_value=value,
                drawdown=drawdown,
                rebound_to_latest=latest_value / value - 1 if value else math.nan,
            )
    return best


def _local_drawdown_episodes(
    symbol: str,
    label: str,
    weekly: list[tuple[dt.date, float]],
    *,
    threshold: float = -0.05,
    lookahead_weeks: int = 8,
) -> list[DrawdownEpisode]:
    episodes: list[DrawdownEpisode] = []
    if len(weekly) < 4:
        return episodes
    latest_value = weekly[-1][1]
    for idx, (peak_week, peak_value) in enumerate(weekly[:-1]):
        left = [value for _, value in weekly[max(0, idx - 2) : idx + 1]]
        right = [value for _, value in weekly[idx : min(len(weekly), idx + 2)]]
        if peak_value < max(left + right):
            continue
        window = weekly[idx + 1 : min(len(weekly), idx + 1 + lookahead_weeks)]
        if not window:
            continue
        trough_week, trough_value = min(window, key=lambda item: item[1])
        drawdown = trough_value / peak_value - 1
        if drawdown <= threshold:
            episodes.append(
                DrawdownEpisode(
                    symbol=symbol,
                    label=label,
                    peak_week=peak_week,
                    trough_week=trough_week,
                    peak_value=peak_value,
                    trough_value=trough_value,
                    drawdown=drawdown,
                    rebound_to_latest=latest_value / trough_value - 1 if trough_value else math.nan,
                )
            )
    return _dedupe_episodes(episodes)


def _dedupe_episodes(episodes: list[DrawdownEpisode]) -> list[DrawdownEpisode]:
    selected: list[DrawdownEpisode] = []
    for episode in sorted(episodes, key=lambda item: item.drawdown):
        overlaps = any(
            episode.symbol == kept.symbol
            and episode.peak_week <= kept.trough_week
            and episode.trough_week >= kept.peak_week
            for kept in selected
        )
        if not overlaps:
            selected.append(episode)
    return sorted(selected, key=lambda item: (item.trough_week, item.symbol))


def _row_by_week(rows: list[dict[str, object]]) -> dict[dt.date, dict[str, object]]:
    return {row["week"]: row for row in rows if isinstance(row.get("week"), dt.date)}


def _nearest_week_on_or_before(rows_by_week: dict[dt.date, dict[str, object]], day: dt.date) -> dt.date | None:
    candidates = [week for week in rows_by_week if week <= day]
    return max(candidates) if candidates else None


def _review_episode(episode: DrawdownEpisode, rows_by_week: dict[dt.date, dict[str, object]]) -> dict[str, object]:
    lookback_start = episode.peak_week - dt.timedelta(days=28)
    lookback_weeks = sorted(week for week in rows_by_week if lookback_start <= week <= episode.peak_week)
    active: list[str] = []
    watch: list[str] = []
    peak_week = _nearest_week_on_or_before(rows_by_week, episode.peak_week)
    peak_row = rows_by_week[peak_week] if peak_week else {}
    for name in SIGNAL_COLUMNS:
        values = [risk._parse_float(rows_by_week[week].get(name)) for week in lookback_weeks]
        if any(_signal_active(name, value) for value in values):
            active.append(name)
        elif any(_signal_watch(name, value) for value in values):
            watch.append(name)
    return {
        "symbol": episode.symbol,
        "market": episode.label,
        "peak_week": episode.peak_week.isoformat(),
        "trough_week": episode.trough_week.isoformat(),
        "drawdown_pct": round(episode.drawdown * 100, 2),
        "rebound_to_latest_pct": round(episode.rebound_to_latest * 100, 2),
        "active_pre_warning": ", ".join(active) or "-",
        "watch_pre_warning": ", ".join(watch) or "-",
        "peak_breadth_weakness": _round(peak_row.get("breadth_weakness_score")),
        "peak_breakage": _round(peak_row.get("breakage_score")),
        "peak_hyg_shy_weakness": _round(peak_row.get("hyg_shy_weakness_score")),
        "peak_vix_term": _round(peak_row.get("vix_vix3m_20d_pctl")),
        "peak_xly_xlp_weakness": _round(peak_row.get("xly_xlp_weakness_score")),
        "peak_iwm_spy_weakness": _round(peak_row.get("iwm_spy_weakness_score")),
        "peak_real_rate": _round(peak_row.get("dfii10_13w_chg_pctl")),
        "peak_dollar": _round(peak_row.get("dtwexbgs_13w_return_pctl")),
    }


def _round(value: object) -> float | None:
    parsed = risk._parse_float(value)
    return None if parsed is None else round(parsed, 3)


def _write_outputs(rows: list[dict[str, object]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _markdown(rows: list[dict[str, object]], latest_signals: dict[str, object]) -> str:
    lines = [
        "# Market Top Risk Event Review",
        "",
        f"Generated at: {dt.datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Latest Signal Snapshot",
        "",
        "| Signal | Value | Active | Watch |",
        "| --- | ---: | --- | --- |",
    ]
    for name, value in latest_signals.items():
        parsed = risk._parse_float(value)
        lines.append(
            f"| {name} | {'-' if parsed is None else f'{parsed:.3f}'} | "
            f"{str(_signal_active(name, parsed)).lower()} | {str(_signal_watch(name, parsed)).lower()} |"
        )
    lines.extend(
        [
            "",
            "## Drawdown Episodes",
            "",
            "| Symbol | Market | Peak | Trough | Drawdown | Rebound to latest | Active before peak | Watch before peak |",
            "| --- | --- | --- | --- | ---: | ---: | --- | --- |",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row['symbol']} | {row['market']} | {row['peak_week']} | {row['trough_week']} | "
            f"{row['drawdown_pct']}% | {row['rebound_to_latest_pct']}% | "
            f"{row['active_pre_warning']} | {row['watch_pre_warning']} |"
        )
    lines.append("")
    return "\n".join(lines)


def run(output_dir: Path) -> int:
    indicator_rows = _build_indicator_rows()
    rows_by_week = _row_by_week(indicator_rows)
    market_prices = _weekly_market_prices()
    episodes: list[DrawdownEpisode] = []
    for symbol, prices in market_prices.items():
        episodes.extend(_local_drawdown_episodes(symbol, MARKET_PROXIES[symbol], prices))
    reviewed = [_review_episode(episode, rows_by_week) for episode in episodes]
    latest = max(rows_by_week)
    latest_row = rows_by_week[latest]
    latest_signals = {name: latest_row.get(name) for name in SIGNAL_COLUMNS}

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_outputs(reviewed, output_dir / "event-review.csv")
    (output_dir / "event-review.md").write_text(_markdown(reviewed, latest_signals), encoding="utf-8")
    (output_dir / "event-review.json").write_text(
        json.dumps(
            {
                "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
                "latest_week": latest.isoformat(),
                "latest_signals": latest_signals,
                "episodes": reviewed,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print((output_dir / "event-review.md").read_text(encoding="utf-8"))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Review whether market top-risk signals warned before recent drawdowns.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    return run(args.output_dir)


if __name__ == "__main__":
    raise SystemExit(main())
