from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from psycopg.types.json import Jsonb

from packages.ai.client import LLMJsonClient
from packages.ai.prompts import STOCK_NARRATIVE_REQUIRED_KEYS, build_stock_narrative_messages
from packages.common.postgres_database import postgres_connection
from packages.common.settings import load_settings


PROMPT_VERSION = "stock_narrative_v1"
CURRENT_WINDOW_DAYS = 7
SHORT_BASELINE_DAYS = 14
LONG_BASELINE_DAYS = 30
MAX_TOPIC_ITEMS = 18
MAX_SAMPLE_EVIDENCE = 2
MAX_LOGIC_CHARS = 220
MAX_EVIDENCE_CHARS = 140

TOPIC_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("AI 算力链", ("ai", "人工智能", "算力", "gpu", "hbm", "数据中心", "服务器", "英伟达", "nvda", "asic")),
    ("半导体 / 先进封装", ("半导体", "芯片", "先进封装", "晶圆", "代工", "foundry", "台积电", "tsmc", "intel foundry")),
    ("电力 / 核电 / 数据中心能耗", ("电力", "核电", "电网", "用电", "能源", "发电", "数据中心能耗", "smr")),
    ("稳定币 / 支付金融", ("稳定币", "stablecoin", "支付", "金融科技", "fintech", "usdc", "circle")),
    ("加密相关股票", ("比特币", "bitcoin", "crypto", "加密", "矿企", "挖矿", "交易所", "coinbase", "mstr")),
    ("机器人 / 自动化", ("机器人", "robot", "自动化", "humanoid", "人形")),
    ("国防 / 无人机", ("国防", "军工", "无人机", "drone", "defense")),
    ("医药 / 生物科技", ("医药", "生物科技", "biotech", "fda", "临床", "药物", "glp-1")),
    ("消费 / 零售", ("消费", "零售", "门店", "同店", "品牌", "电商", "广告")),
    ("汽车 / 电动车", ("汽车", "电动车", "ev", "自动驾驶", "robotaxi", "fsd")),
    ("软件 / 云服务", ("软件", "saas", "云", "cloud", "订阅", "数据库", "安全软件")),
    ("估值 / 资金流", ("估值", "pe", "pb", "资金流", "回购", "仓位", "机构", "持仓")),
    ("财报 / 指引", ("财报", "业绩", "营收", "利润", "eps", "guidance", "指引", "订单")),
)

EVIDENCE_TYPE_LABELS = {
    "price_action": "价格行为",
    "earnings": "财报",
    "guidance": "指引",
    "management_commentary": "管理层表述",
    "valuation": "估值",
    "policy": "政策",
    "rumor": "传闻",
    "position": "持仓",
    "capital_flow": "资金流",
    "technical": "技术面",
    "macro": "宏观",
    "other": "其他证据",
}


@dataclass(frozen=True)
class StockNarrativeViewpoint:
    date: str
    account_name: str
    author_nickname: str
    direction: str
    signal_type: str
    judgment_type: str
    conviction: str
    evidence_type: str
    logic: str
    evidence: tuple[str, ...]
    security_key: str
    security_display_name: str
    ticker: str
    market: str


@dataclass(frozen=True)
class BriefReference:
    id: str
    brief_date: str
    window_start: str
    window_end: str
    brief_text: str
    sections: dict[str, Any]


def _clip(text: str, limit: int) -> str:
    clean = " ".join(str(text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "…"


def _normalize_date(value: Any) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return str(value or "")[:10]


def _normalize_author(value: Any) -> str:
    return str(value or "").strip().lstrip("@").lower()


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _as_date(value: str) -> date:
    return date.fromisoformat(value[:10])


def _select_effective_dates(
    dates: list[str],
    *,
    target_date: str | None,
    window_days: int = CURRENT_WINDOW_DAYS,
) -> list[str]:
    ordered = sorted({item for item in dates if item})
    if target_date:
        ordered = [item for item in ordered if item <= target_date]
    return ordered[-max(1, window_days) :]


def _previous_effective_dates(
    dates: list[str],
    *,
    current_window_start: str,
    window_days: int = CURRENT_WINDOW_DAYS,
) -> list[str]:
    ordered = sorted({item for item in dates if item and item < current_window_start})
    return ordered[-max(1, window_days) :]


def _match_topics(record: StockNarrativeViewpoint) -> list[str]:
    text = " ".join([record.logic, *record.evidence, record.security_display_name, record.ticker]).lower()
    topics = [topic for topic, markers in TOPIC_PATTERNS if any(marker.lower() in text for marker in markers)]
    if topics:
        return topics
    if record.evidence_type in EVIDENCE_TYPE_LABELS:
        return [f"证据类型：{EVIDENCE_TYPE_LABELS[record.evidence_type]}"]
    return [f"个股讨论：{record.security_display_name or record.security_key}"]


def _build_topic_baseline(
    records: list[StockNarrativeViewpoint],
    *,
    current_dates: set[str],
    baseline_start: str,
    baseline_end: str,
    limit: int = MAX_TOPIC_ITEMS,
) -> list[dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for record in records:
        if not (baseline_start <= record.date <= baseline_end):
            continue
        for topic in _match_topics(record):
            item = stats.setdefault(
                topic,
                {
                    "topic": topic,
                    "first_seen_date": record.date,
                    "last_seen_date": record.date,
                    "baseline_count": 0,
                    "recent_7d_count": 0,
                    "author_names": set(),
                    "positive_count": 0,
                    "negative_count": 0,
                    "sample_evidence": [],
                },
            )
            item["first_seen_date"] = min(item["first_seen_date"], record.date)
            item["last_seen_date"] = max(item["last_seen_date"], record.date)
            item["baseline_count"] += 1
            if record.date in current_dates:
                item["recent_7d_count"] += 1
            item["author_names"].add(record.account_name)
            if record.direction == "positive":
                item["positive_count"] += 1
            elif record.direction == "negative":
                item["negative_count"] += 1
            evidence_text = record.evidence[0] if record.evidence else record.logic
            if evidence_text and len(item["sample_evidence"]) < MAX_SAMPLE_EVIDENCE:
                clipped = _clip(evidence_text, MAX_EVIDENCE_CHARS)
                if clipped not in item["sample_evidence"]:
                    item["sample_evidence"].append(clipped)

    rows: list[dict[str, Any]] = []
    for item in stats.values():
        rows.append(
            {
                "topic": item["topic"],
                "first_seen_date": item["first_seen_date"],
                "last_seen_date": item["last_seen_date"],
                "recent_7d_count": item["recent_7d_count"],
                "baseline_count": item["baseline_count"],
                "author_count": len(item["author_names"]),
                "positive_count": item["positive_count"],
                "negative_count": item["negative_count"],
                "sample_evidence": item["sample_evidence"],
            }
        )
    return sorted(
        rows,
        key=lambda item: (
            -int(item["recent_7d_count"]),
            -int(item["author_count"]),
            -int(item["baseline_count"]),
            str(item["topic"]),
        ),
    )[:limit]


def _current_input_items(records: list[StockNarrativeViewpoint], current_dates: set[str]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        if record.date not in current_dates:
            continue
        item = grouped.setdefault(
            (record.date, record.account_name),
            {
                "author": record.author_nickname or record.account_name,
                "account_name": record.account_name,
                "date": record.date,
                "direction": "unknown",
                "positive_count": 0,
                "negative_count": 0,
                "logic_parts": [],
                "evidence": [],
            },
        )
        if record.direction == "positive":
            item["positive_count"] += 1
        elif record.direction == "negative":
            item["negative_count"] += 1
        logic = _clip(record.logic, MAX_LOGIC_CHARS)
        if logic and logic not in item["logic_parts"] and len(item["logic_parts"]) < 3:
            item["logic_parts"].append(logic)
        for evidence in record.evidence:
            clipped = _clip(evidence, MAX_EVIDENCE_CHARS)
            if clipped and clipped not in item["evidence"] and len(item["evidence"]) < 1:
                item["evidence"].append(clipped)
    items: list[dict[str, Any]] = []
    for item in grouped.values():
        positive_count = int(item.pop("positive_count"))
        negative_count = int(item.pop("negative_count"))
        logic_parts = item.pop("logic_parts")
        if positive_count and negative_count:
            item["direction"] = "mixed"
        elif negative_count:
            item["direction"] = "negative"
        elif positive_count:
            item["direction"] = "positive"
        item["direction_counts"] = {"positive": positive_count, "negative": negative_count}
        item["logic"] = "；".join(logic_parts)
        items.append(item)
    return sorted(items, key=lambda item: (str(item["date"]), str(item["account_name"])))


def _find_reference_briefs(
    briefs: list[BriefReference],
    *,
    current_window_start: str,
) -> tuple[BriefReference | None, BriefReference | None]:
    continuity = briefs[0] if briefs else None
    comparison = next(
        (item for item in briefs if item.window_end and item.window_end < current_window_start),
        None,
    )
    return continuity, comparison


def _normalize_sections(payload: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "mainstream_narrative": _string_list(payload.get("mainstream_narrative")),
        "new_directions": _string_list(payload.get("new_directions")),
        "rare_negative_signals": _string_list(payload.get("rare_negative_signals")),
    }


def _fallback_brief_text(sections: dict[str, list[str]]) -> str:
    parts: list[str] = []
    labels = (
        ("主流叙事", sections["mainstream_narrative"]),
        ("新风向", sections["new_directions"]),
        ("少见负面声音", sections["rare_negative_signals"]),
    )
    for label, values in labels:
        if values:
            parts.append(label + "：" + "；".join(values))
    return "\n\n".join(parts)


def _fetch_stock_viewpoints(conn: Any) -> list[StockNarrativeViewpoint]:
    rows = conn.execute(
        """
        with approved as (
          select lower(a.username::text) as account_name, coalesce(nullif(a.display_name::text, ''), a.username::text) as display_name
          from x_accounts a
          join account_domains ad on ad.account_id = a.id
          where ad.domain = 'stock'
            and ad.status = 'approved'
        ),
        expanded as (
          select
            sdv.date_key::date as date_key,
            se.security_key::text as security_key,
            se.display_name::text as security_display_name,
            coalesce(se.ticker::text, '') as ticker,
            coalesce(se.market::text, '') as market,
            view_item.value as view_value,
            lower(regexp_replace(coalesce(view_item.value ->> 'account_name', view_item.value ->> 'author_name', view_item.value ->> 'username', ''), '^@', '')) as account_name
          from security_daily_views sdv
          join security_entities se on se.id = sdv.security_id
          cross join lateral jsonb_array_elements(coalesce(sdv.author_views_json, '[]'::jsonb)) as view_item(value)
          where coalesce(view_item.value ->> 'signal_type', '') in ('explicit_stance', 'logic_based')
            and coalesce(view_item.value ->> 'direction', '') in ('positive', 'negative')
            and coalesce(view_item.value ->> 'judgment_type', '') not in ('factual_only', 'quoted', 'mention_only')
        )
        select e.*, a.display_name as approved_display_name
        from expanded e
        join approved a on a.account_name = e.account_name
        order by e.date_key asc, e.account_name asc, e.security_key asc
        """
    ).fetchall()
    records: list[StockNarrativeViewpoint] = []
    for row in rows:
        view = dict(row["view_value"] or {})
        evidence = tuple(_string_list(view.get("evidence")))
        records.append(
            StockNarrativeViewpoint(
                date=_normalize_date(row["date_key"]),
                account_name=_normalize_author(row["account_name"]),
                author_nickname=str(view.get("author_nickname") or row["approved_display_name"] or row["account_name"]),
                direction=str(view.get("direction") or "unknown"),
                signal_type=str(view.get("signal_type") or "unknown"),
                judgment_type=str(view.get("judgment_type") or "unknown"),
                conviction=str(view.get("conviction") or "unknown"),
                evidence_type=str(view.get("evidence_type") or "unknown"),
                logic=str(view.get("logic") or "").strip(),
                evidence=evidence,
                security_key=str(row["security_key"] or ""),
                security_display_name=str(row["security_display_name"] or row["security_key"] or ""),
                ticker=str(row["ticker"] or ""),
                market=str(row["market"] or ""),
            )
        )
    return records


def _fetch_existing_success(conn: Any, brief_date: str) -> dict[str, Any] | None:
    return conn.execute(
        """
        select id, brief_date::text as brief_date, status, updated_at
        from stock_narrative_briefs
        where brief_date = %s::date
          and status = 'succeeded'
          and nullif(brief_text, '') is not null
        """,
        (brief_date,),
    ).fetchone()


def _fetch_previous_briefs(conn: Any, brief_date: str) -> list[BriefReference]:
    rows = conn.execute(
        """
        select
          id::text,
          brief_date::text as brief_date,
          coalesce(window_start::text, '') as window_start,
          coalesce(window_end::text, '') as window_end,
          brief_text,
          brief_sections_json
        from stock_narrative_briefs
        where status = 'succeeded'
          and brief_date < %s::date
          and nullif(brief_text, '') is not null
        order by brief_date desc, updated_at desc
        limit 20
        """,
        (brief_date,),
    ).fetchall()
    return [
        BriefReference(
            id=str(row["id"]),
            brief_date=str(row["brief_date"]),
            window_start=str(row["window_start"] or ""),
            window_end=str(row["window_end"] or ""),
            brief_text=str(row["brief_text"] or ""),
            sections=dict(row["brief_sections_json"] or {}),
        )
        for row in rows
    ]


def _upsert_brief(
    conn: Any,
    *,
    brief_date: str,
    window_start: str | None,
    window_end: str | None,
    previous_window_start: str | None,
    previous_window_end: str | None,
    baseline_start: str | None,
    baseline_end: str | None,
    status: str,
    input_digest: dict[str, Any],
    sections: dict[str, Any],
    brief_text: str,
    model_name: str | None,
    usage: dict[str, Any],
    error_text: str | None = None,
) -> None:
    conn.execute(
        """
        insert into stock_narrative_briefs (
          brief_date, window_start, window_end, previous_window_start, previous_window_end,
          baseline_start, baseline_end, status, input_digest_json, brief_sections_json,
          brief_text, model_name, prompt_version, usage_json, error_text, updated_at
        )
        values (
          %s::date, nullif(%s, '')::date, nullif(%s, '')::date, nullif(%s, '')::date, nullif(%s, '')::date,
          nullif(%s, '')::date, nullif(%s, '')::date, %s, %s, %s,
          %s, %s, %s, %s, nullif(%s, ''), now()
        )
        on conflict (brief_date) do update set
          window_start = excluded.window_start,
          window_end = excluded.window_end,
          previous_window_start = excluded.previous_window_start,
          previous_window_end = excluded.previous_window_end,
          baseline_start = excluded.baseline_start,
          baseline_end = excluded.baseline_end,
          status = excluded.status,
          input_digest_json = excluded.input_digest_json,
          brief_sections_json = excluded.brief_sections_json,
          brief_text = excluded.brief_text,
          model_name = excluded.model_name,
          prompt_version = excluded.prompt_version,
          usage_json = excluded.usage_json,
          error_text = excluded.error_text,
          updated_at = now()
        """,
        (
            brief_date,
            window_start or "",
            window_end or "",
            previous_window_start or "",
            previous_window_end or "",
            baseline_start or "",
            baseline_end or "",
            status,
            Jsonb(input_digest),
            Jsonb(sections),
            brief_text,
            model_name,
            PROMPT_VERSION,
            Jsonb(usage),
            _clip(error_text or "", 800),
        ),
    )


def build_stock_narrative_input(
    records: list[StockNarrativeViewpoint],
    *,
    target_date: str | None = None,
    previous_briefs: list[BriefReference] | None = None,
) -> dict[str, Any]:
    all_dates = sorted({record.date for record in records})
    current_dates = _select_effective_dates(all_dates, target_date=target_date)
    if not current_dates:
        raise ValueError("no stock viewpoints available for narrative window")
    window_start = current_dates[0]
    window_end = current_dates[-1]
    previous_dates = _previous_effective_dates(all_dates, current_window_start=window_start)
    baseline_end = window_end
    baseline_start_30d = (_as_date(window_end) - timedelta(days=LONG_BASELINE_DAYS - 1)).isoformat()
    baseline_start_14d = (_as_date(window_end) - timedelta(days=SHORT_BASELINE_DAYS - 1)).isoformat()
    current_date_set = set(current_dates)
    current_records = [record for record in records if record.date in current_date_set]
    previous_records = [record for record in records if record.date in set(previous_dates)]
    continuity, comparison = _find_reference_briefs(previous_briefs or [], current_window_start=window_start)

    current_authors = {record.account_name for record in current_records}
    negative_records = [record for record in current_records if record.direction == "negative"]
    positive_records = [record for record in current_records if record.direction == "positive"]

    return {
        "prompt_version": PROMPT_VERSION,
        "scope": "all_approved_stock_accounts",
        "brief_date": target_date or window_end,
        "current_window": {
            "start": window_start,
            "end": window_end,
            "effective_dates": current_dates,
            "viewpoint_count": len(current_records),
            "author_count": len(current_authors),
            "positive_count": len(positive_records),
            "negative_count": len(negative_records),
        },
        "previous_non_overlap_window": {
            "start": previous_dates[0] if previous_dates else None,
            "end": previous_dates[-1] if previous_dates else None,
            "effective_dates": previous_dates,
            "viewpoint_count": len(previous_records),
            "author_count": len({record.account_name for record in previous_records}),
        },
        "baseline": {
            "start": baseline_start_30d,
            "end": baseline_end,
            "lookback_days": LONG_BASELINE_DAYS,
            "topic_baseline_14d": _build_topic_baseline(
                records,
                current_dates=current_date_set,
                baseline_start=baseline_start_14d,
                baseline_end=baseline_end,
                limit=12,
            ),
            "topic_baseline_30d": _build_topic_baseline(
                records,
                current_dates=current_date_set,
                baseline_start=baseline_start_30d,
                baseline_end=baseline_end,
                limit=MAX_TOPIC_ITEMS,
            ),
        },
        "current_viewpoints": _current_input_items(records, current_date_set),
        "previous_non_overlap_brief": None
        if comparison is None
        else {
            "brief_date": comparison.brief_date,
            "window_start": comparison.window_start,
            "window_end": comparison.window_end,
            "brief_text": _clip(comparison.brief_text, 1200),
            "sections": comparison.sections,
        },
        "continuity_brief": None
        if continuity is None
        else {
            "brief_date": continuity.brief_date,
            "window_start": continuity.window_start,
            "window_end": continuity.window_end,
            "brief_text": _clip(continuity.brief_text, 1200),
            "sections": continuity.sections,
        },
    }


def generate_stock_narrative_once(*, brief_date: str | None = None, force: bool = False) -> int:
    with postgres_connection() as conn:
        records = _fetch_stock_viewpoints(conn)
        if not records:
            print("[public-worker] stock_narrative skipped reason=no_stock_viewpoints")
            return 0
        target = brief_date or max(record.date for record in records)
        existing_success = _fetch_existing_success(conn, target)
        if existing_success and not force:
            print(f"[public-worker] stock_narrative skipped reason=already_exists brief_date={target}")
            return 0
        previous_briefs = _fetch_previous_briefs(conn, target)
        try:
            input_digest = build_stock_narrative_input(records, target_date=target, previous_briefs=previous_briefs)
        except Exception as exc:
            _upsert_brief(
                conn,
                brief_date=target,
                window_start=None,
                window_end=None,
                previous_window_start=None,
                previous_window_end=None,
                baseline_start=None,
                baseline_end=None,
                status="skipped",
                input_digest={},
                sections={},
                brief_text="",
                model_name=None,
                usage={},
                error_text=str(exc),
            )
            print(f"[public-worker] stock_narrative skipped reason={_clip(str(exc), 160)} brief_date={target}")
            return 0

        window = input_digest["current_window"]
        previous_window = input_digest["previous_non_overlap_window"]
        baseline = input_digest["baseline"]

        try:
            client = LLMJsonClient(load_settings())
            result = client.generate_json(
                build_stock_narrative_messages(input_digest),
                required_keys=STOCK_NARRATIVE_REQUIRED_KEYS,
                max_tokens=2600,
            )
            sections = _normalize_sections(result.parsed)
            brief_text = str(result.parsed.get("brief_text") or "").strip() or _fallback_brief_text(sections)
            if not brief_text:
                raise RuntimeError("AI response did not include brief_text")
            _upsert_brief(
                conn,
                brief_date=target,
                window_start=window["start"],
                window_end=window["end"],
                previous_window_start=previous_window["start"],
                previous_window_end=previous_window["end"],
                baseline_start=baseline["start"],
                baseline_end=baseline["end"],
                status="succeeded",
                input_digest=input_digest,
                sections=sections,
                brief_text=brief_text,
                model_name=result.model_name,
                usage=result.usage,
            )
        except Exception as exc:
            if not existing_success:
                _upsert_brief(
                    conn,
                    brief_date=target,
                    window_start=window["start"],
                    window_end=window["end"],
                    previous_window_start=previous_window["start"],
                    previous_window_end=previous_window["end"],
                    baseline_start=baseline["start"],
                    baseline_end=baseline["end"],
                    status="failed",
                    input_digest=input_digest,
                    sections={},
                    brief_text="",
                    model_name=None,
                    usage={},
                    error_text=str(exc),
                )
            print(
                "[public-worker] stock_narrative failed "
                f"brief_date={target} window={window['start']}..{window['end']} error={_clip(str(exc), 180)}"
            )
            return 1

    usage = result.usage
    print(
        "[public-worker] stock_narrative "
        f"status=succeeded brief_date={target} "
        f"window={window['start']}..{window['end']} "
        f"viewpoints={window['viewpoint_count']} authors={window['author_count']} "
        f"input_tokens={int(usage.get('input_tokens', 0))} "
        f"output_tokens={int(usage.get('output_tokens', 0))}"
    )
    return 0
