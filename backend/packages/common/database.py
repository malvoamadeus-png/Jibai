from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from .models import (
    AuthorDayRecord,
    CrawlAccountResult,
    NoteExtractRecord,
    RawNoteRecord,
    StockDayRecord,
    StockPriceCandle,
    ThemeDayRecord,
    ViewpointRecord,
)
from .paths import AppPaths
from .security_aliases import SecurityIdentity, resolve_security_identity


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


@contextmanager
def sqlite_connection(paths: AppPaths) -> Iterator[sqlite3.Connection]:
    paths.insight_db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(paths.insight_db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(row["name"]) == column for row in rows)


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    if not _column_exists(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS accounts (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          platform TEXT NOT NULL,
          account_name TEXT NOT NULL,
          author_id TEXT,
          author_nickname TEXT,
          profile_url TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(platform, account_name)
        );

        CREATE TABLE IF NOT EXISTS content_items (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          platform TEXT NOT NULL,
          account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
          external_content_id TEXT NOT NULL,
          url TEXT,
          title TEXT,
          body_text TEXT,
          content_type TEXT,
          publish_time TEXT,
          last_update_time TEXT,
          fetched_at TEXT,
          like_count INTEGER,
          collect_count INTEGER,
          comment_count INTEGER,
          share_count INTEGER,
          metadata_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(platform, external_content_id)
        );

        CREATE TABLE IF NOT EXISTS analysis_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          run_id TEXT NOT NULL UNIQUE,
          run_at TEXT NOT NULL,
          processed_note_count INTEGER NOT NULL DEFAULT 0,
          error_count INTEGER NOT NULL DEFAULT 0,
          errors_json TEXT NOT NULL DEFAULT '[]',
          snapshot_path TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS crawl_account_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          analysis_run_id INTEGER REFERENCES analysis_runs(id) ON DELETE CASCADE,
          platform TEXT NOT NULL,
          account_id INTEGER REFERENCES accounts(id) ON DELETE CASCADE,
          account_name TEXT NOT NULL,
          run_at TEXT NOT NULL,
          status TEXT NOT NULL,
          candidate_count INTEGER NOT NULL DEFAULT 0,
          new_note_count INTEGER NOT NULL DEFAULT 0,
          fetched_note_ids_json TEXT NOT NULL DEFAULT '[]',
          error_text TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS content_analyses (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          content_id INTEGER NOT NULL UNIQUE REFERENCES content_items(id) ON DELETE CASCADE,
          date_key TEXT NOT NULL,
          extracted_at TEXT NOT NULL,
          summary_text TEXT NOT NULL,
          key_points_json TEXT NOT NULL DEFAULT '[]',
          raw_response_json TEXT NOT NULL DEFAULT '{}',
          model_name TEXT,
          request_id TEXT,
          usage_json TEXT NOT NULL DEFAULT '{}',
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS security_entities (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          security_key TEXT NOT NULL UNIQUE,
          display_name TEXT NOT NULL,
          ticker TEXT,
          market TEXT,
          aliases_json TEXT NOT NULL DEFAULT '[]',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS theme_entities (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          theme_key TEXT NOT NULL UNIQUE,
          display_name TEXT NOT NULL,
          aliases_json TEXT NOT NULL DEFAULT '[]',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS security_mentions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          content_id INTEGER NOT NULL REFERENCES content_items(id) ON DELETE CASCADE,
          security_id INTEGER NOT NULL REFERENCES security_entities(id) ON DELETE CASCADE,
          raw_name TEXT NOT NULL,
          stock_name TEXT,
          stance TEXT NOT NULL,
          direction TEXT NOT NULL DEFAULT 'unknown',
          signal_type TEXT NOT NULL DEFAULT 'unknown',
          judgment_type TEXT NOT NULL DEFAULT 'unknown',
          conviction TEXT NOT NULL DEFAULT 'unknown',
          evidence_type TEXT NOT NULL DEFAULT 'unknown',
          view_summary TEXT NOT NULL DEFAULT '',
          evidence TEXT NOT NULL DEFAULT '',
          sort_order INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(content_id, security_id, raw_name, sort_order)
        );

        CREATE TABLE IF NOT EXISTS content_viewpoints (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          content_id INTEGER NOT NULL REFERENCES content_items(id) ON DELETE CASCADE,
          entity_type TEXT NOT NULL,
          entity_key TEXT NOT NULL,
          entity_name TEXT NOT NULL,
          entity_code_or_name TEXT,
          stance TEXT NOT NULL,
          direction TEXT NOT NULL DEFAULT 'unknown',
          signal_type TEXT NOT NULL DEFAULT 'unknown',
          judgment_type TEXT NOT NULL DEFAULT 'unknown',
          conviction TEXT NOT NULL DEFAULT 'unknown',
          evidence_type TEXT NOT NULL DEFAULT 'unknown',
          logic TEXT NOT NULL DEFAULT '',
          evidence TEXT NOT NULL DEFAULT '',
          time_horizon TEXT NOT NULL DEFAULT 'unspecified',
          sort_order INTEGER NOT NULL DEFAULT 0,
          security_id INTEGER REFERENCES security_entities(id) ON DELETE SET NULL,
          theme_id INTEGER REFERENCES theme_entities(id) ON DELETE SET NULL,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(content_id, entity_type, entity_key, sort_order)
        );

        CREATE TABLE IF NOT EXISTS author_daily_summaries (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
          date_key TEXT NOT NULL,
          status TEXT NOT NULL,
          note_count_today INTEGER NOT NULL DEFAULT 0,
          summary_text TEXT NOT NULL,
          note_ids_json TEXT NOT NULL DEFAULT '[]',
          notes_json TEXT NOT NULL DEFAULT '[]',
          mentioned_stocks_json TEXT NOT NULL DEFAULT '[]',
          content_hash TEXT NOT NULL DEFAULT '',
          error_text TEXT,
          updated_at TEXT NOT NULL,
          UNIQUE(account_id, date_key)
        );

        CREATE TABLE IF NOT EXISTS security_daily_views (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          security_id INTEGER NOT NULL REFERENCES security_entities(id) ON DELETE CASCADE,
          date_key TEXT NOT NULL,
          mention_count INTEGER NOT NULL DEFAULT 0,
          author_views_json TEXT NOT NULL DEFAULT '[]',
          content_hash TEXT NOT NULL DEFAULT '',
          updated_at TEXT NOT NULL,
          UNIQUE(security_id, date_key)
        );

        CREATE TABLE IF NOT EXISTS security_daily_prices (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          security_id INTEGER NOT NULL REFERENCES security_entities(id) ON DELETE CASCADE,
          date_key TEXT NOT NULL,
          open_price REAL NOT NULL,
          high_price REAL NOT NULL,
          low_price REAL NOT NULL,
          close_price REAL NOT NULL,
          volume REAL,
          source TEXT NOT NULL,
          source_symbol TEXT NOT NULL DEFAULT '',
          fetched_at TEXT NOT NULL,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(security_id, date_key)
        );

        CREATE TABLE IF NOT EXISTS theme_daily_views (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          theme_id INTEGER NOT NULL REFERENCES theme_entities(id) ON DELETE CASCADE,
          date_key TEXT NOT NULL,
          mention_count INTEGER NOT NULL DEFAULT 0,
          author_views_json TEXT NOT NULL DEFAULT '[]',
          content_hash TEXT NOT NULL DEFAULT '',
          updated_at TEXT NOT NULL,
          UNIQUE(theme_id, date_key)
        );

        CREATE INDEX IF NOT EXISTS idx_content_items_account_publish
          ON content_items(account_id, publish_time DESC);
        CREATE INDEX IF NOT EXISTS idx_author_daily_summaries_account_date
          ON author_daily_summaries(account_id, date_key DESC);
        CREATE INDEX IF NOT EXISTS idx_security_daily_views_security_date
          ON security_daily_views(security_id, date_key DESC);
        CREATE INDEX IF NOT EXISTS idx_security_daily_prices_security_date
          ON security_daily_prices(security_id, date_key DESC);
        CREATE INDEX IF NOT EXISTS idx_theme_daily_views_theme_date
          ON theme_daily_views(theme_id, date_key DESC);
        CREATE INDEX IF NOT EXISTS idx_security_mentions_security_content
          ON security_mentions(security_id, content_id);
        CREATE INDEX IF NOT EXISTS idx_content_viewpoints_content
          ON content_viewpoints(content_id, sort_order ASC);
        CREATE INDEX IF NOT EXISTS idx_content_viewpoints_entity
          ON content_viewpoints(entity_type, entity_key, content_id);
        """
    )
    _ensure_column(
        conn,
        "author_daily_summaries",
        "viewpoints_json",
        "viewpoints_json TEXT NOT NULL DEFAULT '[]'",
    )
    _ensure_column(
        conn,
        "author_daily_summaries",
        "mentioned_themes_json",
        "mentioned_themes_json TEXT NOT NULL DEFAULT '[]'",
    )
    for table in ("content_viewpoints", "security_mentions"):
        _ensure_column(conn, table, "direction", "direction TEXT NOT NULL DEFAULT 'unknown'")
        _ensure_column(conn, table, "signal_type", "signal_type TEXT NOT NULL DEFAULT 'unknown'")
        _ensure_column(conn, table, "judgment_type", "judgment_type TEXT NOT NULL DEFAULT 'unknown'")
        _ensure_column(conn, table, "conviction", "conviction TEXT NOT NULL DEFAULT 'unknown'")
        _ensure_column(conn, table, "evidence_type", "evidence_type TEXT NOT NULL DEFAULT 'unknown'")


@dataclass(slots=True)
class InsightStore:
    conn: sqlite3.Connection

    def upsert_account(
        self,
        *,
        platform: str,
        account_name: str,
        author_id: str = "",
        author_nickname: str = "",
        profile_url: str = "",
    ) -> int:
        self.conn.execute(
            """
            INSERT INTO accounts (
              platform, account_name, author_id, author_nickname, profile_url, updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(platform, account_name) DO UPDATE SET
              author_id = CASE
                WHEN excluded.author_id <> '' THEN excluded.author_id
                ELSE accounts.author_id
              END,
              author_nickname = CASE
                WHEN excluded.author_nickname <> '' THEN excluded.author_nickname
                ELSE accounts.author_nickname
              END,
              profile_url = CASE
                WHEN excluded.profile_url <> '' THEN excluded.profile_url
                ELSE accounts.profile_url
              END,
              updated_at = CURRENT_TIMESTAMP
            """,
            (platform, account_name, author_id, author_nickname, profile_url),
        )
        row = self.conn.execute(
            "SELECT id FROM accounts WHERE platform = ? AND account_name = ?",
            (platform, account_name),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Failed to upsert account: {account_name}")
        return int(row["id"])

    def get_account_row(self, *, platform: str, account_name: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM accounts WHERE platform = ? AND account_name = ?",
            (platform, account_name),
        ).fetchone()

    def upsert_content_item(self, note: RawNoteRecord) -> int:
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
        self.conn.execute(
            """
            INSERT INTO content_items (
              platform, account_id, external_content_id, url, title, body_text, content_type,
              publish_time, last_update_time, fetched_at, like_count, collect_count,
              comment_count, share_count, metadata_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(platform, external_content_id) DO UPDATE SET
              account_id = excluded.account_id,
              url = COALESCE(NULLIF(excluded.url, ''), content_items.url),
              title = COALESCE(NULLIF(excluded.title, ''), content_items.title),
              body_text = COALESCE(NULLIF(excluded.body_text, ''), content_items.body_text),
              content_type = COALESCE(NULLIF(excluded.content_type, ''), content_items.content_type),
              publish_time = COALESCE(excluded.publish_time, content_items.publish_time),
              last_update_time = COALESCE(excluded.last_update_time, content_items.last_update_time),
              fetched_at = COALESCE(excluded.fetched_at, content_items.fetched_at),
              like_count = COALESCE(excluded.like_count, content_items.like_count),
              collect_count = COALESCE(excluded.collect_count, content_items.collect_count),
              comment_count = COALESCE(excluded.comment_count, content_items.comment_count),
              share_count = COALESCE(excluded.share_count, content_items.share_count),
              metadata_json = excluded.metadata_json,
              updated_at = CURRENT_TIMESTAMP
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
                json_dumps(metadata),
            ),
        )
        row = self.conn.execute(
            "SELECT id FROM content_items WHERE platform = ? AND external_content_id = ?",
            (note.platform, note.note_id),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Failed to upsert content item: {note.note_id}")
        return int(row["id"])

    def list_all_content_items(self, *, platform: str | None = None) -> list[RawNoteRecord]:
        sql = """
            SELECT
              c.platform,
              a.account_name,
              a.profile_url,
              c.external_content_id AS note_id,
              c.url,
              COALESCE(c.title, '') AS title,
              COALESCE(c.body_text, '') AS desc,
              COALESCE(a.author_id, '') AS author_id,
              COALESCE(a.author_nickname, '') AS author_nickname,
              COALESCE(c.content_type, '') AS note_type,
              c.publish_time,
              c.last_update_time,
              c.like_count,
              c.collect_count,
              c.comment_count,
              c.share_count,
              COALESCE(c.fetched_at, '') AS fetched_at,
              COALESCE(c.metadata_json, '{}') AS metadata_json
            FROM content_items c
            JOIN accounts a ON a.id = c.account_id
        """
        params: list[Any] = []
        if platform:
            sql += " WHERE c.platform = ?"
            params.append(platform)
        sql += " ORDER BY COALESCE(c.publish_time, c.fetched_at) DESC, c.external_content_id DESC"
        rows = self.conn.execute(sql, params).fetchall()
        result: list[RawNoteRecord] = []
        for row in rows:
            payload = dict(row)
            payload["metadata"] = json_loads(payload.pop("metadata_json"), {})
            result.append(RawNoteRecord.model_validate(payload))
        return result

    def get_analysis_map(self, *, platform: str | None = None) -> dict[str, NoteExtractRecord]:
        sql = """
            SELECT
              c.id AS content_id,
              c.platform,
              c.external_content_id AS note_id,
              a.account_name,
              a.profile_url,
              c.url AS note_url,
              COALESCE(c.title, '') AS note_title,
              COALESCE(c.body_text, '') AS note_desc,
              COALESCE(a.author_id, '') AS author_id,
              COALESCE(a.author_nickname, '') AS author_nickname,
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
            JOIN accounts a ON a.id = c.account_id
        """
        params: list[Any] = []
        if platform:
            sql += " WHERE c.platform = ?"
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
                  signal_type,
                  judgment_type,
                  conviction,
                  evidence_type,
                  logic,
                  evidence,
                  time_horizon,
                  sort_order
                FROM content_viewpoints
                WHERE content_id = ?
                ORDER BY sort_order ASC, id ASC
                """,
                (row["content_id"],),
            ).fetchall()
            payload = json_loads(row["raw_response_json"], {})
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
                publish_time=row["publish_time"],
                date=str(row["date"]),
                extracted_at=str(row["extracted_at"]),
                analysis_version=str(payload.get("analysis_version") or "legacy"),
                summary_text=str(row["summary_text"] or ""),
                key_points=json_loads(row["key_points_json"], []),
                viewpoints=[ViewpointRecord.model_validate(dict(item)) for item in viewpoint_rows],
                model_name=row["model_name"],
                request_id=row["request_id"],
                usage=json_loads(row["usage_json"], {}),
                raw_response=payload,
            )
        return result

    def ensure_security(self, identity: SecurityIdentity, alias_name: str | None = None) -> int:
        row = self.conn.execute(
            "SELECT id, aliases_json FROM security_entities WHERE security_key = ?",
            (identity.security_key,),
        ).fetchone()
        aliases = [] if row is None else json_loads(row["aliases_json"], [])
        if alias_name:
            cleaned = alias_name.strip()
            if cleaned and cleaned not in aliases:
                aliases.append(cleaned)
        self.conn.execute(
            """
            INSERT INTO security_entities (
              security_key, display_name, ticker, market, aliases_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(security_key) DO UPDATE SET
              display_name = COALESCE(NULLIF(excluded.display_name, ''), security_entities.display_name),
              ticker = COALESCE(NULLIF(excluded.ticker, ''), security_entities.ticker),
              market = COALESCE(NULLIF(excluded.market, ''), security_entities.market),
              aliases_json = excluded.aliases_json,
              updated_at = CURRENT_TIMESTAMP
            """,
            (
                identity.security_key,
                identity.display_name,
                identity.ticker,
                identity.market,
                json_dumps(aliases),
            ),
        )
        row = self.conn.execute(
            "SELECT id FROM security_entities WHERE security_key = ?",
            (identity.security_key,),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Failed to upsert security: {identity.security_key}")
        return int(row["id"])

    def ensure_theme(self, theme_key: str, display_name: str, alias_name: str | None = None) -> int:
        row = self.conn.execute(
            "SELECT id, aliases_json FROM theme_entities WHERE theme_key = ?",
            (theme_key,),
        ).fetchone()
        aliases = [] if row is None else json_loads(row["aliases_json"], [])
        if alias_name:
            cleaned = alias_name.strip()
            if cleaned and cleaned not in aliases:
                aliases.append(cleaned)
        self.conn.execute(
            """
            INSERT INTO theme_entities (
              theme_key, display_name, aliases_json, updated_at
            )
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(theme_key) DO UPDATE SET
              display_name = COALESCE(NULLIF(excluded.display_name, ''), theme_entities.display_name),
              aliases_json = excluded.aliases_json,
              updated_at = CURRENT_TIMESTAMP
            """,
            (theme_key, display_name, json_dumps(aliases)),
        )
        row = self.conn.execute(
            "SELECT id FROM theme_entities WHERE theme_key = ?",
            (theme_key,),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Failed to upsert theme: {theme_key}")
        return int(row["id"])

    def replace_content_analysis(
        self,
        extract: NoteExtractRecord,
        aliases: dict[str, SecurityIdentity] | None = None,
    ) -> None:
        content_id_row = self.conn.execute(
            "SELECT id FROM content_items WHERE platform = ? AND external_content_id = ?",
            (extract.platform, extract.note_id),
        ).fetchone()
        if content_id_row is None:
            raise RuntimeError(f"Content item not found for analysis: {extract.note_id}")
        content_id = int(content_id_row["id"])
        self.conn.execute(
            """
            INSERT INTO content_analyses (
              content_id, date_key, extracted_at, summary_text, key_points_json,
              raw_response_json, model_name, request_id, usage_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(content_id) DO UPDATE SET
              date_key = excluded.date_key,
              extracted_at = excluded.extracted_at,
              summary_text = excluded.summary_text,
              key_points_json = excluded.key_points_json,
              raw_response_json = excluded.raw_response_json,
              model_name = excluded.model_name,
              request_id = excluded.request_id,
              usage_json = excluded.usage_json,
              updated_at = CURRENT_TIMESTAMP
            """,
            (
                content_id,
                extract.date,
                extract.extracted_at,
                extract.summary_text,
                json_dumps(extract.key_points),
                json_dumps(extract.raw_response),
                extract.model_name,
                extract.request_id,
                json_dumps(extract.usage),
            ),
        )
        self.conn.execute("DELETE FROM content_viewpoints WHERE content_id = ?", (content_id,))
        self.conn.execute("DELETE FROM security_mentions WHERE content_id = ?", (content_id,))
        alias_map = aliases or {}

        for index, viewpoint in enumerate(extract.viewpoints):
            if viewpoint.entity_type != "stock":
                continue
            if viewpoint.signal_type not in {"explicit_stance", "logic_based"}:
                continue
            if viewpoint.direction not in {"positive", "negative"}:
                continue
            if viewpoint.judgment_type in {"factual_only", "quoted", "mention_only"}:
                continue
            security_id: int | None = None
            theme_id: int | None = None
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
                security_id = self.ensure_security(
                    identity,
                    raw_name,
                )
                self.conn.execute(
                    """
                    INSERT INTO security_mentions (
                      content_id, security_id, raw_name, stock_name, stance,
                      direction, signal_type, judgment_type, conviction, evidence_type,
                      view_summary, evidence, sort_order, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(content_id, security_id, raw_name, sort_order) DO UPDATE SET
                      stock_name = excluded.stock_name,
                      stance = excluded.stance,
                      direction = excluded.direction,
                      signal_type = excluded.signal_type,
                      judgment_type = excluded.judgment_type,
                      conviction = excluded.conviction,
                      evidence_type = excluded.evidence_type,
                      view_summary = excluded.view_summary,
                      evidence = excluded.evidence,
                      updated_at = CURRENT_TIMESTAMP
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
            self.conn.execute(
                """
                INSERT INTO content_viewpoints (
                  content_id, entity_type, entity_key, entity_name, entity_code_or_name,
                  stance, direction, signal_type, judgment_type, conviction, evidence_type,
                  logic, evidence, time_horizon, sort_order, security_id, theme_id, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(content_id, entity_type, entity_key, sort_order) DO UPDATE SET
                  entity_name = excluded.entity_name,
                  entity_code_or_name = excluded.entity_code_or_name,
                  stance = excluded.stance,
                  direction = excluded.direction,
                  signal_type = excluded.signal_type,
                  judgment_type = excluded.judgment_type,
                  conviction = excluded.conviction,
                  evidence_type = excluded.evidence_type,
                  logic = excluded.logic,
                  evidence = excluded.evidence,
                  time_horizon = excluded.time_horizon,
                  security_id = excluded.security_id,
                  theme_id = excluded.theme_id,
                  updated_at = CURRENT_TIMESTAMP
                """,
                (
                    content_id,
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

    def clear_analysis_outputs(self) -> None:
        self.conn.execute("DELETE FROM author_daily_summaries")
        self.conn.execute("DELETE FROM security_daily_views")
        self.conn.execute("DELETE FROM theme_daily_views")
        self.conn.execute("DELETE FROM security_mentions")
        self.conn.execute("DELETE FROM content_viewpoints")
        self.conn.execute("DELETE FROM content_analyses")

    def get_author_daily_summary(
        self,
        *,
        platform: str,
        account_name: str,
        date_key: str,
    ) -> AuthorDayRecord | None:
        row = self.conn.execute(
            """
            SELECT
              a.platform,
              a.account_name,
              a.profile_url,
              COALESCE(a.author_id, '') AS author_id,
              COALESCE(a.author_nickname, '') AS author_nickname,
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
            JOIN accounts a ON a.id = ads.account_id
            WHERE a.platform = ? AND a.account_name = ? AND ads.date_key = ?
            """,
            (platform, account_name, date_key),
        ).fetchone()
        if row is None:
            return None
        payload = dict(row)
        payload["note_ids"] = json_loads(payload.pop("note_ids_json"), [])
        payload["notes"] = json_loads(payload.pop("notes_json"), [])
        payload["viewpoints"] = json_loads(payload.pop("viewpoints_json"), [])
        payload["mentioned_stocks"] = json_loads(payload.pop("mentioned_stocks_json"), [])
        payload["mentioned_themes"] = json_loads(payload.pop("mentioned_themes_json"), [])
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id, date_key) DO UPDATE SET
              status = excluded.status,
              note_count_today = excluded.note_count_today,
              summary_text = excluded.summary_text,
              note_ids_json = excluded.note_ids_json,
              notes_json = excluded.notes_json,
              viewpoints_json = excluded.viewpoints_json,
              mentioned_stocks_json = excluded.mentioned_stocks_json,
              mentioned_themes_json = excluded.mentioned_themes_json,
              content_hash = excluded.content_hash,
              error_text = excluded.error_text,
              updated_at = excluded.updated_at
            """,
            (
                account_id,
                record.date,
                record.status,
                record.note_count_today,
                record.summary_text,
                json_dumps(record.note_ids),
                json_dumps([item.model_dump(mode="json") for item in record.notes]),
                json_dumps([item.model_dump(mode="json") for item in record.viewpoints]),
                json_dumps(record.mentioned_stocks),
                json_dumps(record.mentioned_themes),
                record.content_hash,
                error_text,
                record.updated_at,
            ),
        )

    def clear_security_daily_views(self) -> None:
        self.conn.execute("DELETE FROM security_daily_views")

    def upsert_security_daily_view(self, security_key: str, record: StockDayRecord) -> None:
        row = self.conn.execute(
            "SELECT id FROM security_entities WHERE security_key = ?",
            (security_key,),
        ).fetchone()
        if row is None:
            security_id = self.ensure_security(
                SecurityIdentity(
                    security_key=security_key,
                    display_name=record.stock_name or security_key,
                )
            )
        else:
            security_id = int(row["id"])
        self.conn.execute(
            """
            INSERT INTO security_daily_views (
              security_id, date_key, mention_count, author_views_json, content_hash, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(security_id, date_key) DO UPDATE SET
              mention_count = excluded.mention_count,
              author_views_json = excluded.author_views_json,
              content_hash = excluded.content_hash,
              updated_at = excluded.updated_at
            """,
            (
                security_id,
                record.date,
                record.mention_count,
                json_dumps([item.model_dump(mode="json") for item in record.author_views]),
                record.content_hash,
                record.updated_at,
            ),
        )

    def get_security_identities(self, security_keys: list[str]) -> dict[str, SecurityIdentity]:
        cleaned_keys = [key for key in dict.fromkeys(security_keys) if key]
        if not cleaned_keys:
            return {}
        placeholders = ",".join("?" for _ in cleaned_keys)
        rows = self.conn.execute(
            f"""
            SELECT security_key, display_name, ticker, market
            FROM security_entities
            WHERE security_key IN ({placeholders})
            """,
            tuple(cleaned_keys),
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

    def upsert_security_daily_prices(
        self,
        *,
        security_key: str,
        source: str,
        source_symbol: str,
        candles: list[dict[str, Any] | StockPriceCandle],
        fetched_at: str,
    ) -> int:
        row = self.conn.execute(
            "SELECT id FROM security_entities WHERE security_key = ?",
            (security_key,),
        ).fetchone()
        if row is None:
            security_id = self.ensure_security(
                SecurityIdentity(security_key=security_key, display_name=security_key)
            )
        else:
            security_id = int(row["id"])

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
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(security_id, date_key) DO UPDATE SET
                  open_price = excluded.open_price,
                  high_price = excluded.high_price,
                  low_price = excluded.low_price,
                  close_price = excluded.close_price,
                  volume = excluded.volume,
                  source = excluded.source,
                  source_symbol = excluded.source_symbol,
                  fetched_at = excluded.fetched_at,
                  updated_at = CURRENT_TIMESTAMP
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
        row = self.conn.execute(
            "SELECT id FROM security_entities WHERE security_key = ?",
            (security_key,),
        ).fetchone()
        if row is None:
            return 0
        cursor = self.conn.execute(
            "DELETE FROM security_daily_prices WHERE security_id = ? AND date_key < ?",
            (row["id"], before_date),
        )
        return int(cursor.rowcount or 0)

    def clear_theme_daily_views(self) -> None:
        self.conn.execute("DELETE FROM theme_daily_views")

    def upsert_theme_daily_view(self, theme_key: str, record: ThemeDayRecord) -> None:
        theme_id = self.ensure_theme(theme_key, record.theme_name)
        self.conn.execute(
            """
            INSERT INTO theme_daily_views (
              theme_id, date_key, mention_count, author_views_json, content_hash, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(theme_id, date_key) DO UPDATE SET
              mention_count = excluded.mention_count,
              author_views_json = excluded.author_views_json,
              content_hash = excluded.content_hash,
              updated_at = excluded.updated_at
            """,
            (
                theme_id,
                record.date,
                record.mention_count,
                json_dumps([item.model_dump(mode="json") for item in record.author_views]),
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
        self.conn.execute(
            """
            INSERT INTO analysis_runs (
              run_id, run_at, processed_note_count, error_count, errors_json, snapshot_path
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
              run_at = excluded.run_at,
              processed_note_count = excluded.processed_note_count,
              error_count = excluded.error_count,
              errors_json = excluded.errors_json,
              snapshot_path = excluded.snapshot_path
            """,
            (
                run_id,
                run_at,
                processed_note_count,
                error_count,
                json_dumps(errors),
                snapshot_path,
            ),
        )
        run_row = self.conn.execute(
            "SELECT id FROM analysis_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if run_row is None:
            raise RuntimeError(f"Failed to persist analysis run: {run_id}")
        analysis_run_id = int(run_row["id"])
        self.conn.execute(
            "DELETE FROM crawl_account_runs WHERE analysis_run_id = ?",
            (analysis_run_id,),
        )
        for item in crawl_results:
            account_row = self.get_account_row(platform=item.platform, account_name=item.account_name)
            account_id = None if account_row is None else int(account_row["id"])
            self.conn.execute(
                """
                INSERT INTO crawl_account_runs (
                  analysis_run_id, platform, account_id, account_name, run_at, status,
                  candidate_count, new_note_count, fetched_note_ids_json, error_text
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    analysis_run_id,
                    item.platform,
                    account_id,
                    item.account_name,
                    item.run_at,
                    item.status,
                    item.candidate_count,
                    item.new_note_count,
                    json_dumps(item.fetched_note_ids),
                    item.error,
                ),
            )
