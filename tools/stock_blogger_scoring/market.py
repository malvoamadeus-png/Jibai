from __future__ import annotations

from datetime import datetime, time
from time import sleep
from typing import Any
from zoneinfo import ZoneInfo

from packages.common.market_data import fetch_eastmoney_daily, fetch_security_daily, fetch_yahoo_daily
from packages.common.paths import get_paths
from packages.common.security_aliases import load_security_aliases, resolve_security_identity

from .models import Candle, HorizonScore, ScoringConfig, SignalEvent, StockSignalMention


US_EXCHANGE_TZ = ZoneInfo("America/New_York")
A_SHARE_MARKETS = {"SSE", "SZSE", "BJSE"}
HK_MARKETS = {"HK", "HKEX", "SEHK", "HKG"}


def parse_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    return dt


def exchange_timezone_for_market(market: str | None) -> ZoneInfo:
    normalized = (market or "").strip().upper()
    if normalized in {"TWSE", "TPEX"}:
        return ZoneInfo("Asia/Taipei")
    if normalized in {"SSE", "SZSE", "BJSE"}:
        return ZoneInfo("Asia/Shanghai")
    return US_EXCHANGE_TZ


def event_trading_day(published_at: str, market: str | None) -> str:
    dt = parse_datetime(published_at).astimezone(exchange_timezone_for_market(market))
    return dt.date().isoformat()


def is_a_share_market(market: str | None) -> bool:
    return (market or "").strip().upper() in A_SHARE_MARKETS


def benchmark_kind_for_market(market: str | None) -> str:
    return "a_share" if is_a_share_market(market) else "global"


def normalize_mentions(mentions: list[StockSignalMention]) -> list[StockSignalMention]:
    aliases = load_security_aliases(get_paths())
    normalized: list[StockSignalMention] = []
    for mention in mentions:
        identity = resolve_security_identity(
            mention.ticker_or_code or mention.stock_name,
            mention.stock_name,
            aliases,
        )
        if identity is None:
            mention.security_key = (mention.ticker_or_code or mention.stock_name).strip().casefold()
            mention.display_name = mention.stock_name
            mention.ticker = mention.ticker_or_code
            mention.market = mention.market_hint
            mention.normalized_status = "fallback"
        else:
            mention.security_key = identity.security_key
            mention.display_name = identity.display_name
            mention.ticker = identity.ticker or mention.ticker_or_code
            mention.market = identity.market or mention.market_hint
            mention.normalized_status = "canonical"
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


def fetch_stock_candles(event: SignalEvent, *, days: int) -> tuple[list[Candle], dict[str, Any]]:
    payload: dict[str, Any] = {"sourceLabel": None, "sourceSymbol": None, "message": "not fetched", "candles": []}
    for attempt in range(2):
        try:
            payload = fetch_security_daily(ticker=event.ticker, market=event.market, security_key=event.security_key, days=days)
            break
        except Exception as exc:
            payload = {"sourceLabel": None, "sourceSymbol": None, "message": str(exc), "candles": []}
            if attempt == 0:
                sleep(0.5)
    candles = _to_candles(payload)
    if candles:
        return candles, payload

    normalized_market = (event.market or "").strip().upper()
    ticker = (event.ticker or "").strip().upper()
    if normalized_market in HK_MARKETS and ticker:
        raw = ticker.split(".", 1)[0]
        symbol = f"{raw.zfill(4)}.HK" if raw.isdigit() else (raw if raw.endswith(".HK") else f"{raw}.HK")
        try:
            yahoo_payload = fetch_yahoo_daily(symbol=symbol, days=days)
            yahoo_candles = _to_candles(yahoo_payload)
            if yahoo_candles:
                return yahoo_candles, {
                    **yahoo_payload,
                    "sourceLabel": "Yahoo Finance",
                    "sourceSymbol": symbol,
                    "message": yahoo_payload.get("message") or payload.get("message"),
                }
            payload = {
                **yahoo_payload,
                "sourceLabel": "Yahoo Finance",
                "sourceSymbol": symbol,
                "message": yahoo_payload.get("message") or payload.get("message"),
            }
        except Exception as exc:
            payload = {
                "sourceLabel": "Yahoo Finance",
                "sourceSymbol": symbol,
                "message": f"{payload.get('message') or 'primary market data failed'}; HK Yahoo fallback failed: {exc}",
                "candles": [],
            }
    return candles, payload


def fetch_global_benchmark_candles(config: ScoringConfig) -> tuple[str | None, list[Candle], dict[str, Any]]:
    errors: list[str] = []
    for symbol in (config.benchmark_symbol, config.benchmark_fallback_symbol):
        if not symbol:
            continue
        try:
            payload = fetch_yahoo_daily(symbol=symbol, days=config.price_days)
        except Exception as exc:
            errors.append(f"{symbol}: {exc}")
            continue
        candles = _to_candles(payload)
        if candles:
            return symbol, candles, payload
        errors.append(f"{symbol}: {payload.get('message') or 'no candles'}")
    return None, [], {"sourceLabel": "Yahoo Finance", "message": "; ".join(errors), "candles": []}


def fetch_a_share_benchmark_candles(config: ScoringConfig) -> tuple[str | None, list[Candle], dict[str, Any]]:
    errors: list[str] = []
    symbols: list[str] = []
    for symbol in (
        config.a_share_benchmark_symbol,
        config.a_share_benchmark_fallback_symbol,
        *config.a_share_benchmark_extra_symbols,
    ):
        normalized = str(symbol or "").strip()
        if normalized and normalized not in symbols:
            symbols.append(normalized)

    for symbol in symbols:
        if not symbol:
            continue
        for market in ("SSE", "SZSE", "BJSE"):
            try:
                payload = fetch_eastmoney_daily(ticker=symbol, market=market, days=config.price_days)
            except Exception as exc:
                errors.append(f"{market}:{symbol}: {exc}")
                continue
            candles = _to_candles(payload)
            if candles:
                return f"{market}:{symbol}", candles, {
                    **payload,
                    "sourceLabel": "EastMoney",
                    "sourceSymbol": f"{market}:{symbol}",
                }
            errors.append(f"{market}:{symbol}: {payload.get('message') or 'no candles'}")

        # Last resort only. Some China index codes have sparse Yahoo coverage,
        # but a short fallback is still better than silently marking all A-share
        # events as unsupported when EastMoney is temporarily unreachable.
        for yahoo_symbol in _a_share_benchmark_yahoo_symbols(symbol):
            try:
                payload = fetch_yahoo_daily(symbol=yahoo_symbol, days=config.price_days)
            except Exception as exc:
                errors.append(f"{yahoo_symbol}: {exc}")
                continue
            candles = _to_candles(payload)
            if len(candles) >= 2:
                return yahoo_symbol, candles, {
                    **payload,
                    "sourceLabel": "Yahoo Finance",
                    "sourceSymbol": yahoo_symbol,
                }
            errors.append(f"{yahoo_symbol}: {payload.get('message') or 'not enough candles'}")

    return None, [], {"sourceLabel": "EastMoney / Yahoo Finance", "message": "; ".join(errors), "candles": []}


def _a_share_benchmark_yahoo_symbols(symbol: str) -> list[str]:
    normalized = symbol.strip().upper()
    if not normalized:
        return []
    if "." in normalized:
        return [normalized]
    # 000688 is the STAR 50 index. 000688.SZ is a different Shenzhen-listed
    # stock, so do not try the generic Shenzhen suffix for this benchmark.
    if normalized == "000688":
        return ["000688.SS"]
    if normalized.startswith(("5", "6", "9")):
        return [f"{normalized}.SS"]
    if normalized.startswith(("0", "1", "2", "3")):
        return [f"{normalized}.SZ"]
    return [f"{normalized}.SS", f"{normalized}.SZ"]


def fetch_benchmark_sets(config: ScoringConfig, *, need_global: bool = True, need_a_share: bool = True) -> dict[str, tuple[str | None, list[Candle], dict[str, Any]]]:
    return {
        "global": fetch_global_benchmark_candles(config) if need_global else (None, [], {"message": "global benchmark not requested"}),
        "a_share": fetch_a_share_benchmark_candles(config) if need_a_share else (None, [], {"message": "A-share benchmark not requested"}),
    }


def _date_index(candles: list[Candle]) -> dict[str, int]:
    return {candle.date: index for index, candle in enumerate(candles)}


def _find_on_or_after(candles: list[Candle], date_key: str) -> int | None:
    for index, candle in enumerate(candles):
        if candle.date >= date_key:
            return index
    return None


def _find_exact(candles: list[Candle], date_key: str) -> int | None:
    return _date_index(candles).get(date_key)


def _anchor_event(event: SignalEvent, candles: list[Candle]) -> tuple[int | None, float | None, str | None, str | None]:
    if not candles:
        return None, None, None, "missing_price"
    dt = parse_datetime(event.published_at).astimezone(exchange_timezone_for_market(event.market))
    date_key = dt.date().isoformat()
    same_day_index = _find_exact(candles, date_key)
    market_open = time(9, 30)
    market_close = time(16, 0)

    if same_day_index is not None and dt.time() < market_open:
        candle = candles[same_day_index]
        return same_day_index, candle.open, "same_day_open", None
    if same_day_index is not None and dt.time() <= market_close:
        candle = candles[same_day_index]
        return same_day_index, candle.close, "same_day_close_estimate", None

    next_index = _find_on_or_after(candles, date_key)
    if next_index is not None and same_day_index is not None and candles[next_index].date == date_key:
        next_index = next_index + 1
    if next_index is None or next_index >= len(candles):
        return None, None, None, "pending"
    candle = candles[next_index]
    return next_index, candle.open, "next_day_open", None


def _target_index(anchor_index: int, horizon: int, anchor_kind: str) -> int:
    if anchor_kind.endswith("_open"):
        return anchor_index + horizon - 1
    return anchor_index + horizon


def _price_on_date(candles: list[Candle], date_key: str, price_kind: str) -> float | None:
    index = _find_exact(candles, date_key)
    if index is None:
        return None
    candle = candles[index]
    if price_kind.endswith("_open"):
        return candle.open
    return candle.close


def score_event(
    event: SignalEvent,
    stock_candles: list[Candle],
    benchmark_symbol: str | None,
    benchmark_candles: list[Candle],
    config: ScoringConfig,
) -> SignalEvent:
    if event.status != "scoreable":
        event.horizon_scores = {
            f"{horizon}d": HorizonScore(horizon=f"{horizon}d", status="unscored", message=event.status_reason)
            for horizon in config.horizons
        }
        return event

    anchor_index, anchor_price, anchor_kind, anchor_error = _anchor_event(event, stock_candles)
    if anchor_index is None or anchor_price is None or anchor_kind is None:
        event.status = "unscored"
        event.status_reason = anchor_error or "missing_anchor"
        event.horizon_scores = {
            f"{horizon}d": HorizonScore(horizon=f"{horizon}d", status="pending" if anchor_error == "pending" else "missing_price", message=event.status_reason)
            for horizon in config.horizons
        }
        return event

    anchor_candle = stock_candles[anchor_index]
    event.anchor_trading_day = anchor_candle.date
    event.anchor_price = anchor_price
    event.anchor_price_kind = anchor_kind

    event.benchmark_symbol = benchmark_symbol
    if benchmark_symbol and benchmark_candles:
        event.benchmark_anchor_price = _price_on_date(benchmark_candles, anchor_candle.date, anchor_kind)
        event.benchmark_status = "available" if event.benchmark_anchor_price is not None else "missing_anchor"
    else:
        event.benchmark_status = "missing"

    direction_sign = 1 if event.direction == "positive" else -1
    horizon_scores: dict[str, HorizonScore] = {}
    for horizon in config.horizons:
        label = f"{horizon}d"
        target_index = _target_index(anchor_index, horizon, anchor_kind)
        if target_index >= len(stock_candles):
            horizon_scores[label] = HorizonScore(horizon=label, status="pending", message="target trading day has not matured")
            continue

        target_candle = stock_candles[target_index]
        stock_return = (target_candle.close - anchor_price) / anchor_price if anchor_price else None
        if stock_return is None:
            horizon_scores[label] = HorizonScore(horizon=label, status="missing_price", message="invalid anchor price")
            continue

        if not benchmark_symbol or not benchmark_candles or event.benchmark_anchor_price is None:
            horizon_scores[label] = HorizonScore(
                horizon=label,
                status="missing_price",
                target_date=target_candle.date,
                target_price=target_candle.close,
                stock_return=stock_return,
                message="benchmark unavailable",
            )
            continue

        benchmark_target = _price_on_date(benchmark_candles, target_candle.date, "same_day_close_estimate")
        if benchmark_target is None:
            horizon_scores[label] = HorizonScore(
                horizon=label,
                status="missing_price",
                target_date=target_candle.date,
                target_price=target_candle.close,
                stock_return=stock_return,
                message="benchmark target price missing",
            )
            continue

        benchmark_return = (benchmark_target - event.benchmark_anchor_price) / event.benchmark_anchor_price
        excess_return = stock_return - benchmark_return
        directional_excess = direction_sign * excess_return
        scale = config.score_scales.get(label, 0.1) or 0.1
        horizon_scores[label] = HorizonScore(
            horizon=label,
            status="scored",
            target_date=target_candle.date,
            target_price=target_candle.close,
            benchmark_target_price=benchmark_target,
            stock_return=stock_return,
            benchmark_return=benchmark_return,
            excess_return=excess_return,
            directional_excess=directional_excess,
            score=directional_excess / scale * 100,
        )

    event.horizon_scores = horizon_scores
    return event


def score_events(
    events: list[SignalEvent],
    *,
    config: ScoringConfig,
    skip_market: bool = False,
) -> tuple[list[SignalEvent], dict[str, Any]]:
    if skip_market:
        for event in events:
            event.status = "unscored"
            event.status_reason = "market data skipped"
            event.horizon_scores = {
                f"{horizon}d": HorizonScore(horizon=f"{horizon}d", status="unscored", message=event.status_reason)
                for horizon in config.horizons
            }
        return events, {"benchmark_symbol": None, "stock_payloads": {}, "benchmark_message": "Market data skipped."}

    need_a_share = any(is_a_share_market(event.market) for event in events)
    need_global = any(not is_a_share_market(event.market) for event in events)
    benchmark_sets = fetch_benchmark_sets(config, need_global=need_global, need_a_share=need_a_share)
    stock_payloads: dict[str, Any] = {}
    candles_by_security: dict[str, list[Candle]] = {}

    for event in events:
        if event.security_key in candles_by_security:
            continue
        candles, payload = fetch_stock_candles(event, days=config.price_days)
        candles_by_security[event.security_key] = candles
        stock_payloads[event.security_key] = {
            "display_name": event.display_name,
            "ticker": event.ticker,
            "market": event.market,
            "source_label": payload.get("sourceLabel"),
            "source_symbol": payload.get("sourceSymbol"),
            "message": payload.get("message"),
            "candle_count": len(candles),
        }

    scored: list[SignalEvent] = []
    for event in events:
        benchmark_symbol, benchmark_candles, _benchmark_payload = benchmark_sets.get(
            benchmark_kind_for_market(event.market),
            (None, [], {}),
        )
        scored.append(
            score_event(
                event,
                candles_by_security.get(event.security_key, []),
                benchmark_symbol,
                benchmark_candles,
                config,
            )
        )
    global_symbol, global_candles, global_payload = benchmark_sets["global"]
    a_share_symbol, a_share_candles, a_share_payload = benchmark_sets["a_share"]
    return scored, {
        "benchmark_symbol": global_symbol,
        "benchmark_source_label": global_payload.get("sourceLabel"),
        "benchmark_message": global_payload.get("message"),
        "benchmark_candle_count": len(global_candles),
        "a_share_benchmark_symbol": a_share_symbol,
        "a_share_benchmark_source_label": a_share_payload.get("sourceLabel"),
        "a_share_benchmark_message": a_share_payload.get("message"),
        "a_share_benchmark_candle_count": len(a_share_candles),
        "stock_payloads": stock_payloads,
    }
