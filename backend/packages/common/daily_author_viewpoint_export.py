from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from sqlite3 import Connection
from typing import Any, Literal

from .paths import AppPaths


@dataclass(frozen=True, slots=True)
class DailyAuthorViewpointRow:
    date: str
    author: str
    author_account: str
    target_name: str
    target_code: str
    long_short: str
    conviction: str
    logic: str


@dataclass(frozen=True, slots=True)
class DailyAuthorViewpointExportResult:
    date: str
    row_count: int
    output_path: Path


def _json_loads(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def _long_short_label(direction: str, stance: str) -> str:
    if direction == "positive" or stance in {"strong_bullish", "bullish"}:
        return "看多"
    if direction == "negative" or stance in {"strong_bearish", "bearish"}:
        return "看空"
    if direction == "mixed" or stance == "mixed":
        return "多空分歧"
    if direction == "neutral" or stance == "neutral":
        return "中性"
    return "未知"


def _conviction_label(value: str) -> str:
    return {
        "strong": "强",
        "medium": "中",
        "weak": "弱",
        "none": "无",
        "unknown": "未知",
    }.get(value, value or "未知")


def _display_author(author_nickname: str, account_name: str) -> str:
    nickname = author_nickname.strip()
    if nickname:
        return nickname
    return f"@{account_name}" if account_name else ""


def _security_code_map(conn: Connection) -> dict[str, str]:
    rows = conn.execute(
        """
        SELECT security_key, COALESCE(NULLIF(ticker, ''), security_key) AS target_code
        FROM security_entities
        """
    ).fetchall()
    return {
        str(row["security_key"] or ""): str(row["target_code"] or "")
        for row in rows
        if str(row["security_key"] or "")
    }


def _security_code_map_postgres(conn: Any) -> dict[str, str]:
    rows = conn.execute(
        """
        SELECT security_key, COALESCE(NULLIF(ticker, ''), security_key) AS target_code
        FROM security_entities
        """
    ).fetchall()
    return {
        str(row["security_key"] or ""): str(row["target_code"] or "")
        for row in rows
        if str(row["security_key"] or "")
    }


def _load_rows(
    conn: Connection,
    *,
    date_key: str,
    platform: str | None = None,
) -> list[DailyAuthorViewpointRow]:
    sql = """
        SELECT
          ads.date_key,
          a.platform,
          a.account_name,
          COALESCE(a.author_nickname, '') AS author_nickname,
          COALESCE(ads.viewpoints_json, '[]') AS viewpoints_json
        FROM author_daily_summaries ads
        JOIN accounts a ON a.id = ads.account_id
        WHERE ads.date_key = ?
    """
    params: list[Any] = [date_key]
    if platform:
        sql += " AND a.platform = ?"
        params.append(platform)
    sql += " ORDER BY a.account_name ASC, ads.updated_at DESC"

    security_codes = _security_code_map(conn)
    rows: list[DailyAuthorViewpointRow] = []
    for record in conn.execute(sql, params).fetchall():
        date_value = str(record["date_key"] or "")
        account_name = str(record["account_name"] or "")
        author_nickname = str(record["author_nickname"] or "")
        author = _display_author(author_nickname, account_name)
        viewpoints = _json_loads(record["viewpoints_json"])
        for item in viewpoints:
            if str(item.get("entity_type") or "") != "stock":
                continue
            stance = str(item.get("stance") or "unknown")
            if stance == "mention_only":
                continue
            entity_key = str(item.get("entity_key") or "")
            entity_name = str(item.get("entity_name") or "")
            target_code = security_codes.get(entity_key) or entity_key or entity_name
            rows.append(
                DailyAuthorViewpointRow(
                    date=date_value,
                    author=author,
                    author_account=f"@{account_name}" if account_name else "",
                    target_name=entity_name,
                    target_code=target_code,
                    long_short=_long_short_label(str(item.get("direction") or "unknown"), stance),
                    conviction=_conviction_label(str(item.get("conviction") or "unknown")),
                    logic=str(item.get("logic") or ""),
                )
            )
    return rows


def _load_rows_postgres(
    conn: Any,
    *,
    date_key: str,
    platform: str | None = None,
    analysis_domain: str = "stock",
) -> list[DailyAuthorViewpointRow]:
    if platform and platform != "x":
        return []
    sql = """
        SELECT
          ads.date_key,
          a.username AS account_name,
          COALESCE(a.display_name, '') AS author_nickname,
          COALESCE(ads.viewpoints_json, '[]'::jsonb) AS viewpoints_json
        FROM author_daily_summaries ads
        JOIN x_accounts a ON a.id = ads.account_id
        WHERE ads.date_key = %s
          AND ads.analysis_domain = %s
        ORDER BY a.username ASC, ads.updated_at DESC
    """
    security_codes = _security_code_map_postgres(conn)
    rows: list[DailyAuthorViewpointRow] = []
    for record in conn.execute(sql, (date_key, analysis_domain)).fetchall():
        date_value = str(record["date_key"] or "")
        account_name = str(record["account_name"] or "")
        author_nickname = str(record["author_nickname"] or "")
        author = _display_author(author_nickname, account_name)
        viewpoints = record["viewpoints_json"] if isinstance(record["viewpoints_json"], list) else _json_loads(record["viewpoints_json"])
        for item in viewpoints:
            if str(item.get("entity_type") or "") != "stock":
                continue
            stance = str(item.get("stance") or "unknown")
            if stance == "mention_only":
                continue
            entity_key = str(item.get("entity_key") or "")
            entity_name = str(item.get("entity_name") or "")
            target_code = security_codes.get(entity_key) or entity_key or entity_name
            rows.append(
                DailyAuthorViewpointRow(
                    date=date_value,
                    author=author,
                    author_account=f"@{account_name}" if account_name else "",
                    target_name=entity_name,
                    target_code=target_code,
                    long_short=_long_short_label(str(item.get("direction") or "unknown"), stance),
                    conviction=_conviction_label(str(item.get("conviction") or "unknown")),
                    logic=str(item.get("logic") or ""),
                )
            )
    return rows


def resolve_latest_export_date(conn: Connection, *, platform: str | None = None) -> str | None:
    sql = """
        SELECT DISTINCT ads.date_key
        FROM author_daily_summaries ads
        JOIN accounts a ON a.id = ads.account_id
    """
    params: list[Any] = []
    if platform:
        sql += " WHERE a.platform = ?"
        params.append(platform)
    sql += " ORDER BY ads.date_key DESC"
    for row in conn.execute(sql, params).fetchall():
        date_key = str(row["date_key"] or "")
        if date_key and _load_rows(conn, date_key=date_key, platform=platform):
            return date_key
    return None


def resolve_latest_export_date_postgres(
    conn: Any,
    *,
    platform: str | None = None,
    analysis_domain: str = "stock",
) -> str | None:
    if platform and platform != "x":
        return None
    rows = conn.execute(
        """
        SELECT DISTINCT ads.date_key
        FROM author_daily_summaries ads
        WHERE ads.analysis_domain = %s
        ORDER BY ads.date_key DESC
        """,
        (analysis_domain,),
    ).fetchall()
    for row in rows:
        date_key = str(row["date_key"] or "")
        if date_key and _load_rows_postgres(conn, date_key=date_key, platform=platform, analysis_domain=analysis_domain):
            return date_key
    return None


def build_excel_rows(rows: list[DailyAuthorViewpointRow]) -> list[list[Any]]:
    result: list[list[Any]] = [
        ["日期", "作者", "作者账号", "标的名称", "标的代码/简称", "多空", "强烈程度", "逻辑"]
    ]
    for row in rows:
        result.append(
            [
                row.date,
                row.author,
                row.author_account,
                row.target_name,
                row.target_code,
                row.long_short,
                row.conviction,
                row.logic,
            ]
        )
    return result


def write_csv(path: Path, rows: list[list[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)


def export_daily_author_viewpoints(
    conn: Any,
    *,
    paths: AppPaths,
    date_key: str | None = None,
    platform: str | None = None,
    output_path: str | None = None,
    source: Literal["sqlite", "postgres"] = "sqlite",
    analysis_domain: str = "stock",
) -> DailyAuthorViewpointExportResult:
    if source == "postgres":
        export_date = date_key or resolve_latest_export_date_postgres(
            conn,
            platform=platform,
            analysis_domain=analysis_domain,
        )
        rows = _load_rows_postgres(
            conn,
            date_key=export_date,
            platform=platform,
            analysis_domain=analysis_domain,
        ) if export_date else []
    else:
        export_date = date_key or resolve_latest_export_date(conn, platform=platform)
        rows = _load_rows(conn, date_key=export_date, platform=platform) if export_date else []
    if not export_date:
        raise ValueError("没有找到可导出的作者日观点数据。")
    if not rows:
        raise ValueError(f"{export_date} 没有可导出的作者股票观点数据。")

    exports_dir = paths.runtime_dir / "exports"
    platform_suffix = f"-{platform}" if platform else ""
    final_path = Path(output_path).resolve() if output_path else exports_dir / f"daily-author-viewpoints-{export_date}{platform_suffix}.csv"
    write_csv(final_path, build_excel_rows(rows))
    return DailyAuthorViewpointExportResult(
        date=export_date,
        row_count=len(rows),
        output_path=final_path,
    )
