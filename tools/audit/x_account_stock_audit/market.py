from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from typing import Any

import requests

from packages.common.market_data import fetch_security_daily
from packages.common.paths import get_paths
from packages.common.security_aliases import load_security_aliases, resolve_security_identity

from .models import Candle, ScoreRow, StockChart, StockMention


HK_MARKETS = {"HK", "HKEX", "SEHK", "HKG"}


def normalize_mentions(mentions: list[StockMention]) -> list[StockMention]:
    aliases = load_security_aliases(get_paths())
    normalized: list[StockMention] = []
    for mention in mentions:
        identity = resolve_security_identity(
            mention.ticker_or_code or mention.stock_name,
            mention.stock_name,
            aliases,
        )
        if identity is None:
            identity_key = (mention.ticker_or_code or mention.stock_name).strip().casefold()
            display_name = mention.stock_name
            ticker = mention.ticker_or_code
            market = mention.market_hint
        else:
            identity_key = identity.security_key
            display_name = identity.display_name
            ticker = identity.ticker or mention.ticker_or_code
            market = identity.market or mention.market_hint

        mention.security_key = identity_key
        mention.display_name = display_name
        mention.ticker = ticker
        mention.market = market
        normalized.append(mention)
    return normalized


def _to_candles(payload: dict[str, Any]) -> list[Candle]:
    candles: list[Candle] = []
    for item in payload.get("candles") or []:
        if not isinstance(item, dict):
            continue
        try:
            candles.append(
                Candle(
                    date=str(item["date"]),
                    open=float(item["open"]),
                    high=float(item["high"]),
                    low=float(item["low"]),
                    close=float(item["close"]),
                    volume=float(item["volume"]) if item.get("volume") is not None else None,
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    candles.sort(key=lambda item: item.date)
    return candles


def _hk_yahoo_symbol(ticker: str | None, security_key: str | None) -> str | None:
    raw = (ticker or security_key or "").strip().upper()
    if not raw:
        return None
    raw = raw.split(".", 1)[0]
    if raw.isdigit():
        return f"{raw.zfill(4)}.HK"
    return f"{raw}.HK" if not raw.endswith(".HK") else raw


def fetch_hk_daily(ticker: str | None, security_key: str | None, days: int) -> dict[str, Any]:
    symbol = _hk_yahoo_symbol(ticker, security_key)
    if not symbol:
        return {"sourceLabel": "Yahoo Finance", "sourceSymbol": None, "message": "No HK symbol.", "candles": []}
    from packages.common.market_data import fetch_yahoo_daily

    payload = fetch_yahoo_daily(symbol=symbol, days=days)
    return {**payload, "sourceLabel": "Yahoo Finance", "sourceSymbol": symbol}


def fetch_chart_payload(*, ticker: str | None, market: str | None, security_key: str | None, days: int) -> dict[str, Any]:
    normalized_market = (market or "").strip().upper()
    if normalized_market in HK_MARKETS:
        return fetch_hk_daily(ticker, security_key, days)
    try:
        return fetch_security_daily(ticker=ticker, market=market, security_key=security_key, days=days)
    except Exception as exc:
        return {
            "sourceLabel": None,
            "sourceSymbol": None,
            "message": str(exc),
            "candles": [],
        }


def _find_candle_index(candles: list[Candle], mention_date: str) -> int | None:
    for index, candle in enumerate(candles):
        if candle.date >= mention_date:
            return index
    return None


def _score_return(mention: StockMention, candles: list[Candle], offset: int) -> float | None:
    if mention.stance not in {"bull", "bear"}:
        return None
    start_index = _find_candle_index(candles, mention.date)
    if start_index is None:
        return None
    end_index = start_index + offset
    if end_index >= len(candles):
        return None
    start_close = candles[start_index].close
    if start_close == 0:
        return None
    raw_return = (candles[end_index].close - start_close) / start_close
    return raw_return if mention.stance == "bull" else -raw_return


def attach_prices_and_build_charts(mentions: list[StockMention], *, days: int = 220, skip_market: bool = False) -> list[StockChart]:
    groups: dict[str, list[StockMention]] = defaultdict(list)
    for mention in mentions:
        if not mention.security_key:
            mention.security_key = (mention.ticker_or_code or mention.stock_name).casefold()
        groups[mention.security_key].append(mention)

    charts: list[StockChart] = []
    for security_key, items in sorted(groups.items(), key=lambda pair: pair[0]):
        first = items[0]
        payload = {"sourceLabel": None, "sourceSymbol": None, "message": "Market data skipped.", "candles": []}
        if not skip_market:
            payload = fetch_chart_payload(ticker=first.ticker, market=first.market, security_key=security_key, days=days)
        candles = _to_candles(payload)
        for mention in items:
            candle_index = _find_candle_index(candles, mention.date)
            if candle_index is not None:
                candle = candles[candle_index]
                mention.price_date = candle.date
                mention.price_close = candle.close
            mention.forward_returns = {
                "1d": _score_return(mention, candles, 1),
                "5d": _score_return(mention, candles, 5),
                "20d": _score_return(mention, candles, 20),
            }
        charts.append(
            StockChart(
                security_key=security_key,
                display_name=first.display_name or first.stock_name,
                ticker=first.ticker,
                market=first.market,
                source_label=payload.get("sourceLabel"),
                source_symbol=payload.get("sourceSymbol"),
                message=payload.get("message"),
                candles=candles,
                mentions=items,
            )
        )
    return charts


def build_scores(charts: list[StockChart]) -> list[ScoreRow]:
    rows: list[ScoreRow] = []
    for chart in charts:
        signal_mentions = [item for item in chart.mentions if item.stance in {"bull", "bear"}]
        mention_only_count = sum(1 for item in chart.mentions if item.stance == "mention_only")
        values_by_horizon = {
            horizon: [item.forward_returns.get(horizon) for item in signal_mentions if item.forward_returns.get(horizon) is not None]
            for horizon in ("1d", "5d", "20d")
        }

        def hit_rate(horizon: str) -> float | None:
            values = values_by_horizon[horizon]
            if not values:
                return None
            return sum(1 for value in values if value is not None and value > 0) / len(values)

        def avg_return(horizon: str) -> float | None:
            values = values_by_horizon[horizon]
            if not values:
                return None
            return sum(float(value) for value in values if value is not None) / len(values)

        rows.append(
            ScoreRow(
                security_key=chart.security_key,
                display_name=chart.display_name,
                ticker=chart.ticker,
                market=chart.market,
                signal_count=len(signal_mentions),
                mention_only_count=mention_only_count,
                hit_rate_1d=hit_rate("1d"),
                hit_rate_5d=hit_rate("5d"),
                hit_rate_20d=hit_rate("20d"),
                avg_return_1d=avg_return("1d"),
                avg_return_5d=avg_return("5d"),
                avg_return_20d=avg_return("20d"),
            )
        )
    return rows

