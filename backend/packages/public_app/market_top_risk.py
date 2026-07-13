from __future__ import annotations

import csv
import datetime as dt
import io
import json
import math
import os
import re
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv

from packages.common.models import MarketTopRiskSnapshot
from packages.common.market_data import fetch_yahoo_daily
from packages.common.paths import get_paths
from packages.common.postgres_database import PostgresInsightStore, postgres_connection


CACHE_DIR = get_paths().runtime_dir / "market_top_risk" / "cache"
START_DATE = dt.date(2004, 1, 1)
FRED_SERIES = {
    "NFCI": "NFCI",
    "ANFCI": "ANFCI",
    "BAA10Y": "BAA10Y",
}
FRED_CACHE_MAX_STALE_DAYS = 21
FRED_REFRESH_LOOKBACK_DAYS = 180
NASDAQ_PRICE_SERIES = {
    "NDX": ("index", "nasdaq100"),
    "SPY": ("etf", "px_spy"),
    "RSP": ("etf", "px_rsp"),
    "QQQ": ("etf", "px_qqq"),
    "QQEW": ("etf", "px_qqew"),
    "SOXX": ("etf", "px_soxx"),
    "XLY": ("etf", "px_xly"),
    "XLP": ("etf", "px_xlp"),
    "IWM": ("etf", "px_iwm"),
}
CHINA_YAHOO_PRICE_SERIES = {
    "588200.SS": "px_588200_sh",
    "588120.SS": "px_588120_ss",
    "588000.SS": "px_588000_ss",
    "159915.SZ": "px_159915_sz",
    "159949.SZ": "px_159949_sz",
}
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
FRED_TABLE_ROW_RE = re.compile(r"#?(\d{4}-\d{2}-\d{2})\s*(?:\|\s*|\s+)([-+]?\d+(?:\.\d+)?|[.])")
TRADING_DAYS_13W = 65


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

    last_exc: Exception | None = None
    for attempt in range(1, 4):
        try:
            data = _download_url(url)
            path.write_bytes(data)
            return data
        except Exception as exc:
            last_exc = exc
            if attempt < 3:
                time.sleep(2 * attempt)
    if path.exists():
        age_hours = (time.time() - path.stat().st_mtime) / 3600
        print(
            "[public-worker] market_top_risk stale_cache "
            f"cache={cache_name} age_hours={age_hours:.1f} fetch_error={last_exc}"
        )
        return path.read_bytes()
    raise RuntimeError(f"Fetch failed for {url}: {last_exc}") from last_exc


def _download_headers(url: str) -> dict[str, str]:
    headers = {"Connection": "close"}
    if "nasdaq.com" in url:
        headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "application/json,text/plain,*/*",
                "Origin": "https://www.nasdaq.com",
                "Referer": "https://www.nasdaq.com/",
            }
        )
    return headers


def _download_url(url: str) -> bytes:
    headers = _download_headers(url)
    if os.getenv("PUBLIC_WORKER_TOP_RISK_USE_CURL", "true").lower() != "false":
        return _fetch_url_with_curl(url, headers=headers)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=_request_timeout()[1]) as resp:
        return resp.read()


def _fetch_url_with_curl(url: str, *, headers: dict[str, str] | None = None) -> bytes:
    curl_path = shutil.which("curl")
    if not curl_path:
        raise RuntimeError("curl is not available")
    connect_timeout, read_timeout = _request_timeout()
    command = [
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
    ]
    for key, value in (headers or {}).items():
        if key.lower() == "user-agent":
            command.extend(["--user-agent", value])
        else:
            command.extend(["--header", f"{key}: {value}"])
    command.append(url)
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
    )
    return result.stdout


def _parse_fred_csv(series_id: str, raw: bytes | str) -> dict[dt.date, float]:
    text = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw
    reader = csv.DictReader(io.StringIO(text))
    out: dict[dt.date, float] = {}
    for row in reader:
        day = _parse_date(row.get("observation_date", ""))
        value = _parse_float(row.get(series_id))
        if day and value is not None:
            out[day] = value
    return dict(sorted(out.items()))


def _parse_fred_table_data(raw: bytes | str) -> dict[dt.date, float]:
    text = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw
    out: dict[dt.date, float] = {}
    for match in FRED_TABLE_ROW_RE.finditer(text):
        value = _parse_float(match.group(2))
        if value is None:
            continue
        day = _parse_date(match.group(1))
        if day:
            out[day] = value
    return dict(sorted(out.items()))


def _parse_fred_payload(series_id: str, raw: bytes | str) -> dict[dt.date, float]:
    csv_rows = _parse_fred_csv(series_id, raw)
    return csv_rows if csv_rows else _parse_fred_table_data(raw)


def _fred_cache_path(series_id: str) -> Path:
    return CACHE_DIR / f"fred_{series_id}.csv"


def _read_fred_cache(series_id: str) -> dict[dt.date, float]:
    path = _fred_cache_path(series_id)
    if not path.exists():
        return {}
    try:
        return _parse_fred_payload(series_id, path.read_bytes())
    except Exception as exc:
        print(f"[public-worker] market_top_risk cache_unreadable source=fred series={series_id} error={exc}")
        return {}


def _write_fred_cache(series_id: str, series: dict[dt.date, float]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["observation_date", series_id])
    for day, value in sorted(series.items()):
        writer.writerow([day.isoformat(), f"{value:g}"])
    _fred_cache_path(series_id).write_text(buffer.getvalue(), encoding="utf-8")


def _fetch_fred_series(series_id: str) -> dict[dt.date, float]:
    cached = _read_fred_cache(series_id)
    latest_cached = max(cached) if cached else None
    if latest_cached:
        start_date = max(START_DATE, latest_cached - dt.timedelta(days=FRED_REFRESH_LOOKBACK_DAYS))
    else:
        start_date = START_DATE
    params = urllib.parse.urlencode({"id": series_id, "cosd": start_date.isoformat()})
    urls = [
        f"https://fred.stlouisfed.org/graph/fredgraph.csv?{params}",
        f"https://fred.stlouisfed.org/data/{urllib.parse.quote(series_id)}",
    ]

    fetch_errors: list[str] = []
    fetched: dict[dt.date, float] = {}
    for url in urls:
        try:
            fetched = _parse_fred_payload(series_id, _download_url(url))
            if fetched:
                break
            fetch_errors.append(f"{url}: no parseable observations")
        except Exception as exc:
            fetch_errors.append(f"{url}: {exc}")
    try:
        if not fetched:
            raise RuntimeError("; ".join(fetch_errors) or "no parseable observations")
    except Exception as exc:
        if cached:
            latest_text = latest_cached.isoformat() if latest_cached else "unknown"
            print(
                "[public-worker] market_top_risk stale_cache "
                f"source=fred series={series_id} latest={latest_text} fetch_error={exc}"
            )
            return cached
        raise RuntimeError(f"Fetch failed for FRED series {series_id}: {exc}") from exc

    out = dict(sorted({**cached, **fetched}.items()))
    if not out:
        raise RuntimeError(f"No FRED data parsed for {series_id}")
    _write_fred_cache(series_id, out)
    print(
        "[public-worker] market_top_risk source_refreshed "
        f"source=fred series={series_id} "
        f"from={min(out).isoformat()} to={max(out).isoformat()} "
        f"rows={len(out)}"
    )
    return out


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


def _fetch_yahoo_price(symbol: str, end_date: dt.date) -> dict[dt.date, float]:
    payload = fetch_yahoo_daily(symbol=symbol, days=5000)
    out: dict[dt.date, float] = {}
    for candle in payload.get("candles") or []:
        day = _parse_date(str(candle.get("date") or ""))
        close = _parse_float(candle.get("close"))
        if day and day <= end_date and close is not None:
            out[day] = close
    if not out:
        raise RuntimeError(str(payload.get("message") or f"No Yahoo price data parsed for {symbol}"))
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


def _daily_asof(
    series: dict[dt.date, float],
    dates: list[dt.date],
    *,
    max_stale_days: int | None = None,
) -> list[float | None]:
    items = sorted(series.items())
    idx = 0
    last: float | None = None
    last_day: dt.date | None = None
    out: list[float | None] = []
    for day in dates:
        while idx < len(items) and items[idx][0] <= day:
            last_day = items[idx][0]
            last = items[idx][1]
            idx += 1
        if max_stale_days is not None and last_day is not None and (day - last_day).days > max_stale_days:
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


def _rel_return_by_keys(
    rows: list[dict[str, object]],
    key_a: str,
    key_b: str,
    *,
    lag: int = TRADING_DAYS_13W,
) -> list[float | None]:
    a = [_parse_float(row.get(key_a)) for row in rows]
    b = [_parse_float(row.get(key_b)) for row in rows]
    out: list[float | None] = []
    for idx in range(len(rows)):
        if idx < lag or a[idx] is None or b[idx] is None or a[idx - lag] in (None, 0) or b[idx - lag] in (None, 0):
            out.append(None)
            continue
        out.append((a[idx] / a[idx - lag] - 1) - (b[idx] / b[idx - lag] - 1))
    return out


def _moving_average(values: list[float | None], window: int) -> list[float | None]:
    out: list[float | None] = []
    for idx in range(len(values)):
        window_values = [item for item in values[max(0, idx - window + 1) : idx + 1] if item is not None]
        out.append(sum(window_values) / len(window_values) if len(window_values) == window else None)
    return out


def _price_weakness_scores(rows: list[dict[str, object]], price_key: str, output_key: str) -> None:
    prices = [_parse_float(row.get(price_key)) for row in rows]
    ma20 = _moving_average(prices, 20)
    ma50 = _moving_average(prices, 50)
    scores: list[float | None] = []
    for idx, price in enumerate(prices):
        if price is None:
            scores.append(None)
            continue
        recent = [item for item in prices[max(0, idx - 19) : idx + 1] if item is not None]
        high20 = max(recent) if len(recent) == 20 else None
        dd20 = price / high20 - 1 if high20 not in (None, 0) else None
        ma20_value = ma20[idx]
        ma50_value = ma50[idx]
        ma20_prev = ma20[idx - 5] if idx >= 5 else None
        components = [
            dd20 is not None and dd20 <= -0.05,
            ma20_value is not None and price < ma20_value,
            ma50_value is not None and price < ma50_value,
            ma20_value is not None and ma20_prev is not None and ma20_value < ma20_prev,
        ]
        scores.append(sum(0.25 for item in components if item))
    _add_series(rows, output_key, scores)


def _add_series(rows: list[dict[str, object]], name: str, values: Iterable[object]) -> None:
    for row, value in zip(rows, values):
        row[name] = value


def _mean(values: list[float | None]) -> float | None:
    valid = [item for item in values if item is not None]
    return sum(valid) / len(valid) if valid else None


def _confirmed_flags(values: list[float | None], *, threshold: float, lookback: int = 3, required: int = 2) -> list[bool]:
    out: list[bool] = []
    for idx in range(len(values)):
        recent = values[max(0, idx - lookback + 1) : idx + 1]
        out.append(sum(1 for item in recent if item is not None and item >= threshold) >= required)
    return out


def _recent_true(flags: list[bool], idx: int, *, window: int) -> bool:
    return any(flags[max(0, idx - window + 1) : idx + 1])


def _persistent_true(flags: list[bool], idx: int, *, window: int = 10, required: int = 7) -> bool:
    recent = flags[max(0, idx - window + 1) : idx + 1]
    return sum(1 for item in recent if item) >= required


def _market_state(
    *,
    structure_confirmed: bool,
    structure_recent: bool,
    price_confirmed: bool,
    price_persistent: bool,
) -> str:
    if structure_recent and price_persistent:
        return "breakdown_confirmed"
    if structure_recent and price_confirmed:
        return "top_risk"
    if structure_confirmed:
        return "crowded_rally"
    if price_confirmed:
        return "ordinary_pullback"
    return "healthy_rally"


def _risk_level_from_state(state: str, risk_score: float) -> str:
    if state == "breakdown_confirmed":
        return "high"
    if state == "top_risk":
        return "elevated"
    if state in {"crowded_rally", "ordinary_pullback"}:
        return "watch" if risk_score < 0.70 else "elevated"
    return "watch" if risk_score >= 0.60 else "low"


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
    price_series: dict[str, dict[dt.date, float]] = {}
    for symbol, (assetclass, row_key) in NASDAQ_PRICE_SERIES.items():
        series = _fetch_nasdaq_price(symbol, assetclass, end_date)
        price_series[row_key] = series
    for symbol, row_key in CHINA_YAHOO_PRICE_SERIES.items():
        try:
            price_series[row_key] = _fetch_yahoo_price(symbol, end_date)
        except Exception as exc:
            print(f"[public-worker] market_top_risk source_unavailable source=yahoo symbol={symbol} error={exc}")
            price_series[row_key] = {}

    dates = sorted({day for series in price_series.values() for day in series})
    rows: list[dict[str, object]] = [{"week": day.isoformat(), "date": day.isoformat()} for day in dates]
    for row_key, series in price_series.items():
        _add_series(rows, row_key, _daily_asof(series, dates, max_stale_days=5))

    ndx = [_parse_float(row.get("nasdaq100")) for row in rows]
    dd_from_high: list[float | None] = []
    for idx, value in enumerate(ndx):
        window = [item for item in ndx[max(0, idx - 51) : idx + 1] if item is not None]
        high = max(window) if window else None
        dd_from_high.append(value / high - 1 if value is not None and high not in (None, 0) else None)
    _add_series(rows, "ndx_dd_from_52w_high", dd_from_high)

    feature_inputs = {
        "rsp_spy_13w_rel_pctl": _rel_return_by_keys(rows, "px_rsp", "px_spy"),
        "qqew_qqq_13w_rel_pctl": _rel_return_by_keys(rows, "px_qqew", "px_qqq"),
        "soxx_qqq_13w_rel_pctl": _rel_return_by_keys(rows, "px_soxx", "px_qqq"),
        "xly_xlp_13w_rel_pctl": _rel_return_by_keys(rows, "px_xly", "px_xlp"),
        "iwm_spy_13w_rel_pctl": _rel_return_by_keys(rows, "px_iwm", "px_spy"),
        "china_star100_star50_13w_rel_pctl": _rel_return_by_keys(rows, "px_588120_ss", "px_588000_ss"),
        "china_chinext_100_50_13w_rel_pctl": _rel_return_by_keys(rows, "px_159915_sz", "px_159949_sz"),
    }
    for name, values in feature_inputs.items():
        raw_name = name[:-5] if name.endswith("_pctl") else f"{name}_raw"
        _add_series(rows, raw_name, values)
        _add_series(rows, name, _expanding_percentile(values))

    _price_weakness_scores(rows, "px_soxx", "us_price_weakness_score")
    _price_weakness_scores(rows, "px_588200_sh", "china_price_weakness_score")

    for row in rows:
        us_structure_values = [
            None if (value := _parse_float(row.get(name))) is None else 1 - value
            for name in [
                "rsp_spy_13w_rel_pctl",
                "qqew_qqq_13w_rel_pctl",
                "soxx_qqq_13w_rel_pctl",
                "xly_xlp_13w_rel_pctl",
                "iwm_spy_13w_rel_pctl",
            ]
        ]
        china_structure_values = [
            None if (value := _parse_float(row.get(name))) is None else 1 - value
            for name in [
                "china_star100_star50_13w_rel_pctl",
                "china_chinext_100_50_13w_rel_pctl",
            ]
        ]
        row["us_structure_score"] = _mean(us_structure_values)
        row["china_structure_score"] = _mean(china_structure_values)
        row["breadth_weakness_score"] = _mean(
            [
                _parse_float(row.get("us_structure_score")),
                _parse_float(row.get("china_structure_score")),
            ]
        )
        row["breakage_score"] = _mean(
            [
                _parse_float(row.get("us_price_weakness_score")),
                _parse_float(row.get("china_price_weakness_score")),
            ]
        )

    us_structure_confirmed = _confirmed_flags(
        [_parse_float(row.get("us_structure_score")) for row in rows],
        threshold=0.70,
    )
    china_structure_confirmed = _confirmed_flags(
        [_parse_float(row.get("china_structure_score")) for row in rows],
        threshold=0.70,
    )
    us_price_confirmed = _confirmed_flags(
        [_parse_float(row.get("us_price_weakness_score")) for row in rows],
        threshold=0.50,
    )
    china_price_confirmed = _confirmed_flags(
        [_parse_float(row.get("china_price_weakness_score")) for row in rows],
        threshold=0.50,
    )

    valid_rows = [
        (idx, row)
        for idx, row in enumerate(rows)
        if _parse_float(row.get("breadth_weakness_score")) is not None or _parse_float(row.get("breakage_score")) is not None
    ]
    snapshots: list[MarketTopRiskSnapshot] = []
    for idx, row in valid_rows[-max(1, history_limit) :]:
        signal_map = {
            "rsp_spy_weakness_score": ("us_width", None if (value := _parse_float(row.get("rsp_spy_13w_rel_pctl"))) is None else 1 - value, 0.80),
            "qqew_qqq_weakness_score": ("us_width", None if (value := _parse_float(row.get("qqew_qqq_13w_rel_pctl"))) is None else 1 - value, 0.80),
            "soxx_qqq_weakness_score": ("us_mainline", None if (value := _parse_float(row.get("soxx_qqq_13w_rel_pctl"))) is None else 1 - value, 0.80),
            "xly_xlp_weakness_score": ("risk_appetite", None if (value := _parse_float(row.get("xly_xlp_13w_rel_pctl"))) is None else 1 - value, 0.80),
            "iwm_spy_weakness_score": ("risk_appetite", None if (value := _parse_float(row.get("iwm_spy_13w_rel_pctl"))) is None else 1 - value, 0.80),
            "china_star100_star50_weakness_score": (
                "china_experimental_width",
                None if (value := _parse_float(row.get("china_star100_star50_13w_rel_pctl"))) is None else 1 - value,
                0.80,
            ),
            "china_chinext_100_50_weakness_score": (
                "china_experimental_width",
                None if (value := _parse_float(row.get("china_chinext_100_50_13w_rel_pctl"))) is None else 1 - value,
                0.80,
            ),
            "us_price_weakness_score": ("price_weakness", _parse_float(row.get("us_price_weakness_score")), 0.50),
            "china_price_weakness_score": ("price_weakness", _parse_float(row.get("china_price_weakness_score")), 0.50),
        }
        signals = {
            name: {
                "value": value,
                "active": value is not None and value >= threshold,
                "module": module,
            }
            for name, (module, value, threshold) in signal_map.items()
        }
        us_structure_recent = _recent_true(us_structure_confirmed, idx, window=20)
        china_structure_recent = _recent_true(china_structure_confirmed, idx, window=20)
        us_state = _market_state(
            structure_confirmed=us_structure_confirmed[idx],
            structure_recent=us_structure_recent,
            price_confirmed=us_price_confirmed[idx],
            price_persistent=_persistent_true(us_price_confirmed, idx),
        )
        china_state = _market_state(
            structure_confirmed=china_structure_confirmed[idx],
            structure_recent=china_structure_recent,
            price_confirmed=china_price_confirmed[idx],
            price_persistent=_persistent_true(china_price_confirmed, idx),
        )
        warning_active = bool(us_structure_confirmed[idx] or china_structure_confirmed[idx])
        confirmation_active = bool(us_price_confirmed[idx] or china_price_confirmed[idx])
        us_risk_score = min(
            1.0,
            (0.55 * (_parse_float(row.get("us_structure_score")) or 0.0))
            + (0.45 * (_parse_float(row.get("us_price_weakness_score")) or 0.0)),
        )
        china_risk_score = min(
            1.0,
            (0.55 * (_parse_float(row.get("china_structure_score")) or 0.0))
            + (0.45 * (_parse_float(row.get("china_price_weakness_score")) or 0.0)),
        )
        risk_score = max(us_risk_score, china_risk_score)
        overall_state = us_state if us_risk_score >= china_risk_score else china_state
        snapshots.append(
            MarketTopRiskSnapshot(
                week=str(row["week"]),
                nasdaq100=_parse_float(row.get("nasdaq100")),
                ndx_dd_from_52w_high=_parse_float(row.get("ndx_dd_from_52w_high")),
                breadth_weakness_score=_parse_float(row.get("breadth_weakness_score")),
                breakage_score=_parse_float(row.get("breakage_score")),
                risk_score=risk_score,
                risk_level=_risk_level_from_state(overall_state, risk_score),
                warning_active=warning_active,
                confirmation_active=confirmation_active,
                signals=signals,
                metrics={
                    "near_high": (_parse_float(row.get("ndx_dd_from_52w_high")) or -1.0) >= -0.10,
                    "overall_state": overall_state,
                    "markets": {
                        "us_semis": {
                            "label": "美国半导体",
                            "price_symbol": "SOXX",
                            "structure_score": _parse_float(row.get("us_structure_score")),
                            "structure_confirmed": us_structure_confirmed[idx],
                            "structure_recent_20d": us_structure_recent,
                            "price_weakness_score": _parse_float(row.get("us_price_weakness_score")),
                            "price_confirmed": us_price_confirmed[idx],
                            "state": us_state,
                            "latest_date": row["week"],
                            "source_latest_dates": {
                                "SOXX": max(price_series.get("px_soxx", {}) or {}).isoformat() if price_series.get("px_soxx") else None,
                                "QQQ": max(price_series.get("px_qqq", {}) or {}).isoformat() if price_series.get("px_qqq") else None,
                            },
                        },
                        "china_star": {
                            "label": "中国科创",
                            "price_symbol": "588200.SH",
                            "structure_score": _parse_float(row.get("china_structure_score")),
                            "structure_confirmed": china_structure_confirmed[idx],
                            "structure_recent_20d": china_structure_recent,
                            "price_weakness_score": _parse_float(row.get("china_price_weakness_score")),
                            "price_confirmed": china_price_confirmed[idx],
                            "state": china_state,
                            "latest_date": row["week"],
                            "source_latest_dates": {
                                "588200.SH": max(price_series.get("px_588200_sh", {}) or {}).isoformat() if price_series.get("px_588200_sh") else None,
                                "588120.SS": max(price_series.get("px_588120_ss", {}) or {}).isoformat() if price_series.get("px_588120_ss") else None,
                                "588000.SS": max(price_series.get("px_588000_ss", {}) or {}).isoformat() if price_series.get("px_588000_ss") else None,
                                "159915.SZ": max(price_series.get("px_159915_sz", {}) or {}).isoformat() if price_series.get("px_159915_sz") else None,
                                "159949.SZ": max(price_series.get("px_159949_sz", {}) or {}).isoformat() if price_series.get("px_159949_sz") else None,
                            },
                        },
                    },
                    "baseline": {
                        "near_high_fwd_26w_avg_drawdown": -0.055,
                        "near_high_fwd_26w_dd10_probability": 0.211,
                    },
                },
                sources={
                    "nasdaq": list(NASDAQ_PRICE_SERIES.keys()),
                    "yahoo": list(CHINA_YAHOO_PRICE_SERIES.keys()),
                    "method": "daily close, rolling 13-week relative performance percentiles, 2-of-3 trading day confirmation",
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
