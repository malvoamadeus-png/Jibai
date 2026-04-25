from __future__ import annotations

from dataclasses import dataclass

from .database import InsightStore, init_db, sqlite_connection
from .io import read_json, read_jsonl
from .models import AuthorDayRecord, NoteExtractRecord, RawNoteRecord, StockDayRecord, ViewpointRecord
from .paths import AppPaths
from .security_aliases import load_security_aliases, resolve_security_identity


@dataclass(slots=True)
class MigrationSummary:
    migrated_notes: int
    migrated_extracts: int
    migrated_author_days: int
    migrated_stock_days: int


def _upsert_note(store: InsightStore, note: RawNoteRecord) -> None:
    store.upsert_content_item(note)


def migrate_legacy_json_to_sqlite(paths: AppPaths) -> MigrationSummary:
    aliases = load_security_aliases(paths)
    migrated_notes = 0
    migrated_extracts = 0
    migrated_author_days = 0
    migrated_stock_days = 0

    with sqlite_connection(paths) as conn:
        init_db(conn)
        store = InsightStore(conn)

        for note_path in paths.xhs_notes_dir.glob("*.jsonl"):
            for row in read_jsonl(note_path):
                note = RawNoteRecord.model_validate(row)
                _upsert_note(store, note)
                migrated_notes += 1

        for extract_path in paths.ai_note_extracts_dir.glob("*.json"):
            payload = read_json(extract_path, default=None)
            if not payload:
                continue
            extract = NoteExtractRecord.model_validate(payload)
            if not extract.viewpoints and isinstance(payload.get("stock_mentions"), list):
                viewpoints = []
                for index, raw in enumerate(payload.get("stock_mentions") or []):
                    if not isinstance(raw, dict):
                        continue
                    name = str(raw.get("stock_name") or raw.get("stock_code_or_name") or "").strip()
                    code = str(raw.get("stock_code_or_name") or raw.get("stock_name") or "").strip()
                    stance = str(raw.get("stance") or "unknown").strip()
                    if stance not in {
                        "strong_bullish",
                        "bullish",
                        "neutral",
                        "bearish",
                        "strong_bearish",
                        "mixed",
                        "mention_only",
                        "unknown",
                    }:
                        stance = "unknown"
                    if not name and not code:
                        continue
                    identity = resolve_security_identity(
                        raw_name=code or name,
                        stock_name=name or None,
                        aliases=aliases,
                    )
                    if identity is None:
                        continue
                    viewpoints.append(
                        ViewpointRecord(
                            entity_type="stock",
                            entity_key=identity.security_key,
                            entity_name=identity.display_name,
                            entity_code_or_name=code or name,
                            stance=stance,  # type: ignore[arg-type]
                            logic=str(raw.get("view_summary") or "").strip(),
                            evidence=str(raw.get("evidence") or "").strip(),
                            time_horizon="unspecified",
                            sort_order=index,
                        )
                    )
                extract.viewpoints = viewpoints
                extract.analysis_version = "legacy_migrated"
                raw_response = dict(extract.raw_response)
                raw_response["analysis_version"] = extract.analysis_version
                extract.raw_response = raw_response
            placeholder = RawNoteRecord(
                platform=extract.platform,
                account_name=extract.account_name,
                profile_url=extract.profile_url,
                note_id=extract.note_id,
                url=extract.note_url,
                title=extract.note_title,
                desc=extract.note_desc,
                author_id=extract.author_id,
                author_nickname=extract.author_nickname,
                publish_time=extract.publish_time,
                fetched_at=extract.extracted_at,
            )
            _upsert_note(store, placeholder)
            store.replace_content_analysis(extract, aliases=aliases)
            migrated_extracts += 1

        for timeline_path in paths.ai_author_timelines_dir.glob("*.json"):
            payload = read_json(timeline_path, default=None)
            if not payload:
                continue
            account_name = str(payload.get("account_name") or "")
            profile_url = str(payload.get("profile_url") or "")
            author_id = str(payload.get("author_id") or "")
            author_nickname = str(payload.get("author_nickname") or "")
            if account_name:
                store.upsert_account(
                    platform="xiaohongshu",
                    account_name=account_name,
                    author_id=author_id,
                    author_nickname=author_nickname,
                    profile_url=profile_url,
                )
            for raw_record in payload.get("records") or []:
                if not isinstance(raw_record, dict):
                    continue
                record = AuthorDayRecord.model_validate(raw_record)
                for note_item in record.notes:
                    placeholder = RawNoteRecord(
                        platform=record.platform,
                        account_name=record.account_name,
                        profile_url=record.profile_url,
                        note_id=note_item.note_id,
                        url=note_item.url,
                        title=note_item.title,
                        author_id=record.author_id,
                        author_nickname=record.author_nickname,
                        publish_time=note_item.publish_time,
                        fetched_at=record.updated_at,
                    )
                    _upsert_note(store, placeholder)
                store.upsert_author_daily_summary(record)
                migrated_author_days += 1

        for stock_path in paths.ai_stock_timelines_dir.glob("*.json"):
            payload = read_json(stock_path, default=None)
            if not payload:
                continue
            stock_key_raw = str(payload.get("stock_code_or_name") or "")
            stock_name = str(payload.get("stock_name") or "") or None
            identity = resolve_security_identity(stock_key_raw, stock_name, aliases)
            if identity is None:
                continue
            store.ensure_security(identity, stock_key_raw)
            for raw_record in payload.get("records") or []:
                if not isinstance(raw_record, dict):
                    continue
                record = StockDayRecord.model_validate(raw_record)
                store.upsert_security_daily_view(identity.security_key, record)
                migrated_stock_days += 1

    return MigrationSummary(
        migrated_notes=migrated_notes,
        migrated_extracts=migrated_extracts,
        migrated_author_days=migrated_author_days,
        migrated_stock_days=migrated_stock_days,
    )
