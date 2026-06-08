from __future__ import annotations

import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator
from urllib.parse import urlparse

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .database import json_loads
from .models import (
    AuthorDayRecord,
    CryptoDayRecord,
    CryptoEntityIdentity,
    CrawlAccountResult,
    EventLinkedEntity,
    EventRecord,
    MarketTopRiskSnapshot,
    NewsTimelineDay,
    NoteExtractRecord,
    RawNoteRecord,
    StockDayRecord,
    StockPriceCandle,
    ThemeDayRecord,
    ViewpointRecord,
)
from .crypto_aliases import CryptoIdentity
from .security_aliases import SecurityIdentity, resolve_security_identity


def _database_url() -> str:
    value = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
    if not value:
        raise RuntimeError("Missing SUPABASE_DB_URL or DATABASE_URL for public worker.")
    return value


@contextmanager
def postgres_connection(dsn: str | None = None) -> Iterator[psycopg.Connection[dict[str, Any]]]:
    conn = psycopg.connect(dsn or _database_url(), row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            if not conn.closed:
                conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _normalize_username(value: str) -> str:
    raw = value.strip()
    if not raw:
        return raw
    if raw.startswith("@"):
        return raw[1:].lower()
    if "://" in raw:
        parsed = urlparse(raw)
        parts = [part for part in parsed.path.split("/") if part]
        if parts:
            return parts[0].lstrip("@").lower()
    return raw.lower()


def _json(value: Any) -> Jsonb:
    return Jsonb(value)


def _normalize_domain(value: str | None) -> str:
    return "crypto" if value == "crypto" else "stock"


_CRYPTO_SYMBOL_RE = re.compile(r"^\$?[A-Za-z][A-Za-z0-9_]{1,20}$")


def _crypto_symbol(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    if not _CRYPTO_SYMBOL_RE.fullmatch(cleaned):
        return None
    return cleaned.lstrip("$").upper()


def is_domain_pipeline_enabled(
    conn: psycopg.Connection[dict[str, Any]],
    domain: str = "stock",
) -> bool:
    safe_domain = _normalize_domain(domain)
    row = conn.execute(
        """
        SELECT public.is_domain_pipeline_enabled(%s) AS pipeline_enabled
        """,
        (safe_domain,),
    ).fetchone()
    return bool(row["pipeline_enabled"]) if row is not None else True


@dataclass(slots=True)
class PostgresInsightStore:
    conn: psycopg.Connection[dict[str, Any]]

    def upsert_account(
        self,
        *,
        platform: str,
        account_name: str,
        author_id: str = "",
        author_nickname: str = "",
        profile_url: str = "",
    ) -> str:
        if platform != "x":
            raise ValueError("Postgres public store only accepts X accounts.")
        username = _normalize_username(profile_url or account_name)
        display_name = author_nickname or account_name or username
        profile = profile_url or f"https://x.com/{username}"
        row = self.conn.execute(
            """
            INSERT INTO x_accounts (
              username, display_name, profile_url, x_user_id, status, updated_at
            )
            VALUES (%s, %s, %s, NULLIF(%s, ''), 'approved', now())
            ON CONFLICT (username) DO UPDATE SET
              display_name = COALESCE(NULLIF(EXCLUDED.display_name, ''), x_accounts.display_name),
              profile_url = COALESCE(NULLIF(EXCLUDED.profile_url, ''), x_accounts.profile_url),
              x_user_id = COALESCE(EXCLUDED.x_user_id, x_accounts.x_user_id),
              updated_at = now()
            RETURNING id
            """,
            (username, display_name, profile, author_id),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Failed to upsert account: {account_name}")
        return str(row["id"])

    def get_account_row(self, *, platform: str, account_name: str) -> dict[str, Any] | None:
        if platform != "x":
            return None
        return self.conn.execute(
            "SELECT * FROM x_accounts WHERE username = %s LIMIT 1",
            (_normalize_username(account_name),),
        ).fetchone()

    def upsert_content_item(self, note: RawNoteRecord) -> str:
        account_id = self.upsert_account(
            platform=note.platform,
            account_name=note.account_name,
            author_id=note.author_id,
            author_nickname=note.author_nickname,
            profile_url=note.profile_url,
        )
        metadata = {
            "profile_url": note.profile_url,
            "author_id": note.author_id,
            "author_nickname": note.author_nickname,
        }
        metadata.update(note.metadata)
        row = self.conn.execute(
            """
            INSERT INTO content_items (
              platform, account_id, external_content_id, url, title, body_text, content_type,
              publish_time, last_update_time, fetched_at, like_count, collect_count,
              comment_count, share_count, is_pinned, metadata_json, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
            ON CONFLICT(platform, external_content_id) DO UPDATE SET
              account_id = EXCLUDED.account_id,
              url = COALESCE(NULLIF(EXCLUDED.url, ''), content_items.url),
              title = COALESCE(NULLIF(EXCLUDED.title, ''), content_items.title),
              body_text = COALESCE(NULLIF(EXCLUDED.body_text, ''), content_items.body_text),
              content_type = COALESCE(NULLIF(EXCLUDED.content_type, ''), content_items.content_type),
              publish_time = COALESCE(EXCLUDED.publish_time, content_items.publish_time),
              last_update_time = COALESCE(EXCLUDED.last_update_time, content_items.last_update_time),
              fetched_at = COALESCE(EXCLUDED.fetched_at, content_items.fetched_at),
              like_count = COALESCE(EXCLUDED.like_count, content_items.like_count),
              collect_count = COALESCE(EXCLUDED.collect_count, content_items.collect_count),
              comment_count = COALESCE(EXCLUDED.comment_count, content_items.comment_count),
              share_count = COALESCE(EXCLUDED.share_count, content_items.share_count),
              is_pinned = EXCLUDED.is_pinned,
              metadata_json = EXCLUDED.metadata_json,
              updated_at = now()
            RETURNING id
            """,
            (
                note.platform,
                account_id,
                note.note_id,
                note.url,
                note.title,
                note.desc,
                note.note_type,
                note.publish_time,
                note.last_update_time,
                note.fetched_at,
                note.like_count,
                note.collect_count,
                note.comment_count,
                note.share_count,
                bool(note.metadata.get("is_pinned")),
                _json(metadata),
            ),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Failed to upsert content item: {note.note_id}")
        return str(row["id"])

    def list_all_content_items(self, *, platform: str | None = None) -> list[RawNoteRecord]:
        sql = """
            SELECT
              c.platform,
              a.username AS account_name,
              a.profile_url,
              c.external_content_id AS note_id,
              c.url,
              COALESCE(c.title, '') AS title,
              COALESCE(c.body_text, '') AS desc,
              COALESCE(a.x_user_id, '') AS author_id,
              COALESCE(a.display_name, '') AS author_nickname,
              COALESCE(c.content_type, '') AS note_type,
              c.publish_time,
              c.last_update_time,
              c.like_count,
              c.collect_count,
              c.comment_count,
              c.share_count,
              COALESCE(c.fetched_at, c.publish_time, c.created_at) AS fetched_at,
              COALESCE(c.metadata_json, '{}'::jsonb) AS metadata_json
            FROM content_items c
            JOIN x_accounts a ON a.id = c.account_id
        """
        params: list[Any] = []
        if platform:
            sql += " WHERE c.platform = %s"
            params.append(platform)
        sql += " ORDER BY COALESCE(c.publish_time, c.fetched_at, c.created_at) DESC, c.external_content_id DESC"
        rows = self.conn.execute(sql, params).fetchall()
        result: list[RawNoteRecord] = []
        for row in rows:
            payload = dict(row)
            metadata = payload.pop("metadata_json") or {}
            payload["metadata"] = metadata if isinstance(metadata, dict) else json_loads(str(metadata), {})
            for key in ("publish_time", "last_update_time", "fetched_at"):
                if payload.get(key) is not None:
                    payload[key] = str(payload[key])
            result.append(RawNoteRecord.model_validate(payload))
        return result

    def get_analysis_map(
        self,
        *,
        platform: str | None = None,
        analysis_domain: str = "stock",
    ) -> dict[str, NoteExtractRecord]:
        safe_domain = _normalize_domain(analysis_domain)
        sql = """
            SELECT
              c.id AS content_id,
              c.platform,
              c.external_content_id AS note_id,
              a.username AS account_name,
              a.profile_url,
              c.url AS note_url,
              COALESCE(c.title, '') AS note_title,
              COALESCE(c.body_text, '') AS note_desc,
              COALESCE(a.x_user_id, '') AS author_id,
              COALESCE(a.display_name, '') AS author_nickname,
              c.publish_time,
              ca.date_key AS date,
              ca.extracted_at,
              ca.analysis_domain,
              ca.summary_text,
              ca.key_points_json,
              ca.model_name,
              ca.request_id,
              ca.usage_json,
              ca.raw_response_json
            FROM content_analyses ca
            JOIN content_items c ON c.id = ca.content_id
            JOIN x_accounts a ON a.id = c.account_id
        """
        params: list[Any] = [safe_domain]
        sql += " WHERE ca.analysis_domain = %s"
        if platform:
            sql += " AND c.platform = %s"
            params.append(platform)
        rows = self.conn.execute(sql, params).fetchall()
        content_ids = [str(row["content_id"]) for row in rows]
        viewpoints_by_content_id: dict[str, list[dict[str, Any]]] = {}
        events_by_content_id: dict[str, list[EventRecord]] = {}
        if content_ids:
            viewpoint_rows = self.conn.execute(
                """
                SELECT
                  content_id,
                  entity_type,
                  entity_key,
                  entity_name,
                  entity_code_or_name,
                  stance,
                  direction,
                  signal_type,
                  judgment_type,
                  conviction,
                  evidence_type,
                  logic,
                  evidence,
                  time_horizon,
                  sort_order,
                  metadata_json,
                  COALESCE(metadata_json ->> 'entity_identifier_type', 'unknown') AS entity_identifier_type,
                  COALESCE(metadata_json -> 'raw_identifiers', '[]'::jsonb) AS raw_identifiers,
                  COALESCE(metadata_json ->> 'normalized_status', 'canonical') AS normalized_status,
                  COALESCE(metadata_json ->> 'source_signal_level', 'strong') AS source_signal_level
                FROM content_viewpoints
                WHERE analysis_domain = %s
                  AND content_id = ANY(%s)
                ORDER BY content_id ASC, sort_order ASC, id ASC
                """,
                (safe_domain, content_ids),
            ).fetchall()
            for item in viewpoint_rows:
                payload = dict(item)
                viewpoints_by_content_id.setdefault(str(payload["content_id"]), []).append(payload)
            event_rows = self.conn.execute(
                """
                SELECT
                  ce.id,
                  ce.content_id,
                  ce.headline,
                  ce.event_summary,
                  ce.event_type,
                  ce.event_nature,
                  ce.evidence,
                  ce.sort_order,
                  ce.metadata_json
                FROM content_events ce
                WHERE ce.analysis_domain = %s
                  AND ce.content_id = ANY(%s)
                ORDER BY ce.content_id ASC, ce.sort_order ASC, ce.id ASC
                """,
                (safe_domain, content_ids),
            ).fetchall()
            event_ids = [str(row["id"]) for row in event_rows]
            linked_by_event_id: dict[str, list[EventLinkedEntity]] = {}
            if event_ids:
                linked_rows = self.conn.execute(
                    """
                    SELECT
                      event_id,
                      entity_type,
                      entity_key,
                      entity_name,
                      entity_code_or_name,
                      metadata_json
                    FROM content_event_entities
                    WHERE event_id = ANY(%s)
                    ORDER BY event_id ASC, entity_type ASC, entity_key ASC, id ASC
                    """,
                    (event_ids,),
                ).fetchall()
                for item in linked_rows:
                    linked_by_event_id.setdefault(str(item["event_id"]), []).append(
                        EventLinkedEntity(
                            entity_type=str(item["entity_type"]),  # type: ignore[arg-type]
                            entity_key=str(item["entity_key"] or ""),
                            entity_name=str(item["entity_name"] or ""),
                            entity_code_or_name=str(item["entity_code_or_name"]).strip() if item["entity_code_or_name"] else None,
                            metadata=item.get("metadata_json") or {},
                        )
                    )
            for item in event_rows:
                event = EventRecord(
                    headline=str(item["headline"] or ""),
                    event_summary=str(item["event_summary"] or ""),
                    event_type=str(item["event_type"] or "other"),
                    event_nature=str(item["event_nature"] or "reported"),
                    evidence=str(item["evidence"] or ""),
                    sort_order=int(item["sort_order"] or 0),
                    linked_entities=linked_by_event_id.get(str(item["id"]), []),
                    metadata=item.get("metadata_json") or {},
                )
                events_by_content_id.setdefault(str(item["content_id"]), []).append(event)
        result: dict[str, NoteExtractRecord] = {}
        for row in rows:
            payload = row["raw_response_json"] or {}
            content_id = str(row["content_id"])
            result[f"{row['platform']}::{row['note_id']}"] = NoteExtractRecord(
                platform=str(row["platform"]),
                note_id=str(row["note_id"]),
                account_name=str(row["account_name"]),
                profile_url=str(row["profile_url"] or ""),
                note_url=str(row["note_url"] or ""),
                note_title=str(row["note_title"] or ""),
                note_desc=str(row["note_desc"] or ""),
                author_id=str(row["author_id"] or ""),
                author_nickname=str(row["author_nickname"] or ""),
                publish_time=None if row["publish_time"] is None else str(row["publish_time"]),
                date=str(row["date"]),
                extracted_at=str(row["extracted_at"]),
                analysis_version=str(payload.get("analysis_version") or "legacy"),
                analysis_domain=safe_domain,  # type: ignore[arg-type]
                summary_text=str(row["summary_text"] or ""),
                key_points=row["key_points_json"] or [],
                viewpoints=[
                    ViewpointRecord.model_validate(
                        {
                            **item,
                            "metadata": item.get("metadata_json") or {},
                        }
                    )
                    for item in viewpoints_by_content_id.get(content_id, [])
                ],
                events=events_by_content_id.get(content_id, []),
                model_name=row["model_name"],
                request_id=row["request_id"],
                usage=row["usage_json"] or {},
                raw_response=payload,
            )
        return result

    def ensure_security(self, identity: SecurityIdentity, alias_name: str | None = None) -> str:
        row = self.conn.execute(
            "SELECT id, aliases_json FROM security_entities WHERE security_key = %s",
            (identity.security_key,),
        ).fetchone()
        aliases = [] if row is None else list(row["aliases_json"] or [])
        if alias_name:
            cleaned = alias_name.strip()
            if cleaned and cleaned not in aliases:
                aliases.append(cleaned)
        row = self.conn.execute(
            """
            INSERT INTO security_entities (
              security_key, display_name, ticker, market, aliases_json, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, now())
            ON CONFLICT(security_key) DO UPDATE SET
              display_name = COALESCE(NULLIF(EXCLUDED.display_name, ''), security_entities.display_name),
              ticker = COALESCE(NULLIF(EXCLUDED.ticker, ''), security_entities.ticker),
              market = COALESCE(NULLIF(EXCLUDED.market, ''), security_entities.market),
              aliases_json = EXCLUDED.aliases_json,
              updated_at = now()
            RETURNING id
            """,
            (
                identity.security_key,
                identity.display_name,
                identity.ticker,
                identity.market,
                _json(aliases),
            ),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Failed to upsert security: {identity.security_key}")
        return str(row["id"])

    def ensure_theme(self, theme_key: str, display_name: str, alias_name: str | None = None) -> str:
        row = self.conn.execute(
            "SELECT id, aliases_json FROM theme_entities WHERE theme_key = %s",
            (theme_key,),
        ).fetchone()
        aliases = [] if row is None else list(row["aliases_json"] or [])
        if alias_name:
            cleaned = alias_name.strip()
            if cleaned and cleaned not in aliases:
                aliases.append(cleaned)
        row = self.conn.execute(
            """
            INSERT INTO theme_entities (
              theme_key, display_name, aliases_json, updated_at
            )
            VALUES (%s, %s, %s, now())
            ON CONFLICT(theme_key) DO UPDATE SET
              display_name = COALESCE(NULLIF(EXCLUDED.display_name, ''), theme_entities.display_name),
              aliases_json = EXCLUDED.aliases_json,
              updated_at = now()
            RETURNING id
            """,
            (theme_key, display_name, _json(aliases)),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Failed to upsert theme: {theme_key}")
        return str(row["id"])

    def ensure_crypto_entity(self, identity: CryptoIdentity | CryptoEntityIdentity, alias_name: str | None = None) -> str:
        row = self.conn.execute(
            "SELECT id, aliases_json, raw_identifiers_json, contract_addresses_json, x_accounts_json FROM crypto_entities WHERE asset_key = %s",
            (identity.asset_key,),
        ).fetchone()
        aliases = [] if row is None else list(row["aliases_json"] or [])
        raw_identifiers = [] if row is None else list(row["raw_identifiers_json"] or [])
        contract_addresses = [] if row is None else list(row["contract_addresses_json"] or [])
        x_accounts = [] if row is None else list(row["x_accounts_json"] or [])

        def extend_unique(target: list[str], values: Any) -> None:
            for raw in values or []:
                cleaned = str(raw).strip()
                if cleaned and cleaned not in target:
                    target.append(cleaned)

        if alias_name:
            extend_unique(aliases, [alias_name])
        extend_unique(raw_identifiers, getattr(identity, "raw_identifiers", []))
        extend_unique(contract_addresses, getattr(identity, "contract_addresses", []))
        extend_unique(x_accounts, getattr(identity, "x_accounts", []))
        extend_unique(aliases, getattr(identity, "aliases", []))

        row = self.conn.execute(
            """
            INSERT INTO crypto_entities (
              asset_key, display_name, symbol, identifier_type, raw_identifiers_json,
              contract_addresses_json, x_accounts_json, aliases_json, chain,
              normalized_status, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
            ON CONFLICT(asset_key) DO UPDATE SET
              display_name = COALESCE(NULLIF(EXCLUDED.display_name, ''), crypto_entities.display_name),
              symbol = COALESCE(NULLIF(EXCLUDED.symbol, ''), crypto_entities.symbol),
              identifier_type = CASE
                WHEN EXCLUDED.identifier_type IS NULL OR EXCLUDED.identifier_type IN ('', 'unknown')
                  THEN crypto_entities.identifier_type
                ELSE EXCLUDED.identifier_type
              END,
              raw_identifiers_json = EXCLUDED.raw_identifiers_json,
              contract_addresses_json = EXCLUDED.contract_addresses_json,
              x_accounts_json = EXCLUDED.x_accounts_json,
              aliases_json = EXCLUDED.aliases_json,
              chain = COALESCE(NULLIF(EXCLUDED.chain, ''), crypto_entities.chain),
              normalized_status = CASE
                WHEN crypto_entities.normalized_status = 'canonical' THEN crypto_entities.normalized_status
                ELSE EXCLUDED.normalized_status
              END,
              updated_at = now()
            RETURNING id
            """,
            (
                identity.asset_key,
                identity.display_name,
                identity.symbol,
                identity.identifier_type,
                _json(raw_identifiers),
                _json(contract_addresses),
                _json(x_accounts),
                _json(aliases),
                identity.chain,
                identity.normalized_status,
            ),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Failed to upsert crypto entity: {identity.asset_key}")
        return str(row["id"])

    def replace_content_analysis(
        self,
        extract: NoteExtractRecord,
        aliases: dict[str, SecurityIdentity] | None = None,
        crypto_aliases: dict[str, CryptoIdentity] | None = None,
        analysis_domain: str = "stock",
    ) -> None:
        safe_domain = _normalize_domain(analysis_domain)
        content_row = self.conn.execute(
            "SELECT id FROM content_items WHERE platform = %s AND external_content_id = %s",
            (extract.platform, extract.note_id),
        ).fetchone()
        if content_row is None:
            raise RuntimeError(f"Content item not found for analysis: {extract.note_id}")
        content_id = str(content_row["id"])
        self.conn.execute(
            """
            INSERT INTO content_analyses (
              content_id, analysis_domain, date_key, extracted_at, summary_text, key_points_json,
              raw_response_json, model_name, request_id, usage_json, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
            ON CONFLICT(content_id, analysis_domain) DO UPDATE SET
              date_key = EXCLUDED.date_key,
              extracted_at = EXCLUDED.extracted_at,
              summary_text = EXCLUDED.summary_text,
              key_points_json = EXCLUDED.key_points_json,
              raw_response_json = EXCLUDED.raw_response_json,
              model_name = EXCLUDED.model_name,
              request_id = EXCLUDED.request_id,
              usage_json = EXCLUDED.usage_json,
              updated_at = now()
            """,
            (
                content_id,
                safe_domain,
                extract.date,
                extract.extracted_at,
                extract.summary_text,
                _json(extract.key_points),
                _json(extract.raw_response),
                extract.model_name,
                extract.request_id,
                _json(extract.usage),
            ),
        )
        self.conn.execute(
            "DELETE FROM content_viewpoints WHERE content_id = %s AND analysis_domain = %s",
            (content_id, safe_domain),
        )
        event_rows = self.conn.execute(
            "SELECT id FROM content_events WHERE content_id = %s AND analysis_domain = %s",
            (content_id, safe_domain),
        ).fetchall()
        event_ids = [str(row["id"]) for row in event_rows]
        if event_ids:
            self.conn.execute(
                "DELETE FROM content_event_entities WHERE event_id = ANY(%s)",
                (event_ids,),
            )
        self.conn.execute(
            "DELETE FROM content_events WHERE content_id = %s AND analysis_domain = %s",
            (content_id, safe_domain),
        )
        if safe_domain == "stock":
            self.conn.execute("DELETE FROM security_mentions WHERE content_id = %s", (content_id,))
        alias_map = aliases or {}

        for index, viewpoint in enumerate(extract.viewpoints):
            if safe_domain == "stock" and viewpoint.entity_type != "stock":
                continue
            if safe_domain == "crypto" and viewpoint.entity_type != "crypto_entity":
                continue
            if safe_domain == "stock":
                if viewpoint.signal_type not in {"explicit_stance", "logic_based"}:
                    continue
                if viewpoint.direction not in {"positive", "negative"}:
                    continue
                if viewpoint.judgment_type in {"factual_only", "quoted", "mention_only"}:
                    continue
            security_id: str | None = None
            theme_id: str | None = None
            crypto_entity_id: str | None = None
            raw_name = (viewpoint.entity_code_or_name or viewpoint.entity_name).strip()
            if safe_domain == "stock" and viewpoint.entity_type == "stock":
                identity = resolve_security_identity(
                    raw_name=raw_name,
                    stock_name=viewpoint.entity_name,
                    aliases=alias_map,
                ) or SecurityIdentity(
                    security_key=viewpoint.entity_key,
                    display_name=viewpoint.entity_name,
                )
                security_id = self.ensure_security(identity, raw_name)
                self.conn.execute(
                    """
                    INSERT INTO security_mentions (
                      content_id, security_id, raw_name, stock_name, stance,
                      direction, signal_type, judgment_type, conviction, evidence_type,
                      view_summary, evidence, sort_order, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                    ON CONFLICT(content_id, security_id, raw_name, sort_order) DO UPDATE SET
                      stock_name = EXCLUDED.stock_name,
                      stance = EXCLUDED.stance,
                      direction = EXCLUDED.direction,
                      signal_type = EXCLUDED.signal_type,
                      judgment_type = EXCLUDED.judgment_type,
                      conviction = EXCLUDED.conviction,
                      evidence_type = EXCLUDED.evidence_type,
                      view_summary = EXCLUDED.view_summary,
                      evidence = EXCLUDED.evidence,
                      updated_at = now()
                    """,
                    (
                        content_id,
                        security_id,
                        raw_name,
                        viewpoint.entity_name,
                        viewpoint.stance,
                        viewpoint.direction,
                        viewpoint.signal_type,
                        viewpoint.judgment_type,
                        viewpoint.conviction,
                        viewpoint.evidence_type,
                        viewpoint.logic,
                        viewpoint.evidence,
                        index,
                    ),
                )
            elif safe_domain == "crypto":
                symbol = (
                    _crypto_symbol(viewpoint.entity_code_or_name)
                    if viewpoint.entity_identifier_type in {"symbol", "meme_ticker"}
                    else None
                )
                contract_addresses = tuple(
                    str(item).strip()
                    for item in (viewpoint.metadata.get("contract_addresses") or [])
                    if str(item).strip()
                )
                x_accounts = tuple(
                    str(item).strip()
                    for item in (viewpoint.metadata.get("x_accounts") or [])
                    if str(item).strip()
                )
                chain = str(viewpoint.metadata.get("chain") or "").strip() or None
                crypto_identity = CryptoIdentity(
                    asset_key=viewpoint.entity_key,
                    display_name=viewpoint.entity_name,
                    symbol=symbol,
                    identifier_type=viewpoint.entity_identifier_type,
                    raw_identifiers=tuple(viewpoint.raw_identifiers),
                    contract_addresses=contract_addresses,
                    x_accounts=x_accounts,
                    chain=chain,
                    normalized_status=viewpoint.normalized_status,
                )
                crypto_entity_id = self.ensure_crypto_entity(crypto_identity, raw_name)
            metadata = dict(viewpoint.metadata)
            metadata.update(
                {
                    "entity_identifier_type": viewpoint.entity_identifier_type,
                    "raw_identifiers": viewpoint.raw_identifiers,
                    "normalized_status": viewpoint.normalized_status,
                    "source_signal_level": viewpoint.source_signal_level,
                }
            )
            self.conn.execute(
                """
                INSERT INTO content_viewpoints (
                  content_id, analysis_domain, entity_type, entity_key, entity_name, entity_code_or_name,
                  stance, direction, signal_type, judgment_type, conviction, evidence_type,
                  logic, evidence, time_horizon, sort_order, security_id, theme_id, crypto_entity_id,
                  metadata_json, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT(content_id, analysis_domain, entity_type, entity_key, sort_order) DO UPDATE SET
                  entity_name = EXCLUDED.entity_name,
                  entity_code_or_name = EXCLUDED.entity_code_or_name,
                  stance = EXCLUDED.stance,
                  direction = EXCLUDED.direction,
                  signal_type = EXCLUDED.signal_type,
                  judgment_type = EXCLUDED.judgment_type,
                  conviction = EXCLUDED.conviction,
                  evidence_type = EXCLUDED.evidence_type,
                  logic = EXCLUDED.logic,
                  evidence = EXCLUDED.evidence,
                  time_horizon = EXCLUDED.time_horizon,
                  security_id = EXCLUDED.security_id,
                  theme_id = EXCLUDED.theme_id,
                  crypto_entity_id = EXCLUDED.crypto_entity_id,
                  metadata_json = EXCLUDED.metadata_json,
                  updated_at = now()
                """,
                (
                    content_id,
                    safe_domain,
                    viewpoint.entity_type,
                    viewpoint.entity_key,
                    viewpoint.entity_name,
                    raw_name,
                    viewpoint.stance,
                    viewpoint.direction,
                    viewpoint.signal_type,
                    viewpoint.judgment_type,
                    viewpoint.conviction,
                    viewpoint.evidence_type,
                    viewpoint.logic,
                    viewpoint.evidence,
                    viewpoint.time_horizon,
                    index,
                    security_id,
                    theme_id,
                    crypto_entity_id,
                    _json(metadata),
                ),
            )

        if safe_domain != "stock":
            return

        for event in extract.events:
            linked_entities = [item for item in event.linked_entities if item.entity_type in {"stock", "theme"}]
            if not linked_entities:
                continue
            event_row = self.conn.execute(
                """
                INSERT INTO content_events (
                  content_id, analysis_domain, headline, event_summary, event_type, event_nature,
                  evidence, publish_time, sort_order, metadata_json, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT(content_id, analysis_domain, sort_order) DO UPDATE SET
                  headline = EXCLUDED.headline,
                  event_summary = EXCLUDED.event_summary,
                  event_type = EXCLUDED.event_type,
                  event_nature = EXCLUDED.event_nature,
                  evidence = EXCLUDED.evidence,
                  publish_time = EXCLUDED.publish_time,
                  metadata_json = EXCLUDED.metadata_json,
                  updated_at = now()
                RETURNING id
                """,
                (
                    content_id,
                    safe_domain,
                    event.headline,
                    event.event_summary,
                    event.event_type,
                    event.event_nature,
                    event.evidence,
                    extract.publish_time,
                    event.sort_order,
                    _json(event.metadata),
                ),
            ).fetchone()
            if event_row is None:
                raise RuntimeError(f"Failed to upsert content event: {extract.note_id}:{event.sort_order}")
            event_id = str(event_row["id"])
            for linked in linked_entities:
                security_id: str | None = None
                theme_id: str | None = None
                raw_name = (linked.entity_code_or_name or linked.entity_name).strip()
                if linked.entity_type == "stock":
                    identity = resolve_security_identity(
                        raw_name=raw_name or linked.entity_name,
                        stock_name=linked.entity_name,
                        aliases=alias_map,
                    ) or SecurityIdentity(
                        security_key=linked.entity_key,
                        display_name=linked.entity_name,
                    )
                    security_id = self.ensure_security(identity, raw_name or linked.entity_name)
                else:
                    theme_id = self.ensure_theme(linked.entity_key, linked.entity_name, raw_name or linked.entity_name)
                self.conn.execute(
                    """
                    INSERT INTO content_event_entities (
                      event_id, entity_type, entity_key, entity_name, entity_code_or_name,
                      security_id, theme_id, metadata_json, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
                    ON CONFLICT(event_id, entity_type, entity_key) DO UPDATE SET
                      entity_name = EXCLUDED.entity_name,
                      entity_code_or_name = EXCLUDED.entity_code_or_name,
                      security_id = EXCLUDED.security_id,
                      theme_id = EXCLUDED.theme_id,
                      metadata_json = EXCLUDED.metadata_json,
                      updated_at = now()
                    """,
                    (
                        event_id,
                        linked.entity_type,
                        linked.entity_key,
                        linked.entity_name,
                        linked.entity_code_or_name,
                        security_id,
                        theme_id,
                        _json(linked.metadata),
                    ),
                )

    def prune_orphan_securities(self) -> int:
        cursor = self.conn.execute(
            """
            DELETE FROM security_entities
            WHERE id NOT IN (
              SELECT security_id FROM security_mentions
              UNION
              SELECT security_id FROM content_viewpoints WHERE security_id IS NOT NULL
              UNION
              SELECT security_id FROM content_event_entities WHERE security_id IS NOT NULL
              UNION
              SELECT security_id FROM security_daily_views
            )
            """
        )
        return int(cursor.rowcount or 0)

    def clear_analysis_outputs(self, analysis_domain: str = "stock") -> None:
        safe_domain = _normalize_domain(analysis_domain)
        event_rows = self.conn.execute(
            "SELECT id FROM content_events WHERE analysis_domain = %s",
            (safe_domain,),
        ).fetchall()
        event_ids = [str(row["id"]) for row in event_rows]
        if event_ids:
            self.conn.execute("DELETE FROM content_event_entities WHERE event_id = ANY(%s)", (event_ids,))
        self.conn.execute("DELETE FROM content_events WHERE analysis_domain = %s", (safe_domain,))
        self.conn.execute("DELETE FROM author_daily_summaries WHERE analysis_domain = %s", (safe_domain,))
        self.conn.execute("DELETE FROM content_viewpoints WHERE analysis_domain = %s", (safe_domain,))
        self.conn.execute("DELETE FROM content_analyses WHERE analysis_domain = %s", (safe_domain,))
        if safe_domain == "crypto":
            self.conn.execute("DELETE FROM crypto_entity_daily_views")
            return
        self.conn.execute("DELETE FROM stock_news_daily_timeline")
        self.conn.execute("DELETE FROM security_daily_views")
        self.conn.execute("DELETE FROM theme_daily_views")
        self.conn.execute("DELETE FROM security_mentions")

    def clear_content_analysis_for_notes(
        self,
        notes: list[RawNoteRecord],
        *,
        analysis_domain: str = "stock",
    ) -> int:
        safe_domain = _normalize_domain(analysis_domain)
        cleared = 0
        for note in notes:
            row = self.conn.execute(
                "SELECT id FROM content_items WHERE platform = %s AND external_content_id = %s",
                (note.platform, note.note_id),
            ).fetchone()
            if row is None:
                continue
            content_id = str(row["id"])
            event_rows = self.conn.execute(
                "SELECT id FROM content_events WHERE content_id = %s AND analysis_domain = %s",
                (content_id, safe_domain),
            ).fetchall()
            event_ids = [str(item["id"]) for item in event_rows]
            if event_ids:
                self.conn.execute(
                    "DELETE FROM content_event_entities WHERE event_id = ANY(%s)",
                    (event_ids,),
                )
            self.conn.execute(
                "DELETE FROM content_events WHERE content_id = %s AND analysis_domain = %s",
                (content_id, safe_domain),
            )
            self.conn.execute(
                "DELETE FROM content_viewpoints WHERE content_id = %s AND analysis_domain = %s",
                (content_id, safe_domain),
            )
            if safe_domain == "stock":
                self.conn.execute("DELETE FROM security_mentions WHERE content_id = %s", (content_id,))
            deleted = self.conn.execute(
                "DELETE FROM content_analyses WHERE content_id = %s AND analysis_domain = %s",
                (content_id, safe_domain),
            )
            cleared += int(deleted.rowcount or 0)
        return cleared

    def get_author_daily_summary(
        self,
        *,
        platform: str,
        account_name: str,
        date_key: str,
        analysis_domain: str = "stock",
    ) -> AuthorDayRecord | None:
        if platform != "x":
            return None
        safe_domain = _normalize_domain(analysis_domain)
        row = self.conn.execute(
            """
            SELECT
              'x' AS platform,
              ads.analysis_domain,
              a.username AS account_name,
              a.profile_url,
              COALESCE(a.x_user_id, '') AS author_id,
              COALESCE(a.display_name, '') AS author_nickname,
              ads.date_key AS date,
              ads.status,
              ads.note_count_today,
              ads.summary_text,
              ads.note_ids_json,
              ads.notes_json,
              ads.viewpoints_json,
              ads.mentioned_stocks_json,
              ads.mentioned_themes_json,
              ads.mentioned_crypto_json,
              ads.content_hash,
              ads.updated_at
            FROM author_daily_summaries ads
            JOIN x_accounts a ON a.id = ads.account_id
            WHERE a.username = %s AND ads.date_key = %s AND ads.analysis_domain = %s
            """,
            (_normalize_username(account_name), date_key, safe_domain),
        ).fetchone()
        if row is None:
            return None
        payload = dict(row)
        payload["note_ids"] = payload.pop("note_ids_json") or []
        payload["notes"] = payload.pop("notes_json") or []
        payload["viewpoints"] = payload.pop("viewpoints_json") or []
        payload["mentioned_stocks"] = payload.pop("mentioned_stocks_json") or []
        payload["mentioned_themes"] = payload.pop("mentioned_themes_json") or []
        payload["mentioned_crypto"] = payload.pop("mentioned_crypto_json") or []
        payload["updated_at"] = str(payload["updated_at"])
        return AuthorDayRecord.model_validate(payload)

    def upsert_author_daily_summary(self, record: AuthorDayRecord, error_text: str | None = None) -> None:
        account_id = self.upsert_account(
            platform=record.platform,
            account_name=record.account_name,
            author_id=record.author_id,
            author_nickname=record.author_nickname,
            profile_url=record.profile_url,
        )
        self.conn.execute(
            """
            INSERT INTO author_daily_summaries (
              account_id, analysis_domain, date_key, status, note_count_today, summary_text, note_ids_json,
              notes_json, viewpoints_json, mentioned_stocks_json, mentioned_themes_json,
              mentioned_crypto_json, content_hash, error_text, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(account_id, date_key, analysis_domain) DO UPDATE SET
              status = EXCLUDED.status,
              note_count_today = EXCLUDED.note_count_today,
              summary_text = EXCLUDED.summary_text,
              note_ids_json = EXCLUDED.note_ids_json,
              notes_json = EXCLUDED.notes_json,
              viewpoints_json = EXCLUDED.viewpoints_json,
              mentioned_stocks_json = EXCLUDED.mentioned_stocks_json,
              mentioned_themes_json = EXCLUDED.mentioned_themes_json,
              mentioned_crypto_json = EXCLUDED.mentioned_crypto_json,
              content_hash = EXCLUDED.content_hash,
              error_text = EXCLUDED.error_text,
              updated_at = EXCLUDED.updated_at
            """,
            (
                account_id,
                record.analysis_domain,
                record.date,
                record.status,
                record.note_count_today,
                record.summary_text,
                _json(record.note_ids),
                _json([item.model_dump(mode="json") for item in record.notes]),
                _json([item.model_dump(mode="json") for item in record.viewpoints]),
                _json(record.mentioned_stocks),
                _json(record.mentioned_themes),
                _json(record.mentioned_crypto),
                record.content_hash,
                error_text,
                record.updated_at,
            ),
        )

    def clear_security_daily_views(self) -> None:
        self.conn.execute("DELETE FROM security_daily_views")

    def clear_stock_news_daily_timeline(self) -> None:
        self.conn.execute("DELETE FROM stock_news_daily_timeline")

    def clear_crypto_entity_daily_views(self) -> None:
        self.conn.execute("DELETE FROM crypto_entity_daily_views")

    def upsert_stock_news_day(self, record: NewsTimelineDay) -> None:
        self.conn.execute(
            """
            INSERT INTO stock_news_daily_timeline (
              date_key, event_count, events_json, content_hash, updated_at
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT(date_key) DO UPDATE SET
              event_count = EXCLUDED.event_count,
              events_json = EXCLUDED.events_json,
              content_hash = EXCLUDED.content_hash,
              updated_at = EXCLUDED.updated_at
            """,
            (
                record.date,
                record.event_count,
                _json([item.model_dump(mode="json") for item in record.events]),
                record.content_hash,
                record.updated_at,
            ),
        )

    def upsert_crypto_entity_daily_view(self, asset_key: str, record: CryptoDayRecord) -> None:
        identity = CryptoIdentity(
            asset_key=asset_key,
            display_name=record.display_name or asset_key,
            symbol=record.symbol,
            identifier_type="unknown",
            normalized_status="temporary",
        )
        crypto_entity_id = self.ensure_crypto_entity(identity)
        self.conn.execute(
            """
            INSERT INTO crypto_entity_daily_views (
              crypto_entity_id, date_key, mention_count, author_views_json, content_hash, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT(crypto_entity_id, date_key) DO UPDATE SET
              mention_count = EXCLUDED.mention_count,
              author_views_json = EXCLUDED.author_views_json,
              content_hash = EXCLUDED.content_hash,
              updated_at = EXCLUDED.updated_at
            """,
            (
                crypto_entity_id,
                record.date,
                record.mention_count,
                _json([item.model_dump(mode="json") for item in record.author_views]),
                record.content_hash,
                record.updated_at,
            ),
        )

    def upsert_security_daily_view(self, security_key: str, record: StockDayRecord) -> None:
        security_id = self.ensure_security(
            SecurityIdentity(
                security_key=security_key,
                display_name=record.stock_name or security_key,
            )
        )
        self.conn.execute(
            """
            INSERT INTO security_daily_views (
              security_id, date_key, mention_count, author_views_json, content_hash, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT(security_id, date_key) DO UPDATE SET
              mention_count = EXCLUDED.mention_count,
              author_views_json = EXCLUDED.author_views_json,
              content_hash = EXCLUDED.content_hash,
              updated_at = EXCLUDED.updated_at
            """,
            (
                security_id,
                record.date,
                record.mention_count,
                _json([item.model_dump(mode="json") for item in record.author_views]),
                record.content_hash,
                record.updated_at,
            ),
        )

    def get_security_identities(self, security_keys: list[str]) -> dict[str, SecurityIdentity]:
        cleaned_keys = [key for key in dict.fromkeys(security_keys) if key]
        if not cleaned_keys:
            return {}
        rows = self.conn.execute(
            """
            SELECT security_key, display_name, ticker, market
            FROM security_entities
            WHERE security_key = ANY(%s)
            """,
            (cleaned_keys,),
        ).fetchall()
        return {
            str(row["security_key"]): SecurityIdentity(
                security_key=str(row["security_key"]),
                display_name=str(row["display_name"] or row["security_key"]),
                ticker=str(row["ticker"]).strip() if row["ticker"] else None,
                market=str(row["market"]).strip() if row["market"] else None,
            )
            for row in rows
        }

    def list_recent_security_keys(self, *, limit: int = 30, query: str | None = None) -> list[str]:
        safe_limit = max(1, min(int(limit), 500))
        query_text = (query or "").strip().lower()
        params: list[Any] = []
        where_sql = ""
        if query_text:
            where_sql = """
            WHERE lower(se.security_key::text) LIKE %s
               OR lower(coalesce(se.display_name, '')) LIKE %s
               OR lower(coalesce(se.ticker, '')) LIKE %s
               OR lower(coalesce(se.market, '')) LIKE %s
               OR lower(coalesce(se.aliases_json::text, '')) LIKE %s
            """
            like_value = f"%{query_text}%"
            params.extend([like_value, like_value, like_value, like_value, like_value])
        params.append(safe_limit)
        rows = self.conn.execute(
            f"""
            SELECT se.security_key
            FROM security_entities se
            LEFT JOIN security_daily_views sdv ON sdv.security_id = se.id
            {where_sql}
            GROUP BY se.id, se.security_key
            ORDER BY max(sdv.date_key) DESC NULLS LAST,
                     coalesce(sum(sdv.mention_count), 0) DESC,
                     se.security_key ASC
            LIMIT %s
            """,
            tuple(params),
        ).fetchall()
        return [str(row["security_key"]) for row in rows]

    def upsert_security_daily_prices(
        self,
        *,
        security_key: str,
        source: str,
        source_symbol: str,
        candles: list[dict[str, Any] | StockPriceCandle],
        fetched_at: str,
    ) -> int:
        with self.conn.transaction():
            row = self.conn.execute(
                "SELECT id FROM security_entities WHERE security_key = %s",
                (security_key,),
            ).fetchone()
            if row is None:
                security_id = self.ensure_security(
                    SecurityIdentity(security_key=security_key, display_name=security_key)
                )
            else:
                security_id = str(row["id"])

            written = 0
            for raw_candle in candles:
                candle = (
                    raw_candle
                    if isinstance(raw_candle, StockPriceCandle)
                    else StockPriceCandle.model_validate(raw_candle)
                )
                self.conn.execute(
                    """
                    INSERT INTO security_daily_prices (
                      security_id, date_key, open_price, high_price, low_price,
                      close_price, volume, source, source_symbol, fetched_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                    ON CONFLICT(security_id, date_key) DO UPDATE SET
                      open_price = EXCLUDED.open_price,
                      high_price = EXCLUDED.high_price,
                      low_price = EXCLUDED.low_price,
                      close_price = EXCLUDED.close_price,
                      volume = EXCLUDED.volume,
                      source = EXCLUDED.source,
                      source_symbol = EXCLUDED.source_symbol,
                      fetched_at = EXCLUDED.fetched_at,
                      updated_at = now()
                    """,
                    (
                        security_id,
                        candle.date,
                        candle.open,
                        candle.high,
                        candle.low,
                        candle.close,
                        candle.volume,
                        source,
                        source_symbol,
                        fetched_at,
                    ),
                )
                written += 1
            return written

    def prune_security_daily_prices(self, *, security_key: str, before_date: str) -> int:
        with self.conn.transaction():
            row = self.conn.execute(
                "SELECT id FROM security_entities WHERE security_key = %s",
                (security_key,),
            ).fetchone()
            if row is None:
                return 0
            cursor = self.conn.execute(
                "DELETE FROM security_daily_prices WHERE security_id = %s AND date_key < %s",
                (row["id"], before_date),
            )
            return int(cursor.rowcount or 0)

    def upsert_market_top_risk_snapshot(self, snapshot: MarketTopRiskSnapshot) -> None:
        self.conn.execute(
            """
            INSERT INTO market_top_risk_snapshots (
              week, nasdaq100, ndx_dd_from_52w_high, breadth_weakness_score,
              breakage_score, risk_score, risk_level, warning_active,
              confirmation_active, signals_json, metrics_json, source_json,
              updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
            ON CONFLICT(week) DO UPDATE SET
              nasdaq100 = EXCLUDED.nasdaq100,
              ndx_dd_from_52w_high = EXCLUDED.ndx_dd_from_52w_high,
              breadth_weakness_score = EXCLUDED.breadth_weakness_score,
              breakage_score = EXCLUDED.breakage_score,
              risk_score = EXCLUDED.risk_score,
              risk_level = EXCLUDED.risk_level,
              warning_active = EXCLUDED.warning_active,
              confirmation_active = EXCLUDED.confirmation_active,
              signals_json = EXCLUDED.signals_json,
              metrics_json = EXCLUDED.metrics_json,
              source_json = EXCLUDED.source_json,
              updated_at = now()
            """,
            (
                snapshot.week,
                snapshot.nasdaq100,
                snapshot.ndx_dd_from_52w_high,
                snapshot.breadth_weakness_score,
                snapshot.breakage_score,
                snapshot.risk_score,
                snapshot.risk_level,
                snapshot.warning_active,
                snapshot.confirmation_active,
                _json(snapshot.signals),
                _json(snapshot.metrics),
                _json(snapshot.sources),
            ),
        )

    def clear_theme_daily_views(self) -> None:
        self.conn.execute("DELETE FROM theme_daily_views")

    def upsert_theme_daily_view(self, theme_key: str, record: ThemeDayRecord) -> None:
        theme_id = self.ensure_theme(theme_key, record.theme_name)
        self.conn.execute(
            """
            INSERT INTO theme_daily_views (
              theme_id, date_key, mention_count, author_views_json, content_hash, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT(theme_id, date_key) DO UPDATE SET
              mention_count = EXCLUDED.mention_count,
              author_views_json = EXCLUDED.author_views_json,
              content_hash = EXCLUDED.content_hash,
              updated_at = EXCLUDED.updated_at
            """,
            (
                theme_id,
                record.date,
                record.mention_count,
                _json([item.model_dump(mode="json") for item in record.author_views]),
                record.content_hash,
                record.updated_at,
            ),
        )

    def insert_analysis_run(
        self,
        *,
        run_id: str,
        run_at: str,
        processed_note_count: int,
        error_count: int,
        errors: list[str],
        snapshot_path: str,
        crawl_results: list[CrawlAccountResult],
        analysis_domain: str = "stock",
    ) -> None:
        safe_domain = _normalize_domain(analysis_domain)
        row = self.conn.execute(
            """
            INSERT INTO crawl_runs (
              run_id, analysis_domain, run_at, processed_note_count, error_count, errors_json, snapshot_path
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(run_id) DO UPDATE SET
              analysis_domain = EXCLUDED.analysis_domain,
              run_at = EXCLUDED.run_at,
              processed_note_count = EXCLUDED.processed_note_count,
              error_count = EXCLUDED.error_count,
              errors_json = EXCLUDED.errors_json,
              snapshot_path = EXCLUDED.snapshot_path
            RETURNING id
            """,
            (
                run_id,
                safe_domain,
                run_at,
                processed_note_count,
                error_count,
                _json(errors),
                snapshot_path,
            ),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Failed to persist analysis run: {run_id}")
        run_id_value = str(row["id"])
        self.conn.execute("DELETE FROM crawl_account_runs WHERE crawl_run_id = %s", (run_id_value,))
        for item in crawl_results:
            account_row = self.get_account_row(platform=item.platform, account_name=item.account_name)
            account_id = None if account_row is None else str(account_row["id"])
            self.conn.execute(
                """
                INSERT INTO crawl_account_runs (
                  crawl_run_id, platform, account_id, account_name, run_at, status,
                  candidate_count, new_note_count, fetched_note_ids_json, error_text
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    run_id_value,
                    item.platform,
                    account_id,
                    item.account_name,
                    item.run_at,
                    item.status,
                    item.candidate_count,
                    item.new_note_count,
                    _json(item.fetched_note_ids),
                    item.error,
                ),
            )
