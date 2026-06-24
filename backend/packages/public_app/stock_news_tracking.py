from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from psycopg.types.json import Jsonb

from packages.ai.client import LLMJsonClient
from packages.common.market_data import fetch_security_daily
from packages.common.postgres_database import PostgresInsightStore, postgres_connection
from packages.common.security_aliases import SecurityIdentity, resolve_security_identity
from packages.common.settings import load_settings
from packages.common.time_utils import now_iso


PROMPT_VERSION = "stock_news_tracking_v3_one_hop_compact"
TRACKING_MODEL = "gpt-5.4"
TRACKING_REASONING_EFFORT = "high"
MAX_TRACKED_STOCKS_PER_NEWS = 30
PRICE_WINDOW_DAYS = 180
PRICE_HORIZONS = (3, 7)
ALLOWED_BENEFIT_LAYERS = {"self", "peer", "upstream_1", "downstream_1"}
DEFAULT_TRACKING_PRICE_REFRESH_LIMIT = 25


@dataclass(frozen=True, slots=True)
class TrackingStockCandidate:
    identity: SecurityIdentity
    country_or_region: str
    benefit_layer: str
    core_link: str
    benefit_logic: str
    confidence: str
    raw_payload: dict[str, Any]


def _json(value: Any) -> Jsonb:
    return Jsonb(value)


def _clip(value: Any, limit: int = 4000) -> str:
    text = str(value or "").strip()
    return text[:limit]


def _as_record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _normalize_market(value: Any) -> str | None:
    raw = str(value or "").strip().upper()
    if not raw:
        return None
    aliases = {
        "A": "",
        "A股": "",
        "CHINA": "",
        "CHINA_A": "",
        "CN": "",
        "SH": "SSE",
        "SS": "SSE",
        "SHA": "SSE",
        "SHANGHAI": "SSE",
        "SZ": "SZSE",
        "SHE": "SZSE",
        "SHENZHEN": "SZSE",
        "BJ": "BJSE",
        "BEIJING": "BJSE",
        "US": "US",
        "USA": "US",
        "NYSE": "NYSE",
        "NASDAQ": "NASDAQ",
        "AMEX": "AMEX",
        "JP": "TSE",
        "JAPAN": "TSE",
        "TYO": "TSE",
        "T": "TSE",
        "TSE": "TSE",
        "KR": "KRX",
        "KOREA": "KRX",
        "KS": "KRX",
        "KRX": "KRX",
        "KQ": "KOSDAQ",
        "KOSDAQ": "KOSDAQ",
        "TW": "TWSE",
        "TAIWAN": "TWSE",
        "TWSE": "TWSE",
        "TWO": "TPEX",
        "TPEX": "TPEX",
        "HK": "HKEX",
        "HKG": "HKEX",
        "SEHK": "HKEX",
        "HKEX": "HKEX",
    }
    normalized = aliases.get(raw, raw)
    return normalized or None


def _identifier_for_resolution(ticker: str, market: str | None) -> str:
    normalized_ticker = ticker.strip().upper()
    normalized_market = _normalize_market(market)
    if not normalized_ticker:
        return ""
    suffix_by_market = {
        "SSE": ".SH",
        "SZSE": ".SZ",
        "BJSE": ".BJ",
        "TSE": ".T",
        "KRX": ".KS",
        "KOSDAQ": ".KQ",
        "TWSE": ".TW",
        "TPEX": ".TWO",
        "HKEX": ".HK",
    }
    suffix = suffix_by_market.get(normalized_market or "")
    if suffix and not normalized_ticker.endswith(suffix):
        return f"{normalized_ticker}{suffix}"
    return normalized_ticker


def _candidate_to_identity(raw: dict[str, Any]) -> TrackingStockCandidate | None:
    company = _clip(raw.get("company_name") or raw.get("company") or raw.get("name"), 200)
    ticker = _clip(raw.get("ticker") or raw.get("symbol"), 80).upper()
    market = _normalize_market(raw.get("market") or raw.get("exchange"))
    country = _clip(raw.get("country_or_region") or raw.get("country") or raw.get("region"), 120)
    benefit_layer = _clip(raw.get("benefit_layer") or raw.get("layer"), 40).lower()
    core_link = _clip(raw.get("core_link") or raw.get("core_object") or raw.get("core"), 200)
    logic = _clip(raw.get("benefit_logic") or raw.get("logic") or raw.get("reason"), 400)
    confidence = _clip(raw.get("confidence") or "unknown", 40).lower() or "unknown"
    if not company and not ticker:
        return None
    if benefit_layer not in ALLOWED_BENEFIT_LAYERS:
        return None
    if not core_link or not logic:
        return None

    identifier = _identifier_for_resolution(ticker, market) if ticker else company
    identity = resolve_security_identity(identifier, company or ticker, {})
    if identity is None:
        return None
    if market and identity.market is None:
        identity = SecurityIdentity(
            security_key=identity.security_key,
            display_name=identity.display_name,
            ticker=identity.ticker,
            market=market,
        )
    if ticker and identity.ticker is None:
        identity = SecurityIdentity(
            security_key=identity.security_key,
            display_name=identity.display_name,
            ticker=ticker,
            market=identity.market,
        )
    return TrackingStockCandidate(
        identity=identity,
        country_or_region=country,
        benefit_layer=benefit_layer,
        core_link=core_link,
        benefit_logic=logic,
        confidence=confidence,
        raw_payload=raw,
    )


def _build_tracking_messages(event_snapshot: dict[str, Any]) -> list[dict[str, str]]:
    headline = _clip(event_snapshot.get("headline"), 1000)
    summary = _clip(event_snapshot.get("event_summary") or event_snapshot.get("eventSummary"), 3000)
    linked_entities = event_snapshot.get("linked_entities") or event_snapshot.get("linkedEntities") or []
    source = {
        "headline": headline,
        "event_summary": summary,
        "event_type": event_snapshot.get("event_type") or event_snapshot.get("eventType") or "other",
        "event_nature": event_snapshot.get("event_nature") or event_snapshot.get("eventNature") or "reported",
        "publish_time": event_snapshot.get("publish_time") or event_snapshot.get("publishTime"),
        "linked_entities": linked_entities,
    }
    return [
        {
            "role": "system",
            "content": (
                "你是全球股票事件映射分析师。只输出新闻核心对象一跳内的受益上市公司，覆盖日本、中国大陆、韩国、美国、台湾等市场。"
                "先识别新闻核心对象，再按 self、peer、upstream_1、downstream_1 四类输出标的。"
                "self 是新闻直接提到的公司或核心对象本身；peer 是同环节可替代公司；upstream_1 是直接供给核心对象的原材料、关键设备、工艺服务或耗材；downstream_1 是直接使用核心对象生产下一层产品的公司。"
                "只保留最直接的一跳标的，最多 30 只。不要扩展到终端应用或主题行情。不要输出基金、ETF、指数、未上市公司或无法交易标的。只输出 JSON。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请基于这条新闻输出最多 30 只可能受益股票，只能使用 self、peer、upstream_1、downstream_1 四种 benefit_layer。"
                "benefit_logic 写成一句结果话，简短说明核心对象、该公司所在的一跳位置、受益原因。"
                "JSON 格式必须为：{\"stocks\":[{\"company_name\":\"...\",\"ticker\":\"...\","
                "\"market\":\"NASDAQ/NYSE/SSE/SZSE/TSE/KRX/KOSDAQ/TWSE/TPEX/HKEX 等\","
                "\"country_or_region\":\"...\",\"benefit_layer\":\"self/peer/upstream_1/downstream_1\","
                "\"core_link\":\"新闻核心对象，如 InP、WF6、PCB、玻纤布、铜箔\","
                "\"benefit_logic\":\"...\",\"confidence\":\"high/medium/low\"}]}。\n"
                f"新闻：{source}"
            ),
        },
    ]


def _tracking_settings():
    settings = load_settings()
    return settings.model_copy(
        update={
            "model": TRACKING_MODEL,
            "fallback_models": [],
            "reasoning_effort": TRACKING_REASONING_EFFORT,
        }
    )


def analyze_pending_stock_news_tracking_once(*, limit: int = 5) -> int:
    processed = 0
    safe_limit = max(1, min(int(limit), 20))
    settings = _tracking_settings()
    client = LLMJsonClient(settings)

    with postgres_connection() as conn:
        rows = conn.execute(
            """
            SELECT id::text AS id, event_key, event_snapshot_json
            FROM public.stock_news_tracking
            WHERE status = 'pending'
            ORDER BY created_at ASC
            LIMIT %s
            """,
            (safe_limit,),
        ).fetchall()
        for row in rows:
            tracking_id = str(row["id"])
            conn.execute(
                """
                UPDATE public.stock_news_tracking
                SET status = 'analyzing', analysis_started_at = now(), error_text = '', updated_at = now()
                WHERE id = %s AND status = 'pending'
                """,
                (tracking_id,),
            )
            try:
                event_snapshot = _as_record(row["event_snapshot_json"])
                result = client.generate_json(
                    _build_tracking_messages(event_snapshot),
                    required_keys=["stocks"],
                    max_tokens=6000,
                )
                candidates: list[TrackingStockCandidate] = []
                seen_keys: set[str] = set()
                for raw_item in _as_list(result.parsed.get("stocks")):
                    candidate = _candidate_to_identity(_as_record(raw_item))
                    if candidate is None or candidate.identity.security_key in seen_keys:
                        continue
                    seen_keys.add(candidate.identity.security_key)
                    candidates.append(candidate)
                    if len(candidates) >= MAX_TRACKED_STOCKS_PER_NEWS:
                        break
                _replace_tracking_stocks(conn, tracking_id, candidates)
                conn.execute(
                    """
                    UPDATE public.stock_news_tracking
                    SET status = 'succeeded',
                        analyzed_at = now(),
                        model_name = %s,
                        request_id = %s,
                        usage_json = %s,
                        raw_response_json = %s,
                        error_text = '',
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (
                        result.model_name,
                        result.request_id,
                        _json(result.usage),
                        _json(result.parsed),
                        tracking_id,
                    ),
                )
                processed += 1
            except Exception as exc:
                conn.execute(
                    """
                    UPDATE public.stock_news_tracking
                    SET status = 'failed', error_text = %s, updated_at = now()
                    WHERE id = %s
                    """,
                    (_clip(exc, 1200), tracking_id),
                )
        conn.commit()

    print(f"[stock-news-tracking] analyzed={processed} pending_seen={len(rows)}")
    return 0


def _replace_tracking_stocks(conn: Any, tracking_id: str, candidates: list[TrackingStockCandidate]) -> None:
    store = PostgresInsightStore(conn)
    tracking_row = conn.execute(
        """
        SELECT event_date, event_snapshot_json
        FROM public.stock_news_tracking
        WHERE id = %s
        LIMIT 1
        """,
        (tracking_id,),
    ).fetchone()
    selected_date = str(tracking_row["event_date"]).strip() if tracking_row and tracking_row.get("event_date") else ""
    if not selected_date and tracking_row:
        snapshot = _as_record(tracking_row.get("event_snapshot_json"))
        selected_date = _clip(snapshot.get("date"), 32)
    if not selected_date:
        raise ValueError(f"Tracking item {tracking_id} is missing event_date for price anchoring.")
    conn.execute("DELETE FROM public.stock_news_tracking_stocks WHERE tracking_id = %s", (tracking_id,))
    for sort_order, candidate in enumerate(candidates, start=1):
        security_id = store.ensure_security(candidate.identity, candidate.identity.display_name)
        conn.execute(
            """
            INSERT INTO public.stock_news_tracking_stocks (
              tracking_id, sort_order, security_id, security_key, display_name, ticker, market,
              country_or_region, benefit_logic, confidence, selected_date, raw_payload_json, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
            """,
            (
                tracking_id,
                sort_order,
                security_id,
                candidate.identity.security_key,
                candidate.identity.display_name,
                candidate.identity.ticker,
                candidate.identity.market,
                candidate.country_or_region,
                candidate.benefit_logic,
                candidate.confidence,
                selected_date,
                _json(candidate.raw_payload),
            ),
        )


def _load_price_candles(conn: Any, security_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT date_key, close_price
        FROM public.security_daily_prices
        WHERE security_id = %s
        ORDER BY date_key ASC
        """,
        (security_id,),
    ).fetchall()
    return [{"date": str(row["date_key"]), "close": float(row["close_price"])} for row in rows]


def _return_from(anchor: float | None, target: float | None) -> float | None:
    if anchor is None or target is None or anchor == 0:
        return None
    return (target - anchor) / anchor


def _score_prices(candles: list[dict[str, Any]], selected_date: str) -> dict[str, Any]:
    if not candles:
        return {
            "price_status": "missing_price",
            "anchor_status": "missing_price",
            "horizon_3_status": "missing_price",
            "horizon_7_status": "missing_price",
        }
    anchor_index = next((index for index, candle in enumerate(candles) if candle["date"] >= selected_date), None)
    if anchor_index is None:
        return {
            "price_status": "pending",
            "anchor_status": "pending",
            "latest_date": candles[-1]["date"],
            "latest_price": candles[-1]["close"],
            "horizon_3_status": "pending",
            "horizon_7_status": "pending",
        }
    anchor = candles[anchor_index]
    latest = candles[-1]
    payload: dict[str, Any] = {
        "price_status": "scored",
        "anchor_status": "exact" if anchor["date"] == selected_date else "next_trading_day",
        "anchor_date": anchor["date"],
        "anchor_price": anchor["close"],
        "latest_date": latest["date"],
        "latest_price": latest["close"],
        "return_since_selected": _return_from(anchor["close"], latest["close"]),
    }
    for horizon in PRICE_HORIZONS:
        target_index = anchor_index + horizon
        if target_index >= len(candles):
            payload[f"horizon_{horizon}_status"] = "pending"
            payload[f"return_{horizon}d"] = None
            continue
        target = candles[target_index]
        payload[f"horizon_{horizon}_status"] = "scored"
        payload[f"target_{horizon}d_date"] = target["date"]
        payload[f"return_{horizon}d"] = _return_from(anchor["close"], target["close"])
    return payload


def refresh_stock_news_tracking_prices_once(*, delay_seconds: float = 0.25, limit: int = DEFAULT_TRACKING_PRICE_REFRESH_LIMIT) -> int:
    import time

    refreshed = 0
    errors = 0
    safe_limit = max(1, min(int(limit), 200))
    with postgres_connection() as conn:
        store = PostgresInsightStore(conn)
        rows = conn.execute(
            """
            SELECT
              t.id::text AS row_id,
              t.tracking_id::text AS tracking_id,
              t.security_id::text AS security_id,
              t.security_key,
              t.display_name,
              t.ticker,
              t.market,
              t.selected_date,
              n.event_date
            FROM public.stock_news_tracking_stocks t
            JOIN public.stock_news_tracking n ON n.id = t.tracking_id
            WHERE n.status = 'succeeded'
            ORDER BY t.last_price_checked_at ASC NULLS FIRST, n.event_date ASC NULLS FIRST, n.created_at ASC, t.sort_order ASC
            LIMIT %s
            """,
            (safe_limit,),
        ).fetchall()
        for index, row in enumerate(rows):
            row_id = str(row["row_id"])
            security_key = str(row["security_key"])
            try:
                anchored_selected_date = str(row["event_date"]).strip() if row.get("event_date") else str(row["selected_date"]).strip()
                if not anchored_selected_date:
                    raise ValueError(f"Tracked stock row {row_id} is missing event_date and selected_date.")
                if anchored_selected_date != str(row["selected_date"]).strip():
                    conn.execute(
                        """
                        UPDATE public.stock_news_tracking_stocks
                        SET selected_date = %s, updated_at = now()
                        WHERE id = %s
                        """,
                        (anchored_selected_date, row_id),
                    )
                payload = fetch_security_daily(
                    ticker=str(row["ticker"]).strip() if row["ticker"] else None,
                    market=str(row["market"]).strip() if row["market"] else None,
                    security_key=security_key,
                    days=PRICE_WINDOW_DAYS,
                )
                candles = payload.get("candles") or []
                if candles:
                    store.upsert_security_daily_prices(
                        security_key=security_key,
                        source=str(payload.get("sourceLabel") or "Unknown"),
                        source_symbol=str(payload.get("sourceSymbol") or row["ticker"] or security_key),
                        candles=candles,
                        fetched_at=now_iso(),
                    )
                    conn.commit()
                price_payload = _score_prices(_load_price_candles(conn, str(row["security_id"])), anchored_selected_date)
                conn.execute(
                    """
                    UPDATE public.stock_news_tracking_stocks
                    SET price_status = %s,
                        anchor_status = %s,
                        anchor_date = %s,
                        anchor_price = %s,
                        latest_date = %s,
                        latest_price = %s,
                        horizon_3_status = %s,
                        return_3d = %s,
                        target_3d_date = %s,
                        horizon_7_status = %s,
                        return_7d = %s,
                        target_7d_date = %s,
                        return_since_selected = %s,
                        last_price_checked_at = now(),
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (
                        price_payload.get("price_status", "missing_price"),
                        price_payload.get("anchor_status", "missing_price"),
                        price_payload.get("anchor_date"),
                        price_payload.get("anchor_price"),
                        price_payload.get("latest_date"),
                        price_payload.get("latest_price"),
                        price_payload.get("horizon_3_status", "missing_price"),
                        price_payload.get("return_3d"),
                        price_payload.get("target_3d_date"),
                        price_payload.get("horizon_7_status", "missing_price"),
                        price_payload.get("return_7d"),
                        price_payload.get("target_7d_date"),
                        price_payload.get("return_since_selected"),
                        row_id,
                    ),
                )
                refreshed += 1
            except Exception as exc:
                errors += 1
                conn.execute(
                    """
                    UPDATE public.stock_news_tracking_stocks
                    SET price_status = 'missing_price', price_error = %s, last_price_checked_at = now(), updated_at = now()
                    WHERE id = %s
                    """,
                    (_clip(exc, 800), row_id),
                )
            if delay_seconds > 0 and index < len(rows) - 1:
                time.sleep(delay_seconds)
        conn.commit()

    print(f"[stock-news-tracking] price_refreshed={refreshed} price_errors={errors}")
    return 0 if refreshed or not errors else 1
