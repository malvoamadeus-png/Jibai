from __future__ import annotations

import csv
import datetime as dt
import io
import json
import math
import os
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv

from packages.common.models import MarketTopRiskSnapshot
from packages.common.paths import get_paths
from packages.common.postgres_database import PostgresInsightStore, postgres_connection


CACHE_DIR = get_paths().runtime_dir / "market_top_risk" / "cache"
START_DATE = dt.date(2004, 1, 1)
FRED_SERIES = {
    "NASDAQ100": "NASDAQ100",
    "NFCI": "NFCI",
    "ANFCI": "ANFCI",
    "BAA10Y": "BAA10Y",
}
NASDAQ_SYMBOLS = {
    "SPY": "etf",
    "RSP": "etf",
    "QQQ": "etf",
    "QQEW": "etf",
}
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _request_timeout() -> tuple[float, float]:
    connect = float(os.getenv("PUBLIC_WORKER_TOP_RISK_CONNECT_TIMEOUT_SECONDS", "20"))
    read = float(os.getenv("PUBLIC_WORKER_TOP_RISK_READ_TIMEOUT_SECONDS", "120"))
    return (max(5.0, connect), max(30.0, read))


def _parse_date(raw: str) -> dt.date | None:
    text = raw.strip()
    if not text or text in {".", "N/A", "NA", "null"}:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def _parse_float(raw: object) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip().replace("$", "").replace(",", "").replace("%", "")
    if not text or text in {".", "N/A", "NA", "null", "--"}:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return None if math.isnan(value) or math.isinf(value) else value


def _week_end(day: dt.date) -> dt.date:
    return day + dt.timedelta(days=(4 - day.weekday()) % 7)


def _all_week_ends(start: dt.date, end: dt.date) -> list[dt.date]:
    current = _week_end(start)
    weeks: list[dt.date] = []
    while current <= end:
        weeks.append(current)
        current += dt.timedelta(days=7)
    return weeks


def _fetch_url(url: str, cache_name: str, *, max_age_hours: int = 24) -> bytes:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / cache_name
    if path.exists() and time.time() - path.stat().st_mtime < max_age_hours * 3600:
        return path.read_bytes()

    headers = {"User-Agent": USER_AGENT, "Connection": "close"}
    if "nasdaq.com" in url:
        headers.update(
            {
                "Accept": "application/json,text/plain,*/*",
                "Origin": "https://www.nasdaq.com",
                "Referer": "https://www.nasdaq.com/",
            }
        )
    last_exc: Exception | None = None
    for attempt in range(1, 4):
        try:
            if os.getenv("PUBLIC_WORKER_TOP_RISK_USE_CURL", "true").lower() != "false":
                data = _fetch_url_with_curl(url)
            else:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=_request_timeout()[1]) as resp:
                    data = resp.read()
            path.write_bytes(data)
            return data
        except Exception as exc:
            last_exc = exc
            if attempt < 3:
                time.sleep(2 * attempt)
    raise RuntimeError(f"Fetch failed for {url}: {last_exc}") from last_exc


def _fetch_url_with_curl(url: str) -> bytes:
    curl_path = shutil.which("curl")
    if not curl_path:
        raise RuntimeError("curl is not available")
    connect_timeout, read_timeout = _request_timeout()
    result = subprocess.run(
        [
            curl_path,
            "-L",
            "--fail",
            "--silent",
            "--show-error",
            "--http1.1",
            "--retry",
            "3",
            "--retry-delay",
            "2",
            "--connect-timeout",
            str(int(connect_timeout)),
            "--max-time",
            str(int(read_timeout)),
            "--user-agent",
            USER_AGENT,
            url,
        ],
        check=True,
        capture_output=True,
    )
    return result.stdout


def _fetch_fred_series(series_id: str) -> dict[dt.date, float]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={urllib.parse.quote(series_id)}"
    text = _fetch_url(url, f"fred_{series_id}.csv").decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    out: dict[dt.date, float] = {}
    for row in reader:
        day = _parse_date(row.get("observation_date", ""))
        value = _parse_float(row.get(series_id))
        if day and value is not None:
            out[day] = value
    if not out:
        raise RuntimeError(f"No FRED data parsed for {series_id}")
    return dict(sorted(out.items()))


def _fetch_nasdaq_price(symbol: str, assetclass: str, end_date: dt.date) -> dict[dt.date, float]:
    params = urllib.parse.urlencode(
        {
            "assetclass": assetclass,
            "fromdate": START_DATE.isoformat(),
            "todate": end_date.isoformat(),
            "limit": "9999",
        }
    )
    url = f"https://api.nasdaq.com/api/quote/{symbol}/historical?{params}"
    raw = _fetch_url(url, f"nasdaq_{symbol}.json").decode("utf-8")
    payload = json.loads(raw)
    rows = (((payload.get("data") or {}).get("tradesTable") or {}).get("rows") or [])
    out: dict[dt.date, float] = {}
    for row in rows:
        day = _parse_date(str(row.get("date") or ""))
        close = _parse_float(row.get("close"))
        if day and close is not None:
            out[day] = close
    if not out:
        raise RuntimeError(f"No Nasdaq price data parsed for {symbol}")
    return dict(sorted(out.items()))


def _weekly_asof(
    series: dict[dt.date, float],
    weeks: list[dt.date],
    *,
    max_stale_days: int | None = None,
) -> list[float | None]:
    items = sorted(series.items())
    idx = 0
    last: float | None = None
    last_day: dt.date | None = None
    out: list[float | None] = []
    for week in weeks:
        while idx < len(items) and items[idx][0] <= week:
            last_day = items[idx][0]
            last = items[idx][1]
            idx += 1
        if max_stale_days is not None and last_day is not None and (week - last_day).days > max_stale_days:
            out.append(None)
        else:
            out.append(last)
    return out


def _percentile_rank(history: list[float], value: float | None) -> float | None:
    if value is None or len(history) < 52:
        return None
    less = sum(1 for item in history if item < value)
    equal = sum(1 for item in history if item == value)
    return (less + 0.5 * equal) / len(history)


def _expanding_percentile(values: list[float | None]) -> list[float | None]:
    history: list[float] = []
    out: list[float | None] = []
    for value in values:
        out.append(_percentile_rank(history, value))
        if value is not None:
            history.append(value)
    return out


def _trailing_change(values: list[float | None], lag: int) -> list[float | None]:
    out: list[float | None] = []
    for idx, value in enumerate(values):
        prev = values[idx - lag] if idx >= lag else None
        out.append(value - prev if value is not None and prev is not None else None)
    return out


def _rel_return(
    rows: list[dict[str, object]],
    sym_a: str,
    sym_b: str,
    *,
    lag: int = 13,
) -> list[float | None]:
    a = [_parse_float(row.get(f"px_{sym_a.lower()}")) for row in rows]
    b = [_parse_float(row.get(f"px_{sym_b.lower()}")) for row in rows]
    out: list[float | None] = []
    for idx in range(len(rows)):
        if idx < lag or a[idx] is None or b[idx] is None or a[idx - lag] is None or b[idx - lag] is None:
            out.append(None)
            continue
        out.append((a[idx] / a[idx - lag] - 1) - (b[idx] / b[idx - lag] - 1))
    return out


def _add_series(rows: list[dict[str, object]], name: str, values: Iterable[object]) -> None:
    for row, value in zip(rows, values):
        row[name] = value


def _mean(values: list[float | None]) -> float | None:
    valid = [item for item in values if item is not None]
    return sum(valid) / len(valid) if valid else None


def _signal(name: str, value: float | None) -> bool:
    if value is None:
        return False
    if name in {"rsp_spy_13w_rel_pctl", "qqew_qqq_13w_rel_pctl"}:
        return value <= 0.20
    if name in {"breadth_weakness_score", "breakage_score"}:
        return value >= 0.70
    return value >= 0.80


def _risk_level(*, warning_active: bool, confirmation_active: bool, risk_score: float) -> str:
    if warning_active and confirmation_active:
        return "high"
    if warning_active or confirmation_active:
        return "elevated" if risk_score >= 0.70 else "watch"
    return "watch" if risk_score >= 0.60 else "low"


def build_market_top_risk_snapshots(*, history_limit: int = 90) -> list[MarketTopRiskSnapshot]:
    end_date = dt.date.today()
    weeks = _all_week_ends(START_DATE, end_date)
    rows: list[dict[str, object]] = [{"week": week.isoformat()} for week in weeks]

    fred = {key: _fetch_fred_series(series_id) for key, series_id in FRED_SERIES.items()}
    for key, series in fred.items():
        _add_series(rows, key.lower(), _weekly_asof(series, weeks, max_stale_days=21))

    for symbol, assetclass in NASDAQ_SYMBOLS.items():
        series = _fetch_nasdaq_price(symbol, assetclass, end_date)
        _add_series(rows, f"px_{symbol.lower()}", _weekly_asof(series, weeks, max_stale_days=14))

    ndx = [_parse_float(row.get("nasdaq100")) for row in rows]
    dd_from_high: list[float | None] = []
    for idx, value in enumerate(ndx):
        window = [item for item in ndx[max(0, idx - 51) : idx + 1] if item is not None]
        high = max(window) if window else None
        dd_from_high.append(value / high - 1 if value is not None and high not in (None, 0) else None)
    _add_series(rows, "ndx_dd_from_52w_high", dd_from_high)

    feature_inputs = {
        "credit_baa10y_pctl": [_parse_float(row.get("baa10y")) for row in rows],
        "nfci_13w_chg_pctl": _trailing_change([_parse_float(row.get("nfci")) for row in rows], 13),
        "anfci_pctl": [_parse_float(row.get("anfci")) for row in rows],
        "rsp_spy_13w_rel_pctl": _rel_return(rows, "RSP", "SPY"),
        "qqew_qqq_13w_rel_pctl": _rel_return(rows, "QQEW", "QQQ"),
    }
    for name, values in feature_inputs.items():
        raw_name = name[:-5] if name.endswith("_pctl") else f"{name}_raw"
        _add_series(rows, raw_name, values)
        _add_series(rows, name, _expanding_percentile(values))

    for row in rows:
        breadth_values = [
            _parse_float(row.get("rsp_spy_13w_rel_pctl")),
            _parse_float(row.get("qqew_qqq_13w_rel_pctl")),
        ]
        breakage_values = [
            _parse_float(row.get("credit_baa10y_pctl")),
            _parse_float(row.get("nfci_13w_chg_pctl")),
            _parse_float(row.get("anfci_pctl")),
        ]
        breadth_mean = _mean(breadth_values)
        row["breadth_weakness_score"] = 1 - breadth_mean if breadth_mean is not None else None
        row["breakage_score"] = _mean(breakage_values)

    valid_rows = [row for row in rows if _parse_float(row.get("breadth_weakness_score")) is not None or _parse_float(row.get("breakage_score")) is not None]
    snapshots: list[MarketTopRiskSnapshot] = []
    for row in valid_rows[-max(1, history_limit) :]:
        signals = {
            name: {
                "value": _parse_float(row.get(name)),
                "active": _signal(name, _parse_float(row.get(name))),
                "module": module,
            }
            for name, module in {
                "breadth_weakness_score": "breadth",
                "rsp_spy_13w_rel_pctl": "breadth",
                "qqew_qqq_13w_rel_pctl": "breadth",
                "breakage_score": "financial_conditions_credit",
                "nfci_13w_chg_pctl": "financial_conditions",
                "anfci_pctl": "financial_conditions",
                "credit_baa10y_pctl": "credit",
            }.items()
        }
        warning_active = bool(
            signals["breadth_weakness_score"]["active"]
            or signals["rsp_spy_13w_rel_pctl"]["active"]
            or signals["qqew_qqq_13w_rel_pctl"]["active"]
        )
        confirmation_active = bool(
            signals["breakage_score"]["active"]
            or signals["nfci_13w_chg_pctl"]["active"]
            or signals["anfci_pctl"]["active"]
            or signals["credit_baa10y_pctl"]["active"]
        )
        breadth_score = _parse_float(row.get("breadth_weakness_score")) or 0.0
        breakage_score = _parse_float(row.get("breakage_score")) or 0.0
        risk_score = min(1.0, (0.58 * breadth_score) + (0.42 * breakage_score))
        snapshots.append(
            MarketTopRiskSnapshot(
                week=str(row["week"]),
                nasdaq100=_parse_float(row.get("nasdaq100")),
                ndx_dd_from_52w_high=_parse_float(row.get("ndx_dd_from_52w_high")),
                breadth_weakness_score=_parse_float(row.get("breadth_weakness_score")),
                breakage_score=_parse_float(row.get("breakage_score")),
                risk_score=risk_score,
                risk_level=_risk_level(
                    warning_active=warning_active,
                    confirmation_active=confirmation_active,
                    risk_score=risk_score,
                ),
                warning_active=warning_active,
                confirmation_active=confirmation_active,
                signals=signals,
                metrics={
                    "near_high": (_parse_float(row.get("ndx_dd_from_52w_high")) or -1.0) >= -0.10,
                    "baseline": {
                        "near_high_fwd_26w_avg_drawdown": -0.055,
                        "near_high_fwd_26w_dd10_probability": 0.211,
                    },
                },
                sources={
                    "fred": list(FRED_SERIES.values()),
                    "nasdaq": list(NASDAQ_SYMBOLS.keys()),
                    "method": "weekly Friday as-of, expanding historical percentiles",
                },
            )
        )
    return snapshots


def sync_market_top_risk_once(*, history_limit: int = 90) -> int:
    load_dotenv(".env", override=False)
    try:
        snapshots = build_market_top_risk_snapshots(history_limit=history_limit)
    except Exception as exc:
        print(f"[public-worker] market_top_risk fetch_failed={exc}")
        return 0
    if not snapshots:
        print("[public-worker] market_top_risk no snapshots built")
        return 0
    with postgres_connection() as conn:
        store = PostgresInsightStore(conn)
        for snapshot in snapshots:
            store.upsert_market_top_risk_snapshot(snapshot)
    latest = snapshots[-1]
    print(
        "[public-worker] market_top_risk "
        f"written={len(snapshots)} "
        f"week={latest.week} "
        f"risk_level={latest.risk_level} "
        f"risk_score={latest.risk_score:.3f} "
        f"warning={str(latest.warning_active).lower()} "
        f"confirmation={str(latest.confirmation_active).lower()}"
    )
    return 0
