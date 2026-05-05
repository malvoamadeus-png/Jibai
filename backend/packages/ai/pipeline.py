from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from datetime import date as date_class, timedelta
from typing import Any

from packages.common.database import InsightStore, init_db, sqlite_connection
from packages.common.io import safe_filename, write_json
from packages.common.market_data import fetch_security_daily
from packages.common.models import (
    AnalysisSnapshot,
    AuthorDayRecord,
    AuthorDayViewpoint,
    AuthorTimelineNote,
    CrawlAccountResult,
    EntityAuthorView,
    NoteExtractRecord,
    RawNoteRecord,
    StockDayRecord,
    ThemeDayRecord,
    ViewConviction,
    ViewDirection,
    ViewEvidenceType,
    ViewHorizon,
    ViewJudgmentType,
    ViewpointRecord,
    ViewStance,
)
from packages.common.paths import AppPaths
from packages.common.security_aliases import (
    SecurityIdentity,
    load_security_aliases,
    resolve_security_identity,
)
from packages.common.settings import load_settings
from packages.common.time_utils import note_date_key, now_iso, today_date_key

from .client import LLMJsonClient
from .prompts import (
    AUTHOR_SUMMARY_REQUIRED_KEYS,
    NOTE_EXTRACT_REQUIRED_KEYS,
    build_author_day_summary_messages,
    build_note_extract_messages,
)


ANALYSIS_VERSION = "viewpoints_v3"
STANCE_PRIORITY: dict[ViewStance, int] = {
    "strong_bullish": 5,
    "bullish": 4,
    "neutral": 3,
    "bearish": 2,
    "strong_bearish": 1,
    "mixed": 0,
    "mention_only": -1,
    "unknown": -2,
}
VALID_STANCES = set(STANCE_PRIORITY)
VALID_DIRECTIONS: set[ViewDirection] = {"positive", "negative", "neutral", "mixed", "unknown"}
VALID_JUDGMENT_TYPES: set[ViewJudgmentType] = {
    "direct",
    "implied",
    "factual_only",
    "quoted",
    "mention_only",
    "unknown",
}
VALID_CONVICTIONS: set[ViewConviction] = {"strong", "medium", "weak", "none", "unknown"}
VALID_EVIDENCE_TYPES: set[ViewEvidenceType] = {
    "price_action",
    "earnings",
    "guidance",
    "management_commentary",
    "valuation",
    "policy",
    "rumor",
    "position",
    "capital_flow",
    "technical",
    "macro",
    "other",
    "unknown",
}
VALID_HORIZONS: set[ViewHorizon] = {"short_term", "medium_term", "long_term", "unspecified"}


@dataclass(slots=True)
class AnalysisRunSummary:
    exit_code: int
    snapshot: AnalysisSnapshot
    market_prices: int = 0
    market_errors: list[str] = field(default_factory=list)


def _hash_payload(payload: object) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _note_key(platform: str, note_id: str) -> str:
    return f"{platform}::{note_id}"


def _account_key(platform: str, account_name: str) -> str:
    return f"{platform}::{account_name}"


def _normalize_entity_key(value: str, default: str) -> str:
    compact = " ".join(value.split()).casefold()
    return safe_filename(compact, default=default)


def _dedupe_preserve(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in values:
        cleaned = item.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def _merge_text(current: str, new_text: str) -> str:
    current_clean = current.strip()
    new_clean = new_text.strip()
    if not new_clean:
        return current_clean
    if not current_clean:
        return new_clean
    if new_clean in current_clean:
        return current_clean
    return f"{current_clean}；{new_clean}"


def _combine_stances(left: ViewStance, right: ViewStance) -> ViewStance:
    if left == right:
        return left
    if left == "unknown":
        return right
    if right == "unknown":
        return left
    if left == "mention_only":
        return right
    if right == "mention_only":
        return left
    positive = {"strong_bullish", "bullish"}
    negative = {"strong_bearish", "bearish"}
    if left in positive and right in positive:
        return "strong_bullish" if "strong_bullish" in {left, right} else "bullish"
    if left in negative and right in negative:
        return "strong_bearish" if "strong_bearish" in {left, right} else "bearish"
    if left == "neutral" and right == "neutral":
        return "neutral"
    return "mixed"


def _direction_from_stance(stance: ViewStance) -> ViewDirection:
    if stance in {"strong_bullish", "bullish"}:
        return "positive"
    if stance in {"strong_bearish", "bearish"}:
        return "negative"
    if stance == "neutral":
        return "neutral"
    if stance == "mixed":
        return "mixed"
    return "unknown"


def _derive_compatible_stance(
    *,
    direction: ViewDirection,
    judgment_type: ViewJudgmentType,
    conviction: ViewConviction,
    legacy_stance: ViewStance,
) -> ViewStance:
    if judgment_type == "mention_only":
        return "mention_only"
    if direction == "positive":
        return "strong_bullish" if conviction == "strong" else "bullish"
    if direction == "negative":
        return "strong_bearish" if conviction == "strong" else "bearish"
    if direction == "neutral":
        return "neutral"
    if direction == "mixed":
        return "mixed"
    return legacy_stance


def _combine_directions(left: ViewDirection, right: ViewDirection) -> ViewDirection:
    if left == right:
        return left
    if left == "unknown":
        return right
    if right == "unknown":
        return left
    directional = {left, right} - {"neutral"}
    if len(directional) == 1:
        return directional.pop()
    return "mixed"


def _combine_judgment_types(left: ViewJudgmentType, right: ViewJudgmentType) -> ViewJudgmentType:
    priority: dict[ViewJudgmentType, int] = {
        "direct": 5,
        "implied": 4,
        "factual_only": 3,
        "quoted": 2,
        "mention_only": 1,
        "unknown": 0,
    }
    return left if priority[left] >= priority[right] else right


def _combine_convictions(left: ViewConviction, right: ViewConviction) -> ViewConviction:
    priority: dict[ViewConviction, int] = {
        "strong": 4,
        "medium": 3,
        "weak": 2,
        "none": 1,
        "unknown": 0,
    }
    return left if priority[left] >= priority[right] else right


def _combine_evidence_types(left: ViewEvidenceType, right: ViewEvidenceType) -> ViewEvidenceType:
    if left == right:
        return left
    if left == "unknown":
        return right
    if right == "unknown":
        return left
    return "other"


def _fallback_note_summary(note: RawNoteRecord) -> str:
    title = note.title.strip()
    desc = note.desc.strip()
    if title and desc:
        return f"{title}：{desc[:180]}"
    if desc:
        return desc[:180]
    return title or f"内容 {note.note_id}"


def _stance_to_cn(stance: ViewStance) -> str:
    mapping = {
        "strong_bullish": "强烈看多",
        "bullish": "看多",
        "neutral": "中性",
        "bearish": "看空",
        "strong_bearish": "强烈看空",
        "mixed": "多空交织",
        "mention_only": "仅提及",
        "unknown": "态度不明",
    }
    return mapping.get(stance, stance)


def _fallback_author_summary(
    account_name: str,
    notes: list[RawNoteRecord],
    viewpoints: list[AuthorDayViewpoint],
) -> str:
    if viewpoints:
        ranked = sorted(
            viewpoints,
            key=lambda item: (STANCE_PRIORITY.get(item.stance, -9), item.entity_type, item.entity_name),
            reverse=True,
        )
        names = [item.entity_name for item in ranked[:3]]
        attitude = _stance_to_cn(ranked[0].stance)
        return f"{account_name} 当天主要围绕 {'、'.join(names)} 表达{attitude}观点。"
    if notes:
        titles = [note.title.strip() or note.desc.strip()[:24] for note in notes]
        merged = "；".join(item for item in titles if item)
        return merged[:220] if merged else f"{account_name} 当天发布了 {len(notes)} 条内容。"
    return f"{account_name} 当天无新内容。"


def _coerce_viewpoint_payloads(payload: dict[str, object]) -> list[dict[str, object]]:
    raw_viewpoints = payload.get("viewpoints")
    if isinstance(raw_viewpoints, list):
        return [item for item in raw_viewpoints if isinstance(item, dict)]

    legacy_mentions = payload.get("stock_mentions")
    if isinstance(legacy_mentions, list):
        converted: list[dict[str, object]] = []
        for item in legacy_mentions:
            if not isinstance(item, dict):
                continue
            converted.append(
                {
                    "entity_type": "stock",
                    "entity_name": item.get("stock_name") or item.get("stock_code_or_name") or "",
                    "entity_code_or_name": item.get("stock_code_or_name") or item.get("stock_name") or "",
                    "stance": item.get("stance") or "unknown",
                    "direction": _direction_from_stance(
                        item.get("stance") if item.get("stance") in VALID_STANCES else "unknown"  # type: ignore[arg-type]
                    ),
                    "judgment_type": "unknown",
                    "conviction": "unknown",
                    "evidence_type": "unknown",
                    "logic": item.get("view_summary") or "",
                    "evidence": item.get("evidence") or "",
                    "time_horizon": "unspecified",
                }
            )
        return converted
    return []


def _parse_viewpoint(
    raw: dict[str, object],
    *,
    order: int,
    aliases: dict[str, SecurityIdentity],
) -> ViewpointRecord | None:
    entity_type_raw = str(raw.get("entity_type") or "").strip().casefold()
    entity_type = entity_type_raw if entity_type_raw in {"stock", "theme", "macro", "other"} else ""
    legacy_stock_name = str(raw.get("stock_name") or "").strip()
    legacy_stock_key = str(raw.get("stock_code_or_name") or "").strip()
    entity_name = str(raw.get("entity_name") or legacy_stock_name or legacy_stock_key).strip()
    entity_code_or_name = str(raw.get("entity_code_or_name") or legacy_stock_key or entity_name).strip()
    if not entity_type and (legacy_stock_name or legacy_stock_key):
        entity_type = "stock"
    if not entity_type or not entity_name:
        return None

    stance_raw = str(raw.get("stance") or "unknown").strip()
    legacy_stance = stance_raw if stance_raw in VALID_STANCES else "unknown"
    direction_raw = str(raw.get("direction") or "").strip()
    direction = (
        direction_raw
        if direction_raw in VALID_DIRECTIONS
        else _direction_from_stance(legacy_stance)  # type: ignore[arg-type]
    )
    judgment_type_raw = str(raw.get("judgment_type") or "").strip()
    judgment_type = (
        judgment_type_raw if judgment_type_raw in VALID_JUDGMENT_TYPES else "unknown"
    )
    if judgment_type == "unknown" and legacy_stance == "mention_only":
        judgment_type = "mention_only"
    conviction_raw = str(raw.get("conviction") or "").strip()
    conviction = conviction_raw if conviction_raw in VALID_CONVICTIONS else "unknown"
    if conviction == "unknown" and judgment_type == "mention_only":
        conviction = "none"
    evidence_type_raw = str(raw.get("evidence_type") or "").strip()
    evidence_type = evidence_type_raw if evidence_type_raw in VALID_EVIDENCE_TYPES else "unknown"
    stance = _derive_compatible_stance(
        direction=direction,  # type: ignore[arg-type]
        judgment_type=judgment_type,  # type: ignore[arg-type]
        conviction=conviction,  # type: ignore[arg-type]
        legacy_stance=legacy_stance,  # type: ignore[arg-type]
    )
    horizon_raw = str(raw.get("time_horizon") or "unspecified").strip()
    time_horizon = horizon_raw if horizon_raw in VALID_HORIZONS else "unspecified"
    logic = str(raw.get("logic") or raw.get("view_summary") or "").strip()
    evidence = str(raw.get("evidence") or "").strip()

    if entity_type == "stock":
        identity = resolve_security_identity(
            raw_name=entity_code_or_name or entity_name,
            stock_name=entity_name,
            aliases=aliases,
        )
        if identity is None:
            return None
        entity_key = identity.security_key
        entity_name = identity.display_name
    else:
        entity_key = _normalize_entity_key(entity_name, default=entity_type)

    return ViewpointRecord(
        entity_type=entity_type,  # type: ignore[arg-type]
        entity_key=entity_key,
        entity_name=entity_name,
        entity_code_or_name=entity_code_or_name or entity_name,
        stance=stance,  # type: ignore[arg-type]
        direction=direction,  # type: ignore[arg-type]
        judgment_type=judgment_type,  # type: ignore[arg-type]
        conviction=conviction,  # type: ignore[arg-type]
        evidence_type=evidence_type,  # type: ignore[arg-type]
        logic=logic,
        evidence=evidence,
        time_horizon=time_horizon,  # type: ignore[arg-type]
        sort_order=order,
    )


def _normalize_viewpoint(
    viewpoint: ViewpointRecord,
    *,
    order: int,
    aliases: dict[str, SecurityIdentity],
) -> ViewpointRecord | None:
    if viewpoint.entity_type != "stock":
        return viewpoint.model_copy(update={"sort_order": order})

    raw_name = (viewpoint.entity_code_or_name or viewpoint.entity_name).strip()
    identity = resolve_security_identity(
        raw_name=raw_name,
        stock_name=viewpoint.entity_name,
        aliases=aliases,
    )
    if identity is None:
        return None

    return viewpoint.model_copy(
        update={
            "entity_key": identity.security_key,
            "entity_name": identity.display_name,
            "sort_order": order,
        }
    )


def _normalize_extract(
    extract: NoteExtractRecord,
    aliases: dict[str, SecurityIdentity],
) -> tuple[NoteExtractRecord, bool]:
    normalized_viewpoints: list[ViewpointRecord] = []
    changed = False

    for index, viewpoint in enumerate(extract.viewpoints):
        normalized = _normalize_viewpoint(viewpoint, order=len(normalized_viewpoints), aliases=aliases)
        if normalized is None:
            changed = True
            continue
        if normalized.model_dump(mode="json") != viewpoint.model_dump(mode="json"):
            changed = True
        normalized_viewpoints.append(normalized)

    if not changed:
        return extract, False

    return extract.model_copy(update={"viewpoints": normalized_viewpoints}), True


def _identity_score(identity: SecurityIdentity) -> tuple[int, int, int, int, int]:
    display = identity.display_name.strip()
    has_separator = int("/" in display or "\\" in display)
    is_ticker_only = int(bool(identity.ticker and display.upper() == identity.ticker.upper()))
    has_chinese = int(any("\u4e00" <= char <= "\u9fff" for char in display))
    has_market = int(bool(identity.market))
    return (
        1 - has_separator,
        has_market,
        has_chinese,
        1 - is_ticker_only,
        len(display),
    )


def _refresh_security_entities(
    *,
    store: InsightStore,
    extracts: dict[str, NoteExtractRecord],
    aliases: dict[str, SecurityIdentity],
) -> None:
    best_identities: dict[str, SecurityIdentity] = {}
    for extract in extracts.values():
        for viewpoint in extract.viewpoints:
            if viewpoint.entity_type != "stock":
                continue
            raw_name = (viewpoint.entity_code_or_name or viewpoint.entity_name).strip()
            identity = resolve_security_identity(
                raw_name=raw_name,
                stock_name=viewpoint.entity_name,
                aliases=aliases,
            )
            if identity is None:
                continue
            current = best_identities.get(identity.security_key)
            if current is None or _identity_score(identity) > _identity_score(current):
                best_identities[identity.security_key] = identity

    for identity in best_identities.values():
        store.ensure_security(identity)


def _needs_reanalysis(note: RawNoteRecord, existing: dict[str, NoteExtractRecord]) -> bool:
    current = existing.get(_note_key(note.platform, note.note_id))
    if current is None:
        return True
    if current.analysis_version != ANALYSIS_VERSION:
        return True
    if current.raw_response.get("analysis_version") != ANALYSIS_VERSION:
        return True
    return False


def _group_notes_by_account_and_date(
    notes: list[RawNoteRecord],
) -> dict[str, dict[str, list[RawNoteRecord]]]:
    grouped: dict[str, dict[str, list[RawNoteRecord]]] = {}
    for note in notes:
        grouped.setdefault(_account_key(note.platform, note.account_name), {}).setdefault(
            note_date_key(note.publish_time, note.fetched_at),
            [],
        ).append(note)
    for account_bucket in grouped.values():
        for items in account_bucket.values():
            items.sort(
                key=lambda item: (item.publish_time or "", item.fetched_at, item.note_id),
                reverse=True,
            )
    return grouped


def _group_extracts_by_account_and_date(
    extracts: dict[str, NoteExtractRecord],
) -> dict[str, dict[str, list[NoteExtractRecord]]]:
    grouped: dict[str, dict[str, list[NoteExtractRecord]]] = {}
    for extract in extracts.values():
        grouped.setdefault(_account_key(extract.platform, extract.account_name), {}).setdefault(
            extract.date,
            [],
        ).append(extract)
    for account_bucket in grouped.values():
        for items in account_bucket.values():
            items.sort(key=lambda item: (item.publish_time or "", item.note_id), reverse=True)
    return grouped


def _analyze_missing_notes(
    *,
    store: InsightStore,
    notes: list[RawNoteRecord],
    paths: AppPaths,
    force: bool = False,
) -> tuple[dict[str, NoteExtractRecord], list[NoteExtractRecord], list[str]]:
    aliases = load_security_aliases(paths)
    existing = store.get_analysis_map()
    missing = notes if force else [note for note in notes if _needs_reanalysis(note, existing)]
    created: list[NoteExtractRecord] = []
    errors: list[str] = []
    if not missing:
        return existing, created, errors

    settings = load_settings()
    if not settings.api_key:
        errors.append("Missing AI API key. Skipping note extract generation.")
        return existing, created, errors

    client = LLMJsonClient(settings)
    for note in missing:
        try:
            result = client.generate_json(
                build_note_extract_messages(note),
                required_keys=NOTE_EXTRACT_REQUIRED_KEYS,
                max_tokens=4000,
            )
            payload = dict(result.parsed)
            viewpoints = []
            for index, raw_view in enumerate(_coerce_viewpoint_payloads(payload)):
                parsed = _parse_viewpoint(raw_view, order=index, aliases=aliases)
                if parsed is not None:
                    viewpoints.append(parsed)
            summary_text = str(payload.get("summary_text") or "").strip() or _fallback_note_summary(note)
            raw_response = dict(payload)
            raw_response["analysis_version"] = ANALYSIS_VERSION
            extract = NoteExtractRecord(
                platform=note.platform,
                note_id=note.note_id,
                account_name=note.account_name,
                profile_url=note.profile_url,
                note_url=note.url,
                note_title=note.title,
                note_desc=note.desc,
                author_id=note.author_id,
                author_nickname=note.author_nickname,
                publish_time=note.publish_time,
                date=note_date_key(note.publish_time, note.fetched_at),
                extracted_at=now_iso(),
                analysis_version=ANALYSIS_VERSION,
                summary_text=summary_text,
                key_points=_dedupe_preserve(
                    [str(item).strip() for item in (payload.get("key_points") or []) if str(item).strip()]
                )[:5],
                viewpoints=viewpoints,
                model_name=result.model_name,
                request_id=result.request_id,
                usage=result.usage,
                raw_response=raw_response,
            )
            extract, _ = _normalize_extract(extract, aliases)
            store.replace_content_analysis(extract, aliases=aliases)
            existing[_note_key(extract.platform, extract.note_id)] = extract
            created.append(extract)
        except Exception as exc:
            errors.append(f"[note {note.platform}/{note.note_id}] {exc}")
    refreshed = store.get_analysis_map()
    return refreshed, created, errors


def _aggregate_author_day_viewpoints(extracts: list[NoteExtractRecord]) -> list[AuthorDayViewpoint]:
    aggregated: dict[tuple[str, str], AuthorDayViewpoint] = {}
    for extract in extracts:
        for viewpoint in extract.viewpoints:
            key = (viewpoint.entity_type, viewpoint.entity_key)
            current = aggregated.get(key)
            if current is None:
                current = AuthorDayViewpoint(
                    entity_type=viewpoint.entity_type,
                    entity_key=viewpoint.entity_key,
                    entity_name=viewpoint.entity_name,
                    stance=viewpoint.stance,
                    direction=viewpoint.direction,
                    judgment_type=viewpoint.judgment_type,
                    conviction=viewpoint.conviction,
                    evidence_type=viewpoint.evidence_type,
                    logic=viewpoint.logic,
                    evidence=[],
                    note_ids=[],
                    note_urls=[],
                    time_horizons=[],
                )
                aggregated[key] = current
            else:
                current.stance = _combine_stances(current.stance, viewpoint.stance)
                current.direction = _combine_directions(current.direction, viewpoint.direction)
                current.judgment_type = _combine_judgment_types(
                    current.judgment_type,
                    viewpoint.judgment_type,
                )
                current.conviction = _combine_convictions(current.conviction, viewpoint.conviction)
                current.evidence_type = _combine_evidence_types(
                    current.evidence_type,
                    viewpoint.evidence_type,
                )
                current.logic = _merge_text(current.logic, viewpoint.logic)

            if viewpoint.evidence and viewpoint.evidence not in current.evidence:
                current.evidence.append(viewpoint.evidence)
            if extract.note_id not in current.note_ids:
                current.note_ids.append(extract.note_id)
            if extract.note_url and extract.note_url not in current.note_urls:
                current.note_urls.append(extract.note_url)
            if viewpoint.time_horizon not in current.time_horizons:
                current.time_horizons.append(viewpoint.time_horizon)

    return sorted(
        aggregated.values(),
        key=lambda item: (
            STANCE_PRIORITY.get(item.stance, -9),
            item.entity_type,
            item.entity_name,
        ),
        reverse=True,
    )


def _build_author_day_record(
    *,
    platform: str,
    account_name: str,
    profile_url: str,
    date: str,
    status: str,
    notes: list[RawNoteRecord],
    extracts: list[NoteExtractRecord],
    existing: AuthorDayRecord | None,
    crawl_error: str | None,
) -> AuthorDayRecord:
    day_viewpoints = _aggregate_author_day_viewpoints(extracts)
    mentioned_stocks = [item.entity_name for item in day_viewpoints if item.entity_type == "stock"]
    mentioned_themes = [item.entity_name for item in day_viewpoints if item.entity_type == "theme"]
    notes_payload = [
        AuthorTimelineNote(
            note_id=note.note_id,
            url=note.url,
            title=note.title,
            publish_time=note.publish_time,
        )
        for note in notes
    ]

    content_hash = _hash_payload(
        {
            "platform": platform,
            "account_name": account_name,
            "date": date,
            "status": status,
            "note_ids": [note.note_id for note in notes],
            "viewpoints": [item.model_dump(mode="json") for item in day_viewpoints],
            "crawl_error": crawl_error or "",
        }
    )

    if status == "no_update_today":
        summary_text = "当天无新内容。"
    elif status == "crawl_failed":
        summary_text = f"本次抓取失败：{crawl_error or 'unknown error'}"
    elif existing and existing.content_hash == content_hash and existing.summary_text.strip():
        summary_text = existing.summary_text
    else:
        summary_text = ""
        settings = load_settings()
        if settings.api_key and extracts:
            try:
                client = LLMJsonClient(settings)
                result = client.generate_json(
                    build_author_day_summary_messages(account_name, date, extracts),
                    required_keys=AUTHOR_SUMMARY_REQUIRED_KEYS,
                    max_tokens=2500,
                )
                summary_text = str(result.parsed.get("summary_text") or "").strip()
            except Exception:
                summary_text = ""
        if not summary_text:
            summary_text = _fallback_author_summary(account_name, notes, day_viewpoints)

    author_id = next((note.author_id for note in notes if note.author_id), "")
    author_nickname = next((note.author_nickname for note in notes if note.author_nickname), "")
    if not author_id and existing:
        author_id = existing.author_id
    if not author_nickname and existing:
        author_nickname = existing.author_nickname

    return AuthorDayRecord(
        platform=platform,
        date=date,
        account_name=account_name,
        profile_url=profile_url,
        author_id=author_id,
        author_nickname=author_nickname,
        status=status,  # type: ignore[arg-type]
        note_count_today=len(notes),
        summary_text=summary_text,
        note_ids=[note.note_id for note in notes],
        notes=notes_payload,
        viewpoints=day_viewpoints,
        mentioned_stocks=mentioned_stocks,
        mentioned_themes=mentioned_themes,
        content_hash=content_hash,
        updated_at=now_iso(),
    )


def _materialize_author_timelines(
    *,
    store: InsightStore,
    notes: list[RawNoteRecord],
    extracts: dict[str, NoteExtractRecord],
    crawl_results: list[CrawlAccountResult],
) -> tuple[list[AuthorDayRecord], list[str]]:
    errors: list[str] = []
    updated_records: list[AuthorDayRecord] = []
    notes_by_account_date = _group_notes_by_account_and_date(notes)
    extracts_by_account_date = _group_extracts_by_account_and_date(extracts)
    crawl_result_map = {
        _account_key(item.platform, item.account_name): item for item in crawl_results
    }
    today = today_date_key()

    for account_id, crawl_result in crawl_result_map.items():
        all_dates = set(notes_by_account_date.get(account_id, {}).keys())
        all_dates.add(today)
        for date in sorted(all_dates, reverse=True):
            day_notes = notes_by_account_date.get(account_id, {}).get(date, [])
            day_extracts = extracts_by_account_date.get(account_id, {}).get(date, [])
            existing = store.get_author_daily_summary(
                platform=crawl_result.platform,
                account_name=crawl_result.account_name,
                date_key=date,
            )

            if date == today and crawl_result.status == "failed":
                status = "crawl_failed"
                crawl_error = crawl_result.error
            elif day_notes:
                status = "has_update_today"
                crawl_error = None
            elif date == today:
                status = "no_update_today"
                crawl_error = None
            else:
                continue

            try:
                record = _build_author_day_record(
                    platform=crawl_result.platform,
                    account_name=crawl_result.account_name,
                    profile_url=crawl_result.profile_url,
                    date=date,
                    status=status,
                    notes=day_notes,
                    extracts=day_extracts,
                    existing=existing,
                    crawl_error=crawl_error,
                )
                store.upsert_author_daily_summary(record, error_text=crawl_error)
                if existing is None or existing.model_dump(mode="json") != record.model_dump(mode="json") or date == today:
                    updated_records.append(record)
            except Exception as exc:
                errors.append(f"[author {crawl_result.platform}/{crawl_result.account_name} {date}] {exc}")
    return updated_records, errors


def _materialize_stock_timelines(
    *,
    store: InsightStore,
    extracts: dict[str, NoteExtractRecord],
) -> list[StockDayRecord]:
    grouped: dict[str, dict[str, list[tuple[NoteExtractRecord, ViewpointRecord]]]] = {}
    display_names: dict[str, str] = {}
    for extract in extracts.values():
        for viewpoint in extract.viewpoints:
            if viewpoint.entity_type != "stock":
                continue
            display_names[viewpoint.entity_key] = viewpoint.entity_name
            grouped.setdefault(viewpoint.entity_key, {}).setdefault(extract.date, []).append(
                (extract, viewpoint)
            )

    store.clear_security_daily_views()
    updated_records: list[StockDayRecord] = []
    for security_key, date_map in grouped.items():
        for date, items in date_map.items():
            author_map: dict[str, EntityAuthorView] = {}
            for extract, viewpoint in items:
                author_key = _account_key(extract.platform, extract.account_name)
                view = author_map.setdefault(
                    author_key,
                    EntityAuthorView(
                        platform=extract.platform,
                        account_name=extract.account_name,
                        author_nickname=extract.author_nickname,
                        stance=viewpoint.stance,
                        direction=viewpoint.direction,
                        judgment_type=viewpoint.judgment_type,
                        conviction=viewpoint.conviction,
                        evidence_type=viewpoint.evidence_type,
                        logic="",
                        note_ids=[],
                        note_urls=[],
                        evidence=[],
                        time_horizons=[],
                    ),
                )
                view.stance = _combine_stances(view.stance, viewpoint.stance)
                view.direction = _combine_directions(view.direction, viewpoint.direction)
                view.judgment_type = _combine_judgment_types(
                    view.judgment_type,
                    viewpoint.judgment_type,
                )
                view.conviction = _combine_convictions(view.conviction, viewpoint.conviction)
                view.evidence_type = _combine_evidence_types(
                    view.evidence_type,
                    viewpoint.evidence_type,
                )
                view.logic = _merge_text(view.logic, viewpoint.logic)
                if viewpoint.evidence and viewpoint.evidence not in view.evidence:
                    view.evidence.append(viewpoint.evidence)
                if viewpoint.time_horizon not in view.time_horizons:
                    view.time_horizons.append(viewpoint.time_horizon)
                if extract.note_id not in view.note_ids:
                    view.note_ids.append(extract.note_id)
                if extract.note_url not in view.note_urls:
                    view.note_urls.append(extract.note_url)

            author_views = sorted(
                author_map.values(),
                key=lambda item: (item.platform, item.account_name),
            )
            record = StockDayRecord(
                date=date,
                stock_code_or_name=security_key,
                stock_name=display_names.get(security_key) or security_key,
                mention_count=len(items),
                author_views=author_views,
                content_hash=_hash_payload(
                    {
                        "security_key": security_key,
                        "date": date,
                        "author_views": [item.model_dump(mode="json") for item in author_views],
                    }
                ),
                updated_at=now_iso(),
            )
            store.upsert_security_daily_view(security_key, record)
            updated_records.append(record)
    return updated_records


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _refresh_stock_market_data(
    *,
    store: Any,
    stock_records: list[StockDayRecord],
) -> tuple[int, list[str]]:
    if not stock_records:
        return 0, []
    if not hasattr(store, "get_security_identities") or not hasattr(store, "upsert_security_daily_prices"):
        return 0, []

    max_securities = max(0, _env_int("PUBLIC_WORKER_MARKET_DATA_MAX_SECURITIES", 30))
    if max_securities <= 0:
        return 0, []
    days = max(30, _env_int("PUBLIC_WORKER_MARKET_DATA_DAYS", 730))
    delay_seconds = max(0.0, _env_float("PUBLIC_WORKER_MARKET_DATA_DELAY_SECONDS", 0.25))

    ordered_keys = list(dict.fromkeys(record.stock_code_or_name for record in stock_records if record.stock_code_or_name))
    identities = store.get_security_identities(ordered_keys)
    fetched_at = now_iso()
    cutoff_date = (date_class.today() - timedelta(days=days + 14)).isoformat()
    written_candles = 0
    errors: list[str] = []

    for index, security_key in enumerate(ordered_keys[:max_securities]):
        identity = identities.get(
            security_key,
            SecurityIdentity(security_key=security_key, display_name=security_key),
        )
        try:
            payload = fetch_security_daily(
                ticker=identity.ticker,
                market=identity.market,
                security_key=identity.security_key,
                days=days,
            )
            candles = payload.get("candles") or []
            if not candles:
                message = str(payload.get("message") or "Market data returned no daily candles.")
                errors.append(f"[market {security_key}] {message}")
                continue

            written_candles += store.upsert_security_daily_prices(
                security_key=security_key,
                source=str(payload.get("sourceLabel") or "Unknown"),
                source_symbol=str(payload.get("sourceSymbol") or identity.ticker or security_key),
                candles=candles,
                fetched_at=fetched_at,
            )
            if hasattr(store, "prune_security_daily_prices"):
                store.prune_security_daily_prices(security_key=security_key, before_date=cutoff_date)
        except Exception as exc:
            errors.append(f"[market {security_key}] {exc}")

        if delay_seconds > 0 and index < min(len(ordered_keys), max_securities) - 1:
            time.sleep(delay_seconds)

    return written_candles, errors


def _materialize_theme_timelines(
    *,
    store: InsightStore,
    extracts: dict[str, NoteExtractRecord],
) -> list[ThemeDayRecord]:
    grouped: dict[str, dict[str, list[tuple[NoteExtractRecord, ViewpointRecord]]]] = {}
    display_names: dict[str, str] = {}
    for extract in extracts.values():
        for viewpoint in extract.viewpoints:
            if viewpoint.entity_type != "theme":
                continue
            display_names[viewpoint.entity_key] = viewpoint.entity_name
            grouped.setdefault(viewpoint.entity_key, {}).setdefault(extract.date, []).append(
                (extract, viewpoint)
            )

    store.clear_theme_daily_views()
    updated_records: list[ThemeDayRecord] = []
    for theme_key, date_map in grouped.items():
        for date, items in date_map.items():
            author_map: dict[str, EntityAuthorView] = {}
            for extract, viewpoint in items:
                author_key = _account_key(extract.platform, extract.account_name)
                view = author_map.setdefault(
                    author_key,
                    EntityAuthorView(
                        platform=extract.platform,
                        account_name=extract.account_name,
                        author_nickname=extract.author_nickname,
                        stance=viewpoint.stance,
                        direction=viewpoint.direction,
                        judgment_type=viewpoint.judgment_type,
                        conviction=viewpoint.conviction,
                        evidence_type=viewpoint.evidence_type,
                        logic="",
                        note_ids=[],
                        note_urls=[],
                        evidence=[],
                        time_horizons=[],
                    ),
                )
                view.stance = _combine_stances(view.stance, viewpoint.stance)
                view.direction = _combine_directions(view.direction, viewpoint.direction)
                view.judgment_type = _combine_judgment_types(
                    view.judgment_type,
                    viewpoint.judgment_type,
                )
                view.conviction = _combine_convictions(view.conviction, viewpoint.conviction)
                view.evidence_type = _combine_evidence_types(
                    view.evidence_type,
                    viewpoint.evidence_type,
                )
                view.logic = _merge_text(view.logic, viewpoint.logic)
                if viewpoint.evidence and viewpoint.evidence not in view.evidence:
                    view.evidence.append(viewpoint.evidence)
                if viewpoint.time_horizon not in view.time_horizons:
                    view.time_horizons.append(viewpoint.time_horizon)
                if extract.note_id not in view.note_ids:
                    view.note_ids.append(extract.note_id)
                if extract.note_url not in view.note_urls:
                    view.note_urls.append(extract.note_url)

            author_views = sorted(
                author_map.values(),
                key=lambda item: (item.platform, item.account_name),
            )
            record = ThemeDayRecord(
                date=date,
                theme_key=theme_key,
                theme_name=display_names.get(theme_key) or theme_key,
                mention_count=len(items),
                author_views=author_views,
                content_hash=_hash_payload(
                    {
                        "theme_key": theme_key,
                        "date": date,
                        "author_views": [item.model_dump(mode="json") for item in author_views],
                    }
                ),
                updated_at=now_iso(),
            )
            store.upsert_theme_daily_view(theme_key, record)
            updated_records.append(record)
    return updated_records


def _build_synthetic_crawl_results(notes: list[RawNoteRecord]) -> list[CrawlAccountResult]:
    account_map: dict[tuple[str, str], CrawlAccountResult] = {}
    run_at = now_iso()
    for note in notes:
        key = (note.platform, note.account_name)
        if key in account_map:
            continue
        account_map[key] = CrawlAccountResult(
            platform=note.platform,
            account_name=note.account_name,
            profile_url=note.profile_url,
            run_at=run_at,
            status="success",
            candidate_count=0,
            new_note_count=0,
            fetched_note_ids=[],
            error=None,
        )
    return sorted(account_map.values(), key=lambda item: (item.platform, item.account_name))


def normalize_existing_analysis(paths: AppPaths) -> tuple[AnalysisRunSummary, int]:
    aliases = load_security_aliases(paths)
    normalized_count = 0

    with sqlite_connection(paths) as conn:
        init_db(conn)
        store = InsightStore(conn)
        extracts = store.get_analysis_map()
        for extract in extracts.values():
            normalized_extract, changed = _normalize_extract(extract, aliases)
            if not changed:
                continue
            store.replace_content_analysis(normalized_extract, aliases=aliases)
            normalized_count += 1

    with sqlite_connection(paths) as conn:
        init_db(conn)
        store = InsightStore(conn)
        notes = store.list_all_content_items()

    summary = run_analysis(
        paths=paths,
        notes=notes,
        crawl_results=_build_synthetic_crawl_results(notes),
        crawl_errors=[],
    )
    return summary, normalized_count


def reanalyze_existing_content(paths: AppPaths) -> AnalysisRunSummary:
    with sqlite_connection(paths) as conn:
        init_db(conn)
        store = InsightStore(conn)
        notes = store.list_all_content_items()

    return run_analysis(
        paths=paths,
        notes=notes,
        crawl_results=_build_synthetic_crawl_results(notes),
        crawl_errors=[],
        force_reanalysis=True,
    )


def run_analysis(
    paths: AppPaths,
    notes: list[RawNoteRecord],
    crawl_results: list[CrawlAccountResult],
    crawl_errors: list[str],
    force_reanalysis: bool = False,
) -> AnalysisRunSummary:
    with sqlite_connection(paths) as conn:
        init_db(conn)
        store = InsightStore(conn)
        return run_analysis_with_store(
            store=store,
            paths=paths,
            notes=notes,
            crawl_results=crawl_results,
            crawl_errors=crawl_errors,
            force_reanalysis=force_reanalysis,
        )


def run_analysis_with_store(
    *,
    store: Any,
    paths: AppPaths,
    notes: list[RawNoteRecord],
    crawl_results: list[CrawlAccountResult],
    crawl_errors: list[str],
    force_reanalysis: bool = False,
) -> AnalysisRunSummary:
    run_at = now_iso()
    run_id = run_at.replace(":", "").replace("+08:00", "").replace("-", "")
    aliases = load_security_aliases(paths)

    extracts, created_extracts, extract_errors = _analyze_missing_notes(
        store=store,
        notes=notes,
        paths=paths,
        force=force_reanalysis,
    )
    _refresh_security_entities(store=store, extracts=extracts, aliases=aliases)
    author_records, author_errors = _materialize_author_timelines(
        store=store,
        notes=notes,
        extracts=extracts,
        crawl_results=crawl_results,
    )
    stock_records = _materialize_stock_timelines(
        store=store,
        extracts=extracts,
    )
    market_prices, market_errors = _refresh_stock_market_data(
        store=store,
        stock_records=stock_records,
    )
    theme_records = _materialize_theme_timelines(
        store=store,
        extracts=extracts,
    )
    store.prune_orphan_securities()

    snapshot = AnalysisSnapshot(
        run_id=run_id,
        run_at=run_at,
        processed_note_ids=[_note_key(note.platform, note.note_id) for note in notes],
        crawl_results=crawl_results,
        note_extracts=created_extracts,
        author_summaries=author_records,
        stock_views=stock_records,
        theme_views=theme_records,
        errors=[*crawl_errors, *extract_errors, *author_errors],
    )
    snapshot_path = paths.ai_snapshots_dir / f"{run_id}.json"
    write_json(snapshot_path, snapshot.model_dump(mode="json"))
    store.insert_analysis_run(
        run_id=run_id,
        run_at=run_at,
        processed_note_count=len(notes),
        error_count=len(snapshot.errors),
        errors=snapshot.errors,
        snapshot_path=str(snapshot_path),
        crawl_results=crawl_results,
    )

    exit_code = 0 if not snapshot.errors else 1
    return AnalysisRunSummary(
        exit_code=exit_code,
        snapshot=snapshot,
        market_prices=market_prices,
        market_errors=market_errors,
    )
