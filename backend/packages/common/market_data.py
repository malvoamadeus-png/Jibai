from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import requests


def _to_number(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_yahoo_range(days: int) -> str:
    normalized_days = max(30, min(int(days), 5000))
    if normalized_days <= 125:
        return "6mo"
    if normalized_days <= 250:
        return "1y"
    if normalized_days <= 500:
        return "2y"
    if normalized_days <= 1250:
        return "5y"
    if normalized_days <= 2500:
        return "10y"
    return "max"


def _format_yahoo_date(timestamp: int | float | None, exchange_timezone: str | None) -> str | None:
    if timestamp is None:
        return None
    dt = datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
    if exchange_timezone:
        try:
            dt = dt.astimezone(ZoneInfo(exchange_timezone))
        except Exception:
            pass
    return dt.strftime("%Y-%m-%d")


def fetch_eastmoney_daily(*, ticker: str, market: str, days: int = 180) -> dict[str, Any]:
    normalized_market = market.strip().upper()
    if normalized_market not in {"SSE", "SZSE", "BJSE"}:
        raise ValueError(f"Unsupported EastMoney market: {market}")

    secid_prefix = "1" if normalized_market == "SSE" else "0"
    session = requests.Session()
    session.trust_env = False

    response = session.get(
        "https://push2his.eastmoney.com/api/qt/stock/kline/get",
        params={
            "secid": f"{secid_prefix}.{ticker}",
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
            "klt": "101",
            "fqt": "1",
            "beg": "0",
            "end": "20500101",
            "lmt": max(30, min(int(days), 1000)),
        },
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://quote.eastmoney.com/",
        },
        timeout=8,
    )
    response.raise_for_status()
    payload = response.json()

    candles: list[dict[str, Any]] = []
    for raw_line in (payload.get("data") or {}).get("klines") or []:
        parts = str(raw_line).split(",")
        if len(parts) < 6:
            continue
        open_price = _to_number(parts[1])
        close_price = _to_number(parts[2])
        high_price = _to_number(parts[3])
        low_price = _to_number(parts[4])
        volume = _to_number(parts[5])
        if not parts[0] or open_price is None or close_price is None or high_price is None or low_price is None:
            continue
        candles.append(
            {
                "date": parts[0],
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": volume,
            }
        )

    return {
        "sourceLabel": "东财",
        "message": None if candles else "东财没有返回这只股票的日线数据。",
        "candles": candles,
    }


def fetch_yahoo_daily(*, symbol: str, days: int = 180) -> dict[str, Any]:
    normalized_days = max(30, min(int(days), 5000))
    session = requests.Session()

    response = session.get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
        params={
            "interval": "1d",
            "includePrePost": "false",
            "events": "div,splits",
            "range": _to_yahoo_range(normalized_days),
        },
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json,text/plain,*/*",
        },
        timeout=8,
    )
    response.raise_for_status()
    payload = response.json()

    chart = payload.get("chart") or {}
    result = ((chart.get("result") or [None])[0]) or {}
    meta = result.get("meta") or {}
    quote = (((result.get("indicators") or {}).get("quote") or [None])[0]) or {}

    timestamps = result.get("timestamp") or []
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    exchange_timezone = meta.get("exchangeTimezoneName") or meta.get("timezone")

    candles: list[dict[str, Any]] = []
    for index, raw_timestamp in enumerate(timestamps):
        open_price = _to_number(opens[index] if index < len(opens) else None)
        high_price = _to_number(highs[index] if index < len(highs) else None)
        low_price = _to_number(lows[index] if index < len(lows) else None)
        close_price = _to_number(closes[index] if index < len(closes) else None)
        volume = _to_number(volumes[index] if index < len(volumes) else None)
        trade_date = _format_yahoo_date(raw_timestamp, exchange_timezone)
        if (
            trade_date is None
            or open_price is None
            or high_price is None
            or low_price is None
            or close_price is None
        ):
            continue
        candles.append(
            {
                "date": trade_date,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": volume,
            }
        )

    if len(candles) > normalized_days:
        candles = candles[-normalized_days:]

    error = chart.get("error") or {}
    return {
        "sourceLabel": "Yahoo Finance",
        "message": None if candles else error.get("description") or "Yahoo Finance did not return daily candles for this symbol.",
        "candles": candles,
    }
