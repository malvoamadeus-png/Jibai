from __future__ import annotations

import os
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
    CrawlAccountResult,
    NoteExtractRecord,
    RawNoteRecord,
    StockDayRecord,
    ThemeDayRecord,
    ViewpointRecord,
)
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
        conn.rollback()
        raise
    finally:
        conn.close()


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
              COALESCE(c.fetched_at, '') AS fetched_at,
              COALESCE(c.metadata_json, '{}'::jsonb) AS metadata_json
            FROM content_items c
            JOIN x_accounts a ON a.id = c.account_id
        """
        params: list[Any] = []
        if platform:
            sql += " WHERE c.platform = %s"
            params.append(platform)
        sql += " ORDER BY COALESCE(c.publish_time, c.fetched_at) DESC, c.external_content_id DESC"
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

    def get_analysis_map(self, *, platform: str | None = None) -> dict[str, NoteExtractRecord]:
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
        params: list[Any] = []
        if platform:
            sql += " WHERE c.platform = %s"
            params.append(platform)
        rows = self.conn.execute(sql, params).fetchall()
        result: dict[str, NoteExtractRecord] = {}
        for row in rows:
            viewpoint_rows = self.conn.execute(
                """
                SELECT
                  entity_type,
                  entity_key,
                  entity_name,
                  entity_code_or_name,
                  stance,
                  direction,
                  judgment_type,
                  conviction,
                  evidence_type,
                  logic,
                  evidence,
                  time_horizon,
                  sort_order
                FROM content_viewpoints
                WHERE content_id = %s
                ORDER BY sort_order ASC, id ASC
                """,
                (row["content_id"],),
            ).fetchall()
            payload = row["raw_response_json"] or {}
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
                summary_text=str(row["summary_text"] or ""),
                key_points=row["key_points_json"] or [],
                viewpoints=[ViewpointRecord.model_validate(dict(item)) for item in viewpoint_rows],
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

    def replace_content_analysis(
        self,
        extract: NoteExtractRecord,
        aliases: dict[str, SecurityIdentity] | None = None,
    ) -> None:
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
              content_id, date_key, extracted_at, summary_text, key_points_json,
              raw_response_json, model_name, request_id, usage_json, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
            ON CONFLICT(content_id) DO UPDATE SET
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
        self.conn.execute("DELETE FROM content_viewpoints WHERE content_id = %s", (content_id,))
        self.conn.execute("DELETE FROM security_mentions WHERE content_id = %s", (content_id,))
        alias_map = aliases or {}

        for index, viewpoint in enumerate(extract.viewpoints):
            security_id: str | None = None
            theme_id: str | None = None
            raw_name = (viewpoint.entity_code_or_name or viewpoint.entity_name).strip()
            if viewpoint.entity_type == "stock":
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
                      direction, judgment_type, conviction, evidence_type,
                      view_summary, evidence, sort_order, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                    ON CONFLICT(content_id, security_id, raw_name, sort_order) DO UPDATE SET
                      stock_name = EXCLUDED.stock_name,
                      stance = EXCLUDED.stance,
                      direction = EXCLUDED.direction,
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
                        viewpoint.judgment_type,
                        viewpoint.conviction,
                        viewpoint.evidence_type,
                        viewpoint.logic,
                        viewpoint.evidence,
                        index,
                    ),
                )
            elif viewpoint.entity_type == "theme":
                theme_id = self.ensure_theme(viewpoint.entity_key, viewpoint.entity_name, raw_name)

            self.conn.execute(
                """
                INSERT INTO content_viewpoints (
                  content_id, entity_type, entity_key, entity_name, entity_code_or_name,
                  stance, direction, judgment_type, conviction, evidence_type,
                  logic, evidence, time_horizon, sort_order, security_id, theme_id, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT(content_id, entity_type, entity_key, sort_order) DO UPDATE SET
                  entity_name = EXCLUDED.entity_name,
                  entity_code_or_name = EXCLUDED.entity_code_or_name,
                  stance = EXCLUDED.stance,
                  direction = EXCLUDED.direction,
                  judgment_type = EXCLUDED.judgment_type,
                  conviction = EXCLUDED.conviction,
                  evidence_type = EXCLUDED.evidence_type,
                  logic = EXCLUDED.logic,
                  evidence = EXCLUDED.evidence,
                  time_horizon = EXCLUDED.time_horizon,
                  security_id = EXCLUDED.security_id,
                  theme_id = EXCLUDED.theme_id,
                  updated_at = now()
                """,
                (
                    content_id,
                    viewpoint.entity_type,
                    viewpoint.entity_key,
                    viewpoint.entity_name,
                    raw_name,
                    viewpoint.stance,
                    viewpoint.direction,
                    viewpoint.judgment_type,
                    viewpoint.conviction,
                    viewpoint.evidence_type,
                    viewpoint.logic,
                    viewpoint.evidence,
                    viewpoint.time_horizon,
                    index,
                    security_id,
                    theme_id,
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
              SELECT security_id FROM security_daily_views
            )
            """
        )
        return int(cursor.rowcount or 0)

    def get_author_daily_summary(
        self,
        *,
        platform: str,
        account_name: str,
        date_key: str,
    ) -> AuthorDayRecord | None:
        if platform != "x":
            return None
        row = self.conn.execute(
            """
            SELECT
              'x' AS platform,
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
              ads.content_hash,
              ads.updated_at
            FROM author_daily_summaries ads
            JOIN x_accounts a ON a.id = ads.account_id
            WHERE a.username = %s AND ads.date_key = %s
            """,
            (_normalize_username(account_name), date_key),
        ).fetchone()
        if row is None:
            return None
        payload = dict(row)
        payload["note_ids"] = payload.pop("note_ids_json") or []
        payload["notes"] = payload.pop("notes_json") or []
        payload["viewpoints"] = payload.pop("viewpoints_json") or []
        payload["mentioned_stocks"] = payload.pop("mentioned_stocks_json") or []
        payload["mentioned_themes"] = payload.pop("mentioned_themes_json") or []
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
              account_id, date_key, status, note_count_today, summary_text, note_ids_json,
              notes_json, viewpoints_json, mentioned_stocks_json, mentioned_themes_json,
              content_hash, error_text, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(account_id, date_key) DO UPDATE SET
              status = EXCLUDED.status,
              note_count_today = EXCLUDED.note_count_today,
              summary_text = EXCLUDED.summary_text,
              note_ids_json = EXCLUDED.note_ids_json,
              notes_json = EXCLUDED.notes_json,
              viewpoints_json = EXCLUDED.viewpoints_json,
              mentioned_stocks_json = EXCLUDED.mentioned_stocks_json,
              mentioned_themes_json = EXCLUDED.mentioned_themes_json,
              content_hash = EXCLUDED.content_hash,
              error_text = EXCLUDED.error_text,
              updated_at = EXCLUDED.updated_at
            """,
            (
                account_id,
                record.date,
                record.status,
                record.note_count_today,
                record.summary_text,
                _json(record.note_ids),
                _json([item.model_dump(mode="json") for item in record.notes]),
                _json([item.model_dump(mode="json") for item in record.viewpoints]),
                _json(record.mentioned_stocks),
                _json(record.mentioned_themes),
                record.content_hash,
                error_text,
                record.updated_at,
            ),
        )

    def clear_security_daily_views(self) -> None:
        self.conn.execute("DELETE FROM security_daily_views")

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
    ) -> None:
        row = self.conn.execute(
            """
            INSERT INTO crawl_runs (
              run_id, run_at, processed_note_count, error_count, errors_json, snapshot_path
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT(run_id) DO UPDATE SET
              run_at = EXCLUDED.run_at,
              processed_note_count = EXCLUDED.processed_note_count,
              error_count = EXCLUDED.error_count,
              errors_json = EXCLUDED.errors_json,
              snapshot_path = EXCLUDED.snapshot_path
            RETURNING id
            """,
            (
                run_id,
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
