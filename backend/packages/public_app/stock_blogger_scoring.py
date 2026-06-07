from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from psycopg import Connection
from psycopg.types.json import Jsonb

from packages.common.market_data import fetch_security_daily
from packages.common.postgres_database import PostgresInsightStore, postgres_connection
from packages.common.security_aliases import SecurityIdentity
from packages.common.time_utils import SHANGHAI_TZ, now_iso, today_date_key


DEFAULT_ACCOUNTS = ("labubu_trader", "hicagr", "xiaomustock")
HORIZONS = (1, 5, 20)
HORIZON_LABELS = ("1d", "5d", "20d")
HORIZON_WEIGHTS = {"1d": 0.20, "5d": 0.35, "20d": 0.45}
SCORE_SCALES = {"1d": 0.05, "5d": 0.10, "20d": 0.20}
CONVICTION_WEIGHTS = {"strong": 1.25, "medium": 1.0, "unknown": 0.85, "weak": 0.65}
A_SHARE_MARKETS = {"SSE", "SZSE", "BJSE"}
PRICE_WINDOW_DAYS = 180


@dataclass(slots=True)
class PriceCandle:
    date: str
    open: float
    close: float


@dataclass(slots=True)
class MentionRow:
    content_id: str
    viewpoint_id: str
    account_id: str
    account_name: str
    author_nickname: str
    publish_time: datetime | None
    security_id: str
    security_key: str
    display_name: str
    ticker: str | None
    market: str | None
    direction: str
    signal_type: str
    judgment_type: str
    conviction: str
    evidence_type: str
    time_horizon: str
    sort_order: int


@dataclass(slots=True)
class ScoreEvent:
    event_id: str
    account_id: str
    account_name: str
    author_nickname: str
    security_id: str
    security_key: str
    display_name: str
    ticker: str | None
    market: str | None
    event_trading_day: str
    published_at: datetime | None
    direction: str
    conviction: str
    evidence_type: str
    time_horizons: list[str]
    content_ids: list[str]
    viewpoint_ids: list[str]
    anchor_trading_day: str | None = None
    anchor_price: float | None = None
    anchor_price_kind: str | None = None
    benchmark_symbol: str | None = None
    benchmark_anchor_price: float | None = None
    horizon_scores: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(slots=True)
class AuthorScore:
    account_id: str
    account_name: str
    author_nickname: str
    overall_score: float | None
    score_by_horizon: dict[str, float | None]
    scored_day_count_by_horizon: dict[str, int]
    matured_count_by_horizon: dict[str, int]
    pending_count_by_horizon: dict[str, int]
    event_count: int
    scored_event_count: int
    scored_day_count: int
    positive_count: int
    negative_count: int
    conviction_counts: dict[str, int]
    best_horizon: str | None
    worst_horizon: str | None


def _json(value: Any) -> Jsonb:
    return Jsonb(value)


def _accounts_from_env() -> list[str]:
    raw = os.getenv("PUBLIC_STOCK_BLOGGER_SCORE_ACCOUNTS", ",".join(DEFAULT_ACCOUNTS))
    values: list[str] = []
    for item in raw.split(","):
        account = item.strip().lstrip("@").lower()
        if account and account not in values:
            values.append(account)
    return values or list(DEFAULT_ACCOUNTS)


def _config_payload(accounts: list[str], days: int) -> dict[str, Any]:
    return {
        "accounts": accounts,
        "history_days": days,
        "price_days": PRICE_WINDOW_DAYS,
        "horizons": list(HORIZONS),
        "horizon_weights": HORIZON_WEIGHTS,
        "score_scales": SCORE_SCALES,
        "conviction_weights": CONVICTION_WEIGHTS,
        "benchmark_symbol": "^IXIC",
        "benchmark_fallback_symbol": "QQQ",
        "a_share_benchmark_symbol": "000688",
        "a_share_benchmark_fallback_symbol": "588000",
    }


def _normalize_market(value: str | None) -> str:
    return (value or "").strip().upper()


def _is_a_share_market(value: str | None) -> bool:
    return _normalize_market(value) in A_SHARE_MARKETS


def _exchange_timezone(market: str | None) -> ZoneInfo:
    normalized = _normalize_market(market)
    if normalized in A_SHARE_MARKETS:
        return ZoneInfo("Asia/Shanghai")
    if normalized in {"HK", "HKEX", "SEHK", "HKG"}:
        return ZoneInfo("Asia/Hong_Kong")
    if normalized in {"TWSE", "TPEX", "TW", "TWO"}:
        return ZoneInfo("Asia/Taipei")
    if normalized in {"KRX", "KOSDAQ"}:
        return ZoneInfo("Asia/Seoul")
    return ZoneInfo("America/New_York")


def _market_hours(market: str | None) -> tuple[time, time]:
    if _normalize_market(market) in A_SHARE_MARKETS:
        return time(9, 30), time(15, 0)
    if _normalize_market(market) in {"HK", "HKEX", "SEHK", "HKG"}:
        return time(9, 30), time(16, 0)
    return time(9, 30), time(16, 0)


def _local_dt(value: datetime | None, market: str | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=SHANGHAI_TZ)
    return value.astimezone(_exchange_timezone(market))


def _event_trading_day(value: datetime | None, market: str | None) -> str:
    local = _local_dt(value, market)
    return (local.date() if local else datetime.now(SHANGHAI_TZ).date()).isoformat()


def _find_exact(candles: list[PriceCandle], date_key: str) -> int | None:
    for index, candle in enumerate(candles):
        if candle.date == date_key:
            return index
    return None


def _find_on_or_after(candles: list[PriceCandle], date_key: str) -> int | None:
    for index, candle in enumerate(candles):
        if candle.date >= date_key:
            return index
    return None


def _anchor_event(event: ScoreEvent, candles: list[PriceCandle]) -> tuple[int | None, float | None, str | None, str | None]:
    local = _local_dt(event.published_at, event.market)
    date_key = event.event_trading_day if local is None else local.date().isoformat()
    same_day_index = _find_exact(candles, date_key)
    open_time, close_time = _market_hours(event.market)

    if local is not None and same_day_index is not None and local.time() < open_time:
        return same_day_index, candles[same_day_index].open, "same_day_open", None
    if local is not None and same_day_index is not None and local.time() <= close_time:
        return same_day_index, candles[same_day_index].close, "same_day_close_estimate", None

    next_index = _find_on_or_after(candles, date_key)
    if next_index is not None and same_day_index is not None and candles[next_index].date == date_key:
        next_index += 1
    if next_index is None or next_index >= len(candles):
        return None, None, None, "pending"
    return next_index, candles[next_index].open, "next_day_open", None


def _target_index(anchor_index: int, horizon: int, anchor_kind: str) -> int:
    return anchor_index + horizon - 1 if anchor_kind.endswith("_open") else anchor_index + horizon


def _price_on_date(candles: list[PriceCandle], date_key: str, price_kind: str) -> float | None:
    index = _find_exact(candles, date_key)
    if index is None:
        return None
    return candles[index].open if price_kind.endswith("_open") else candles[index].close


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _weighted_mean(values: list[tuple[float, float]]) -> float | None:
    total_weight = sum(weight for _value, weight in values)
    if total_weight <= 0:
        return None
    return sum(value * weight for value, weight in values) / total_weight


def _parse_candles(rows: list[dict[str, Any]]) -> list[PriceCandle]:
    candles: list[PriceCandle] = []
    for row in rows:
        try:
            candles.append(
                PriceCandle(
                    date=str(row["date_key"]),
                    open=float(row["open_price"]),
                    close=float(row["close_price"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(candles, key=lambda item: item.date)


def _fetch_mentions(conn: Connection[dict[str, Any]], *, accounts: list[str], start_date: str, end_date: str) -> list[MentionRow]:
    rows = conn.execute(
        """
        SELECT
          c.id::text AS content_id,
          cv.id::text AS viewpoint_id,
          a.id::text AS account_id,
          lower(a.username::text) AS account_name,
          coalesce(nullif(a.display_name, ''), a.username::text) AS author_nickname,
          c.publish_time,
          se.id::text AS security_id,
          se.security_key::text AS security_key,
          se.display_name::text AS display_name,
          se.ticker::text AS ticker,
          se.market::text AS market,
          cv.direction,
          cv.signal_type,
          cv.judgment_type,
          cv.conviction,
          cv.evidence_type,
          cv.time_horizon,
          cv.sort_order
        FROM public.content_viewpoints cv
        JOIN public.content_items c ON c.id = cv.content_id
        JOIN public.x_accounts a ON a.id = c.account_id
        JOIN public.security_entities se ON se.id = cv.security_id
        JOIN public.account_domains ad ON ad.account_id = a.id AND ad.domain = 'stock'
        WHERE cv.analysis_domain = 'stock'
          AND cv.entity_type = 'stock'
          AND lower(a.username::text) = ANY(%s)
          AND ad.status = 'approved'
          AND coalesce(cv.signal_type, '') IN ('explicit_stance', 'logic_based')
          AND coalesce(cv.direction, '') IN ('positive', 'negative')
          AND coalesce(cv.judgment_type, '') IN ('direct', 'implied')
          AND coalesce(cv.conviction, '') <> 'none'
          AND coalesce(c.publish_time, c.fetched_at, c.created_at)::date BETWEEN %s::date AND %s::date
        ORDER BY lower(a.username::text), coalesce(c.publish_time, c.fetched_at, c.created_at), se.security_key, cv.sort_order
        """,
        (accounts, start_date, end_date),
    ).fetchall()
    return [
        MentionRow(
            content_id=str(row["content_id"]),
            viewpoint_id=str(row["viewpoint_id"]),
            account_id=str(row["account_id"]),
            account_name=str(row["account_name"]),
            author_nickname=str(row["author_nickname"] or row["account_name"]),
            publish_time=row["publish_time"],
            security_id=str(row["security_id"]),
            security_key=str(row["security_key"]),
            display_name=str(row["display_name"]),
            ticker=str(row["ticker"]).strip() if row["ticker"] else None,
            market=str(row["market"]).strip() if row["market"] else None,
            direction=str(row["direction"]),
            signal_type=str(row["signal_type"]),
            judgment_type=str(row["judgment_type"]),
            conviction=str(row["conviction"] or "unknown"),
            evidence_type=str(row["evidence_type"] or "unknown"),
            time_horizon=str(row["time_horizon"] or "unspecified"),
            sort_order=int(row["sort_order"] or 0),
        )
        for row in rows
    ]


def build_events(mentions: list[MentionRow]) -> list[ScoreEvent]:
    grouped: dict[tuple[str, str, str, str], list[MentionRow]] = {}
    for mention in mentions:
        day = _event_trading_day(mention.publish_time, mention.market)
        key = (mention.account_id, mention.security_id, day, mention.direction)
        grouped.setdefault(key, []).append(mention)

    events: list[ScoreEvent] = []
    for (_account_id, _security_id, day, direction), items in sorted(grouped.items(), key=lambda pair: pair[0]):
        ordered = sorted(items, key=lambda item: (item.publish_time or datetime.min.replace(tzinfo=SHANGHAI_TZ), item.sort_order))
        first = ordered[0]
        event_key = "|".join([first.account_id, first.security_id, day, direction, *sorted(item.viewpoint_id for item in ordered)])
        events.append(
            ScoreEvent(
                event_id=str(uuid.uuid5(uuid.NAMESPACE_URL, event_key)),
                account_id=first.account_id,
                account_name=first.account_name,
                author_nickname=first.author_nickname,
                security_id=first.security_id,
                security_key=first.security_key,
                display_name=first.display_name,
                ticker=first.ticker,
                market=first.market,
                event_trading_day=day,
                published_at=first.publish_time,
                direction=direction,
                conviction=_best_conviction([item.conviction for item in ordered]),
                evidence_type=first.evidence_type,
                time_horizons=list(dict.fromkeys(item.time_horizon for item in ordered if item.time_horizon)),
                content_ids=list(dict.fromkeys(item.content_id for item in ordered)),
                viewpoint_ids=list(dict.fromkeys(item.viewpoint_id for item in ordered)),
            )
        )
    return events


def _best_conviction(values: list[str]) -> str:
    rank = {"strong": 4, "medium": 3, "unknown": 2, "weak": 1, "none": 0}
    return max(values or ["unknown"], key=lambda value: rank.get(value, 0))


def _load_price_map(conn: Connection[dict[str, Any]], security_ids: list[str]) -> dict[str, list[PriceCandle]]:
    if not security_ids:
        return {}
    rows = conn.execute(
        """
        SELECT security_id::text, date_key, open_price, close_price
        FROM public.security_daily_prices
        WHERE security_id = ANY(%s)
        ORDER BY security_id, date_key
        """,
        (list(dict.fromkeys(security_ids)),),
    ).fetchall()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["security_id"]), []).append(dict(row))
    return {key: _parse_candles(value) for key, value in grouped.items()}


def _ensure_benchmark(conn: Connection[dict[str, Any]], key: str, display_name: str, ticker: str, market: str) -> str:
    store = PostgresInsightStore(conn)
    return store.ensure_security(
        SecurityIdentity(security_key=key, display_name=display_name, ticker=ticker, market=market)
    )


def _refresh_benchmark(conn: Connection[dict[str, Any]], *, key: str, display_name: str, ticker: str, market: str) -> tuple[str, list[PriceCandle]]:
    security_id = _ensure_benchmark(conn, key, display_name, ticker, market)
    payload = fetch_security_daily(ticker=ticker, market=market, security_key=key, days=PRICE_WINDOW_DAYS)
    candles = payload.get("candles") or []
    if candles:
        store = PostgresInsightStore(conn)
        store.upsert_security_daily_prices(
            security_key=key,
            source=str(payload.get("sourceLabel") or "Unknown"),
            source_symbol=str(payload.get("sourceSymbol") or ticker),
            candles=candles,
            fetched_at=now_iso(),
        )
        conn.commit()
    prices = _load_price_map(conn, [security_id]).get(security_id, [])
    return str(payload.get("sourceSymbol") or ticker), prices


def _benchmark_sets(conn: Connection[dict[str, Any]]) -> tuple[tuple[str, list[PriceCandle]], tuple[str, list[PriceCandle]]]:
    global_symbol, global_prices = _refresh_benchmark(
        conn,
        key="^ixic",
        display_name="Nasdaq Composite",
        ticker="^IXIC",
        market="US",
    )
    if not global_prices:
        global_symbol, global_prices = _refresh_benchmark(
            conn,
            key="qqq",
            display_name="Invesco QQQ Trust",
            ticker="QQQ",
            market="NASDAQ",
        )
    a_symbol, a_prices = _refresh_benchmark(
        conn,
        key="000688.sh",
        display_name="科创50指数",
        ticker="000688",
        market="SSE",
    )
    if not a_prices:
        a_symbol, a_prices = _refresh_benchmark(
            conn,
            key="588000.sh",
            display_name="科创50ETF",
            ticker="588000",
            market="SSE",
        )
    return (global_symbol, global_prices), (a_symbol, a_prices)


def score_events(events: list[ScoreEvent], price_map: dict[str, list[PriceCandle]], benchmarks: tuple[tuple[str, list[PriceCandle]], tuple[str, list[PriceCandle]]]) -> list[ScoreEvent]:
    global_benchmark, a_benchmark = benchmarks
    for event in events:
        stock_candles = price_map.get(event.security_id, [])
        anchor_index, anchor_price, anchor_kind, anchor_error = _anchor_event(event, stock_candles)
        if anchor_index is None or anchor_price is None or anchor_kind is None:
            event.horizon_scores = {
                label: {"status": "pending" if anchor_error == "pending" else "missing_price", "message": anchor_error or "missing_anchor"}
                for label in HORIZON_LABELS
            }
            continue

        anchor_candle = stock_candles[anchor_index]
        benchmark_symbol, benchmark_candles = a_benchmark if _is_a_share_market(event.market) else global_benchmark
        event.anchor_trading_day = anchor_candle.date
        event.anchor_price = anchor_price
        event.anchor_price_kind = anchor_kind
        event.benchmark_symbol = benchmark_symbol
        event.benchmark_anchor_price = _price_on_date(benchmark_candles, anchor_candle.date, anchor_kind)

        direction_sign = 1 if event.direction == "positive" else -1
        event.horizon_scores = {}
        for horizon in HORIZONS:
            label = f"{horizon}d"
            target_index = _target_index(anchor_index, horizon, anchor_kind)
            if target_index >= len(stock_candles):
                event.horizon_scores[label] = {"status": "pending", "message": "target trading day has not matured"}
                continue
            target_candle = stock_candles[target_index]
            stock_return = (target_candle.close - anchor_price) / anchor_price
            if event.benchmark_anchor_price is None or not benchmark_candles:
                event.horizon_scores[label] = {
                    "status": "missing_price",
                    "target_date": target_candle.date,
                    "target_price": target_candle.close,
                    "stock_return": stock_return,
                    "message": "benchmark unavailable",
                }
                continue
            benchmark_target = _price_on_date(benchmark_candles, target_candle.date, "same_day_close_estimate")
            if benchmark_target is None:
                event.horizon_scores[label] = {
                    "status": "missing_price",
                    "target_date": target_candle.date,
                    "target_price": target_candle.close,
                    "stock_return": stock_return,
                    "message": "benchmark target price missing",
                }
                continue
            benchmark_return = (benchmark_target - event.benchmark_anchor_price) / event.benchmark_anchor_price
            excess_return = stock_return - benchmark_return
            directional_excess = direction_sign * excess_return
            event.horizon_scores[label] = {
                "status": "scored",
                "target_date": target_candle.date,
                "target_price": target_candle.close,
                "benchmark_target_price": benchmark_target,
                "stock_return": stock_return,
                "benchmark_return": benchmark_return,
                "excess_return": excess_return,
                "directional_excess": directional_excess,
                "score": directional_excess / SCORE_SCALES[label] * 100,
            }
    return events


def aggregate_author_scores(events: list[ScoreEvent]) -> list[AuthorScore]:
    by_author: dict[str, list[ScoreEvent]] = {}
    for event in events:
        by_author.setdefault(event.account_id, []).append(event)

    rows: list[AuthorScore] = []
    for account_id, items in sorted(by_author.items(), key=lambda pair: pair[1][0].account_name):
        score_by_horizon: dict[str, float | None] = {}
        scored_day_count_by_horizon: dict[str, int] = {}
        matured_count_by_horizon: dict[str, int] = {}
        pending_count_by_horizon: dict[str, int] = {}

        for label in HORIZON_LABELS:
            by_day: dict[str, list[tuple[float, float]]] = {}
            pending_count = 0
            for event in items:
                horizon_score = event.horizon_scores.get(label) or {}
                if horizon_score.get("status") == "pending":
                    pending_count += 1
                if horizon_score.get("status") != "scored":
                    continue
                score = horizon_score.get("score")
                if score is None:
                    continue
                by_day.setdefault(event.event_trading_day, []).append(
                    (float(score), CONVICTION_WEIGHTS.get(event.conviction, 1.0))
                )
            day_scores = [value for values in by_day.values() if (value := _weighted_mean(values)) is not None]
            score_by_horizon[label] = _mean(day_scores)
            scored_day_count_by_horizon[label] = len(day_scores)
            matured_count_by_horizon[label] = sum(len(values) for values in by_day.values())
            pending_count_by_horizon[label] = pending_count

        overall = _weighted_mean(
            [
                (score, HORIZON_WEIGHTS[label])
                for label, score in score_by_horizon.items()
                if score is not None
            ]
        )
        non_null_scores = {label: score for label, score in score_by_horizon.items() if score is not None}
        scored_events = [event for event in items if any((score.get("status") == "scored") for score in event.horizon_scores.values())]
        conviction_counts: dict[str, int] = {}
        for event in items:
            conviction_counts[event.conviction] = conviction_counts.get(event.conviction, 0) + 1
        rows.append(
            AuthorScore(
                account_id=account_id,
                account_name=items[0].account_name,
                author_nickname=items[0].author_nickname,
                overall_score=overall,
                score_by_horizon=score_by_horizon,
                scored_day_count_by_horizon=scored_day_count_by_horizon,
                matured_count_by_horizon=matured_count_by_horizon,
                pending_count_by_horizon=pending_count_by_horizon,
                event_count=len(items),
                scored_event_count=len(scored_events),
                scored_day_count=len({event.event_trading_day for event in scored_events}),
                positive_count=sum(1 for event in items if event.direction == "positive"),
                negative_count=sum(1 for event in items if event.direction == "negative"),
                conviction_counts=conviction_counts,
                best_horizon=max(non_null_scores, key=lambda label: non_null_scores[label]) if non_null_scores else None,
                worst_horizon=min(non_null_scores, key=lambda label: non_null_scores[label]) if non_null_scores else None,
            )
        )
    rows.sort(key=lambda row: (row.overall_score is None, -(row.overall_score or -10**12), row.account_name))
    return rows


def _score_value(score_by_horizon: dict[str, float | None], label: str) -> float | None:
    value = score_by_horizon.get(label)
    return float(value) if value is not None else None


def _insert_run(
    conn: Connection[dict[str, Any]],
    *,
    run_id: str,
    window_start: str,
    window_end: str,
    config: dict[str, Any],
    status: str,
    event_count: int,
    author_count: int,
    error_text: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO public.stock_blogger_score_runs (
          id, run_date, window_start, window_end, status, config_json,
          event_count, author_count, error_text, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
        ON CONFLICT(id) DO UPDATE SET
          status = EXCLUDED.status,
          event_count = EXCLUDED.event_count,
          author_count = EXCLUDED.author_count,
          error_text = EXCLUDED.error_text,
          updated_at = now()
        """,
        (run_id, today_date_key(), window_start, window_end, status, _json(config), event_count, author_count, error_text),
    )


def _persist_scores(conn: Connection[dict[str, Any]], *, run_id: str, author_scores: list[AuthorScore], events: list[ScoreEvent]) -> None:
    author_score_ids: dict[str, str] = {}
    for row in author_scores:
        score_id = str(uuid.uuid4())
        author_score_ids[row.account_id] = score_id
        conn.execute(
            """
            INSERT INTO public.stock_blogger_author_scores (
              id, run_id, account_id, account_name, author_nickname, overall_score,
              score_1d, score_5d, score_20d, scored_day_count, event_count,
              scored_event_count, pending_count, positive_count, negative_count,
              direction_counts_json, conviction_counts_json, score_by_horizon_json,
              scored_day_count_by_horizon_json, matured_count_by_horizon_json,
              pending_count_by_horizon_json, best_horizon, worst_horizon
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                score_id,
                run_id,
                row.account_id,
                row.account_name,
                row.author_nickname,
                row.overall_score,
                _score_value(row.score_by_horizon, "1d"),
                _score_value(row.score_by_horizon, "5d"),
                _score_value(row.score_by_horizon, "20d"),
                row.scored_day_count,
                row.event_count,
                row.scored_event_count,
                sum(row.pending_count_by_horizon.values()),
                row.positive_count,
                row.negative_count,
                _json({"positive": row.positive_count, "negative": row.negative_count}),
                _json(row.conviction_counts),
                _json(row.score_by_horizon),
                _json(row.scored_day_count_by_horizon),
                _json(row.matured_count_by_horizon),
                _json(row.pending_count_by_horizon),
                row.best_horizon,
                row.worst_horizon,
            ),
        )

    for event in events:
        conn.execute(
            """
            INSERT INTO public.stock_blogger_score_events (
              event_key, run_id, author_score_id, account_id, account_name, author_nickname,
              security_id, security_key, display_name, ticker, market, event_trading_day,
              published_at, direction, conviction, evidence_type, time_horizons_json,
              content_ids_json, viewpoint_ids_json, anchor_trading_day, anchor_price,
              anchor_price_kind, benchmark_symbol, benchmark_anchor_price,
              horizon_scores_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                event.event_id,
                run_id,
                author_score_ids.get(event.account_id),
                event.account_id,
                event.account_name,
                event.author_nickname,
                event.security_id,
                event.security_key,
                event.display_name,
                event.ticker,
                event.market,
                event.event_trading_day,
                event.published_at,
                event.direction,
                event.conviction,
                event.evidence_type,
                _json(event.time_horizons),
                _json(event.content_ids),
                _json(event.viewpoint_ids),
                event.anchor_trading_day,
                event.anchor_price,
                event.anchor_price_kind,
                event.benchmark_symbol,
                event.benchmark_anchor_price,
                _json(event.horizon_scores),
            ),
        )


def _refresh_event_market_data(conn: Connection[dict[str, Any]], events: list[ScoreEvent]) -> tuple[int, list[str]]:
    if not events:
        return 0, []
    store = PostgresInsightStore(conn)
    keys = list(dict.fromkeys(event.security_key for event in events if event.security_key))
    from packages.ai.pipeline import refresh_security_market_data  # noqa: PLC0415

    return refresh_security_market_data(
        store=store,
        security_keys=keys,
        max_securities=len(keys),
        days=PRICE_WINDOW_DAYS,
        retain_days=PRICE_WINDOW_DAYS,
        delay_seconds=0.25,
        progress_label="[stock-blogger-score]",
    )


def rebuild_stock_blogger_scores_once(*, days: int = 90, refresh_market: bool = True) -> int:
    safe_days = max(1, int(days))
    accounts = _accounts_from_env()
    end_date = datetime.now(SHANGHAI_TZ).date()
    start_date = end_date - timedelta(days=safe_days - 1)
    run_id = str(uuid.uuid4())
    config = _config_payload(accounts, safe_days)

    with postgres_connection() as conn:
        _insert_run(
            conn,
            run_id=run_id,
            window_start=start_date.isoformat(),
            window_end=end_date.isoformat(),
            config=config,
            status="running",
            event_count=0,
            author_count=0,
        )
        mentions = _fetch_mentions(
            conn,
            accounts=accounts,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
        )
        events = build_events(mentions)
        market_errors: list[str] = []
        market_prices = 0
        if refresh_market and events:
            market_prices, market_errors = _refresh_event_market_data(conn, events)
        price_map = _load_price_map(conn, [event.security_id for event in events])
        benchmarks = _benchmark_sets(conn)
        scored_events = score_events(events, price_map, benchmarks)
        author_scores = aggregate_author_scores(scored_events)
        _persist_scores(conn, run_id=run_id, author_scores=author_scores, events=scored_events)
        _insert_run(
            conn,
            run_id=run_id,
            window_start=start_date.isoformat(),
            window_end=end_date.isoformat(),
            config={**config, "market_prices": market_prices},
            status="succeeded",
            event_count=len(scored_events),
            author_count=len(author_scores),
            error_text="; ".join(market_errors[:10]),
        )

    print(
        "[stock-blogger-score] rebuilt "
        f"run_id={run_id} start={start_date.isoformat()} end={end_date.isoformat()} "
        f"mentions={len(mentions)} events={len(events)} authors={len(author_scores)} "
        f"market_prices={market_prices} market_errors={len(market_errors)}"
    )
    for error in market_errors[:10]:
        print(error)
    return 0


def ensure_stock_blogger_accounts_once() -> int:
    accounts = _accounts_from_env()
    with postgres_connection() as conn:
        for account in accounts:
            row = conn.execute(
                """
                INSERT INTO public.x_accounts (
                  username, display_name, profile_url, status, approved_at, updated_at
                )
                VALUES (%s, %s, %s, 'approved', now(), now())
                ON CONFLICT(username) DO UPDATE SET
                  status = 'approved',
                  profile_url = COALESCE(NULLIF(public.x_accounts.profile_url, ''), EXCLUDED.profile_url),
                  display_name = COALESCE(NULLIF(public.x_accounts.display_name, ''), EXCLUDED.display_name),
                  approved_at = COALESCE(public.x_accounts.approved_at, now()),
                  updated_at = now()
                RETURNING id
                """,
                (account, account, f"https://x.com/{account}"),
            ).fetchone()
            if row is None:
                raise RuntimeError(f"Failed to ensure X account: {account}")
            conn.execute(
                """
                INSERT INTO public.account_domains (
                  account_id, domain, status, approved_at, rejected_at, disabled_at, updated_at
                )
                VALUES (%s, 'stock', 'approved', now(), null, null, now())
                ON CONFLICT(account_id, domain) DO UPDATE SET
                  status = 'approved',
                  approved_at = COALESCE(public.account_domains.approved_at, now()),
                  rejected_at = null,
                  disabled_at = null,
                  updated_at = now()
                """,
                (row["id"],),
            )
    print("[stock-blogger-score] ensured_accounts=" + ",".join(accounts))
    return 0
