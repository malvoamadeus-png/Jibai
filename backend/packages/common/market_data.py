from __future__ import annotations

import re
from datetime import date as date_class, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import requests


A_SHARE_MARKETS = {"SSE", "SZSE", "BJSE"}
US_MARKETS = {"NASDAQ", "NYSE", "AMEX", "ARCA", "BATS", "IEX", "OTC", "US"}
YAHOO_SUFFIX_BY_MARKET = {
    "KRX": ".KS",
    "KOSDAQ": ".KQ",
    "LSE": ".L",
    "TSX": ".TO",
    "TSXV": ".V",
    "XETRA": ".DE",
    "EPA": ".PA",
    "EURONEXT": ".AS",
    "EBR": ".BR",
    "XMIL": ".MI",
    "SIX": ".SW",
    "STO": ".ST",
    "TWSE": ".TW",
    "TPEX": ".TWO",
}
_PLAIN_US_TICKER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9.]{0,4}$")
_A_SHARE_KEY_RE = re.compile(r"^(\d{6})\.(sh|sz|bj)$", re.IGNORECASE)
_TAIWAN_KEY_RE = re.compile(r"^(\d{4,6})\.(tw|tpex)$", re.IGNORECASE)


def _to_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text in {"--", "-", "X", "x"}:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _to_yahoo_range(days: int) -> str:
    normalized_days = max(30, min(int(days), 5000))
    if normalized_days <= 190:
        return "6mo"
    if normalized_days <= 370:
        return "1y"
    if normalized_days <= 800:
        return "2y"
    if normalized_days <= 1900:
        return "5y"
    if normalized_days <= 3700:
        return "10y"
    return "max"


def _normalize_market(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    aliases = {
        "SH": "SSE",
        "SZ": "SZSE",
        "BJ": "BJSE",
        "ST": "STO",
        "OMXSTO": "STO",
        "TW": "TWSE",
        "TSE": "TWSE",
        "TWO": "TPEX",
    }
    return aliases.get(normalized, normalized) or None


def _infer_ticker_from_key(security_key: str | None) -> str | None:
    key = (security_key or "").strip()
    if _PLAIN_US_TICKER_RE.fullmatch(key):
        return key.upper()
    return None


def _infer_a_share_from_key(security_key: str | None) -> tuple[str, str] | None:
    match = _A_SHARE_KEY_RE.fullmatch((security_key or "").strip())
    if not match:
        return None
    ticker = match.group(1)
    suffix = match.group(2).lower()
    if suffix == "sh":
        return ticker, "SSE"
    if suffix == "sz":
        return ticker, "SZSE"
    return ticker, "BJSE"


def _infer_taiwan_from_key(security_key: str | None) -> tuple[str, str] | None:
    match = _TAIWAN_KEY_RE.fullmatch((security_key or "").strip())
    if not match:
        return None
    ticker = match.group(1)
    suffix = match.group(2).lower()
    return ticker, "TWSE" if suffix == "tw" else "TPEX"


def _to_yahoo_us_symbol(ticker: str) -> str:
    return ticker.replace(".", "-")


def build_market_data_target(
    *,
    ticker: str | None,
    market: str | None,
    security_key: str | None = None,
) -> dict[str, str] | None:
    normalized_ticker = (ticker or "").strip().upper()
    normalized_market = _normalize_market(market)

    if not normalized_ticker:
        a_share = _infer_a_share_from_key(security_key)
        if a_share is not None:
            normalized_ticker, normalized_market = a_share
        else:
            taiwan_share = _infer_taiwan_from_key(security_key)
            if taiwan_share is not None:
                normalized_ticker, normalized_market = taiwan_share
            else:
                normalized_ticker = _infer_ticker_from_key(security_key) or ""

    if not normalized_ticker:
        return None

    if normalized_market in A_SHARE_MARKETS:
        return {
            "provider": "eastmoney",
            "symbol": normalized_ticker,
            "ticker": normalized_ticker,
            "market": normalized_market,
        }

    if normalized_market in US_MARKETS or normalized_market is None:
        return {
            "provider": "yahoo",
            "symbol": _to_yahoo_us_symbol(normalized_ticker),
            "ticker": normalized_ticker,
            "market": normalized_market or "US",
        }

    suffix = YAHOO_SUFFIX_BY_MARKET.get(normalized_market)
    if suffix:
        return {
            "provider": "yahoo",
            "symbol": f"{normalized_ticker}{suffix}",
            "ticker": normalized_ticker,
            "market": normalized_market,
        }

    return None


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


def _month_starts_between(start: date_class, end: date_class) -> list[date_class]:
    current = date_class(start.year, start.month, 1)
    results: list[date_class] = []
    while current <= end:
        results.append(current)
        if current.month == 12:
            current = date_class(current.year + 1, 1, 1)
        else:
            current = date_class(current.year, current.month + 1, 1)
    return results


def _parse_twse_date(value: str) -> str | None:
    parts = value.strip().split("/")
    if len(parts) != 3:
        return None
    try:
        year = int(parts[0])
        month = int(parts[1])
        day = int(parts[2])
    except ValueError:
        return None
    if year < 1911:
        year += 1911
    try:
        return date_class(year, month, day).isoformat()
    except ValueError:
        return None


def fetch_twse_daily(*, ticker: str, days: int = 180) -> dict[str, Any]:
    normalized_days = max(30, min(int(days), 5000))
    end_date = date_class.today()
    start_date = end_date - timedelta(days=normalized_days)
    session = requests.Session()

    candles_by_date: dict[str, dict[str, Any]] = {}
    for month_start in _month_starts_between(start_date, end_date):
        response = session.get(
            "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY",
            params={
                "date": month_start.strftime("%Y%m%d"),
                "stockNo": ticker,
                "response": "json",
            },
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json,text/plain,*/*",
            },
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("stat") != "OK":
            continue

        fields = payload.get("fields") if isinstance(payload.get("fields"), list) else []
        field_index = {str(field): index for index, field in enumerate(fields)}
        date_index = field_index.get("日期", 0)
        volume_index = field_index.get("成交股數", 1)
        open_index = field_index.get("開盤價", 3)
        high_index = field_index.get("最高價", 4)
        low_index = field_index.get("最低價", 5)
        close_index = field_index.get("收盤價", 6)

        rows = payload.get("data") if isinstance(payload.get("data"), list) else []
        for row in rows:
            if not isinstance(row, list):
                continue
            values = [str(item).strip() for item in row]
            if len(values) <= max(date_index, volume_index, open_index, high_index, low_index, close_index):
                continue
            trade_date = _parse_twse_date(values[date_index])
            if trade_date is None:
                continue
            trade_date_obj = date_class.fromisoformat(trade_date)
            if trade_date_obj < start_date or trade_date_obj > end_date:
                continue
            open_price = _to_number(values[open_index])
            high_price = _to_number(values[high_index])
            low_price = _to_number(values[low_index])
            close_price = _to_number(values[close_index])
            volume = _to_number(values[volume_index])
            if open_price is None or high_price is None or low_price is None or close_price is None:
                continue
            candles_by_date[trade_date] = {
                "date": trade_date,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": volume,
            }

    candles = [candles_by_date[key] for key in sorted(candles_by_date)]
    return {
        "sourceLabel": "TWSE",
        "message": None if candles else "TWSE 没有返回这只股票的日线数据。",
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


def fetch_security_daily(
    *,
    ticker: str | None,
    market: str | None,
    security_key: str | None = None,
    days: int = 730,
) -> dict[str, Any]:
    target = build_market_data_target(ticker=ticker, market=market, security_key=security_key)
    if target is None:
        return {
            "sourceLabel": None,
            "sourceSymbol": None,
            "message": "No supported market-data symbol was found for this stock.",
            "candles": [],
        }

    if target["provider"] == "eastmoney":
        payload = fetch_eastmoney_daily(
            ticker=target["ticker"],
            market=target["market"],
            days=days,
        )
        return {
            **payload,
            "sourceLabel": "EastMoney",
            "sourceSymbol": f"{target['market']}:{target['ticker']}",
        }

    yahoo_error: Exception | None = None
    try:
        payload = fetch_yahoo_daily(symbol=target["symbol"], days=days)
    except Exception as exc:
        if target["market"] != "TWSE":
            raise
        yahoo_error = exc
        payload = {
            "sourceLabel": "Yahoo Finance",
            "message": str(exc),
            "candles": [],
        }

    if target["market"] == "TWSE" and not payload.get("candles"):
        try:
            twse_payload = fetch_twse_daily(ticker=target["ticker"], days=days)
            if twse_payload.get("candles"):
                return {
                    **twse_payload,
                    "sourceLabel": "TWSE",
                    "sourceSymbol": f"TWSE:{target['ticker']}",
                }
        except Exception as exc:
            if yahoo_error is not None:
                return {
                    "sourceLabel": "Yahoo Finance / TWSE",
                    "sourceSymbol": target["symbol"],
                    "message": f"Yahoo Finance 和 TWSE 都没有返回可用日线：{yahoo_error}; {exc}",
                    "candles": [],
                }
            return {
                "sourceLabel": "Yahoo Finance / TWSE",
                "sourceSymbol": target["symbol"],
                "message": f"TWSE 兜底失败：{exc}",
                "candles": [],
            }

    return {
        **payload,
        "sourceLabel": "Yahoo Finance",
        "sourceSymbol": target["symbol"],
    }
