import "server-only";

import type Database from "better-sqlite3";
import { z } from "zod";

import type {
  AuthorDetailData,
  AuthorListItem,
  OverviewData,
  PagedResult,
  StockDetailData,
  StockListItem,
  ThemeDetailData,
  ThemeListItem,
} from "@/lib/types";
import {
  authorDayViewpointSchema,
  authorListItemSchema,
  authorTimelineDaySchema,
  entityAuthorViewSchema,
  stockListItemSchema,
  stockTimelineDaySchema,
  themeListItemSchema,
  themeTimelineDaySchema,
  timelineNoteSchema,
} from "@/lib/schemas";
import { withDb } from "@/lib/db";
import { makeAccountKey } from "@/lib/utils";

function parseJson<T>(raw: string | null, schema: z.ZodType<T>, fallback: T) {
  if (!raw) return fallback;
  try {
    return schema.parse(JSON.parse(raw));
  } catch {
    return fallback;
  }
}

function toPagedResult<T>(rows: T[], total: number, page: number, pageSize: number): PagedResult<T> {
  return {
    rows,
    total,
    page,
    pageSize,
    totalPages: Math.max(1, Math.ceil(total / pageSize)),
  };
}

function splitAccountKey(accountKey: string) {
  const separator = accountKey.indexOf("::");
  if (separator < 0) {
    return null;
  }
  return {
    platform: accountKey.slice(0, separator),
    accountName: accountKey.slice(separator + 2),
  };
}

function authorHasViewpoints(alias: string) {
  return `EXISTS (
    SELECT 1
    FROM json_each(
      CASE
        WHEN json_valid(COALESCE(${alias}.viewpoints_json, '[]')) THEN COALESCE(${alias}.viewpoints_json, '[]')
        ELSE '[]'
      END
    ) author_viewpoint
    WHERE COALESCE(json_extract(author_viewpoint.value, '$.stance'), '') <> 'mention_only'
  )`;
}

type AuthorDayRow = {
  date: string;
  status: "has_update_today" | "no_update_today" | "crawl_failed";
  noteCountToday: number;
  summaryText: string;
  noteIdsJson: string | null;
  notesJson: string | null;
  viewpointsJson: string | null;
  mentionedStocksJson: string | null;
  mentionedThemesJson: string | null;
  updatedAt: string;
};

type EntityDayRow = {
  date: string;
  mentionCount: number;
  authorViewsJson: string | null;
  updatedAt: string;
};

function mapAuthorViewpoints(raw: string | null) {
  const values = parseJson(
    raw,
    z.array(
      z.object({
        entity_type: z.enum(["stock", "theme", "macro", "other"]),
        entity_key: z.string(),
        entity_name: z.string(),
        stance: z.string(),
        logic: z.string().default(""),
        evidence: z.array(z.string()).default([]),
        note_ids: z.array(z.string()).default([]),
        note_urls: z.array(z.string()).default([]),
        time_horizons: z.array(z.string()).default([]),
      }),
    ),
    [],
  );

  return values
    .filter((item) => item.stance !== "mention_only")
    .map((item) =>
      authorDayViewpointSchema.parse({
        entityType: item.entity_type,
        entityKey: item.entity_key,
        entityName: item.entity_name,
        stance: item.stance,
        logic: item.logic,
        evidence: item.evidence,
        noteIds: item.note_ids,
        noteUrls: item.note_urls,
        timeHorizons: item.time_horizons,
      }),
    );
}

function dedupeStrings(values: string[]) {
  const seen = new Set<string>();
  const result: string[] = [];

  for (const value of values) {
    const cleaned = value.trim();
    if (!cleaned || seen.has(cleaned)) continue;
    seen.add(cleaned);
    result.push(cleaned);
  }

  return result;
}

function collectMentionedEntities(
  viewpoints: ReturnType<typeof mapAuthorViewpoints>,
  entityType: "stock" | "theme",
) {
  return dedupeStrings(
    viewpoints
      .filter((viewpoint) => viewpoint.entityType === entityType)
      .map((viewpoint) => viewpoint.entityName || viewpoint.entityKey),
  );
}

function getAuthorsPageFromDb(
  db: Database.Database,
  page: number,
  pageSize: number,
  query: string,
  platform: string,
): PagedResult<AuthorListItem> {
  const normalizedQuery = `%${query.trim().toLowerCase()}%`;
  const offset = (page - 1) * pageSize;
  const filters = [];
  const params: Array<string | number> = [];
  if (query.trim()) {
    filters.push("(LOWER(a.account_name) LIKE ? OR LOWER(COALESCE(a.author_nickname, '')) LIKE ?)");
    params.push(normalizedQuery, normalizedQuery);
  }
  if (platform.trim()) {
    filters.push("a.platform = ?");
    params.push(platform.trim());
  }
  const whereClause = filters.length > 0 ? `WHERE ${filters.join(" AND ")}` : "";

  const countRow = db
    .prepare(
      `
      SELECT COUNT(*) AS total
      FROM (
        SELECT a.id
        FROM accounts a
        JOIN author_daily_summaries ads
          ON ads.account_id = a.id
         AND ${authorHasViewpoints("ads")}
        ${whereClause}
        GROUP BY a.id
      ) counted
      `,
    )
    .get(...params) as { total: number };

  const authorRows = db
    .prepare(
      `
      SELECT
        a.platform AS platform,
        a.account_name AS accountName,
        COALESCE(a.author_nickname, '') AS authorNickname,
        COALESCE(a.profile_url, '') AS profileUrl,
        MAX(ads.date_key) AS latestDate,
        (
          SELECT ads2.status
          FROM author_daily_summaries ads2
          WHERE ads2.account_id = a.id
            AND ${authorHasViewpoints("ads2")}
          ORDER BY ads2.date_key DESC
          LIMIT 1
        ) AS latestStatus,
        COUNT(*) AS totalDays,
        COALESCE(SUM(ads.note_count_today), 0) AS totalNotes,
        MAX(ads.updated_at) AS updatedAt
      FROM accounts a
      JOIN author_daily_summaries ads
        ON ads.account_id = a.id
       AND ${authorHasViewpoints("ads")}
      ${whereClause}
      GROUP BY a.id
      ORDER BY latestDate DESC, updatedAt DESC, a.account_name ASC
      LIMIT ? OFFSET ?
      `,
    )
    .all(...params, pageSize, offset) as Array<{
      platform: string;
      accountName: string;
      authorNickname: string;
      profileUrl: string;
      latestDate: string | null;
      latestStatus: string | null;
      totalDays: number;
      totalNotes: number;
      updatedAt: string | null;
    }>;
  const rows = authorRows.map((row) =>
    authorListItemSchema.parse({
      platform: row.platform,
      accountName: row.accountName,
      authorNickname: row.authorNickname,
      profileUrl: row.profileUrl,
      latestDate: row.latestDate,
      latestStatus: row.latestStatus,
      totalDays: row.totalDays,
      totalNotes: row.totalNotes,
      updatedAt: row.updatedAt,
      accountKey: makeAccountKey(row.platform, row.accountName),
    }),
  );

  return toPagedResult(rows, countRow.total, page, pageSize);
}

function getAuthorDetailFromDb(
  db: Database.Database,
  accountKey: string,
  page: number,
  pageSize: number,
): AuthorDetailData | null {
  const parsedKey = splitAccountKey(accountKey);
  if (!parsedKey) return null;

  const meta = db
    .prepare(
      `
      SELECT
        a.platform,
        a.account_name AS accountName,
        COALESCE(a.author_nickname, '') AS authorNickname,
        COALESCE(a.author_id, '') AS authorId,
        COALESCE(a.profile_url, '') AS profileUrl
      FROM accounts a
      WHERE a.platform = ? AND a.account_name = ?
      LIMIT 1
      `,
    )
    .get(parsedKey.platform, parsedKey.accountName) as
    | {
        platform: string;
        accountName: string;
        authorNickname: string;
        authorId: string;
        profileUrl: string;
      }
    | undefined;

  if (!meta) return null;

  const countRow = db
    .prepare(
      `
      SELECT COUNT(*) AS total
      FROM author_daily_summaries ads
      JOIN accounts a ON a.id = ads.account_id
      WHERE a.platform = ? AND a.account_name = ?
        AND ${authorHasViewpoints("ads")}
      `,
    )
    .get(parsedKey.platform, parsedKey.accountName) as { total: number };

  const offset = (page - 1) * pageSize;
  const authorDayRows = db
    .prepare(
      `
      SELECT
        ads.date_key AS date,
        ads.status AS status,
        ads.note_count_today AS noteCountToday,
        ads.summary_text AS summaryText,
        ads.note_ids_json AS noteIdsJson,
        ads.notes_json AS notesJson,
        ads.viewpoints_json AS viewpointsJson,
        ads.mentioned_stocks_json AS mentionedStocksJson,
        ads.mentioned_themes_json AS mentionedThemesJson,
        ads.updated_at AS updatedAt
      FROM author_daily_summaries ads
      JOIN accounts a ON a.id = ads.account_id
      WHERE a.platform = ? AND a.account_name = ?
        AND ${authorHasViewpoints("ads")}
      ORDER BY ads.date_key DESC
      LIMIT ? OFFSET ?
      `,
    )
    .all(parsedKey.platform, parsedKey.accountName, pageSize, offset) as AuthorDayRow[];
  const rows = authorDayRows.map((row) => {
    const viewpoints = mapAuthorViewpoints(row.viewpointsJson);

    return authorTimelineDaySchema.parse({
      date: row.date,
      status: row.status,
      noteCountToday: row.noteCountToday,
      summaryText: row.summaryText,
      noteIds: parseJson(row.noteIdsJson, z.array(z.string()), []),
      notes: parseJson(row.notesJson, z.array(timelineNoteSchema), []),
      viewpoints,
      mentionedStocks: collectMentionedEntities(viewpoints, "stock"),
      mentionedThemes: collectMentionedEntities(viewpoints, "theme"),
      updatedAt: row.updatedAt,
    });
  });

  return {
    ...meta,
    accountKey,
    timeline: toPagedResult(rows, countRow.total, page, pageSize),
  };
}

function getStocksPageFromDb(
  db: Database.Database,
  page: number,
  pageSize: number,
  query: string,
): PagedResult<StockListItem> {
  const normalizedQuery = `%${query.trim().toLowerCase()}%`;
  const offset = (page - 1) * pageSize;
  const whereClause = query.trim()
    ? "WHERE LOWER(se.security_key) LIKE ? OR LOWER(se.display_name) LIKE ? OR LOWER(COALESCE(se.ticker, '')) LIKE ?"
    : "";
  const params: Array<string | number> = query.trim()
    ? [normalizedQuery, normalizedQuery, normalizedQuery]
    : [];

  const countRow = db
    .prepare(
      `
      SELECT COUNT(*) AS total
      FROM (
        SELECT se.id
        FROM security_entities se
        JOIN security_daily_views sdv ON sdv.security_id = se.id
        ${whereClause}
        GROUP BY se.id
      ) counted
      `,
    )
    .get(...params) as { total: number };

  const stockRows = db
    .prepare(
      `
      SELECT
        se.security_key AS securityKey,
        se.display_name AS displayName,
        se.ticker AS ticker,
        se.market AS market,
        MAX(sdv.date_key) AS latestDate,
        COUNT(*) AS mentionDays,
        COALESCE(SUM(sdv.mention_count), 0) AS totalMentions,
        MAX(sdv.updated_at) AS updatedAt
      FROM security_entities se
      JOIN security_daily_views sdv ON sdv.security_id = se.id
      ${whereClause}
      GROUP BY se.id
      ORDER BY latestDate DESC, totalMentions DESC, se.display_name ASC
      LIMIT ? OFFSET ?
      `,
    )
    .all(...params, pageSize, offset);
  const rows = stockRows.map((row) => stockListItemSchema.parse(row));

  return toPagedResult(rows, countRow.total, page, pageSize);
}

function getStockDetailFromDb(
  db: Database.Database,
  securityKey: string,
  page: number,
  pageSize: number,
): StockDetailData | null {
  const meta = db
    .prepare(
      `
      SELECT security_key AS securityKey, display_name AS displayName, ticker, market
      FROM security_entities
      WHERE security_key = ?
      LIMIT 1
      `,
    )
    .get(securityKey) as
    | {
        securityKey: string;
        displayName: string;
        ticker: string | null;
        market: string | null;
      }
    | undefined;
  if (!meta) return null;

  const countRow = db
    .prepare(
      "SELECT COUNT(*) AS total FROM security_daily_views sdv JOIN security_entities se ON se.id = sdv.security_id WHERE se.security_key = ?",
    )
    .get(securityKey) as { total: number };

  const offset = (page - 1) * pageSize;
  const stockDayRows = db
    .prepare(
      `
      SELECT
        sdv.date_key AS date,
        sdv.mention_count AS mentionCount,
        sdv.author_views_json AS authorViewsJson,
        sdv.updated_at AS updatedAt
      FROM security_daily_views sdv
      JOIN security_entities se ON se.id = sdv.security_id
      WHERE se.security_key = ?
      ORDER BY sdv.date_key DESC
      LIMIT ? OFFSET ?
      `,
    )
    .all(securityKey, pageSize, offset) as EntityDayRow[];
  const rows = stockDayRows.map((row) =>
    stockTimelineDaySchema.parse({
      date: row.date,
      mentionCount: row.mentionCount,
      authorViews: parseJson(row.authorViewsJson, z.array(entityAuthorViewSchema), []),
      updatedAt: row.updatedAt,
    }),
  );

  return {
    ...meta,
    timeline: toPagedResult(rows, countRow.total, page, pageSize),
  };
}

function getThemesPageFromDb(
  db: Database.Database,
  page: number,
  pageSize: number,
  query: string,
): PagedResult<ThemeListItem> {
  const normalizedQuery = `%${query.trim().toLowerCase()}%`;
  const offset = (page - 1) * pageSize;
  const whereClause = query.trim()
    ? "WHERE LOWER(te.theme_key) LIKE ? OR LOWER(te.display_name) LIKE ?"
    : "";
  const params: Array<string | number> = query.trim()
    ? [normalizedQuery, normalizedQuery]
    : [];

  const countRow = db
    .prepare(
      `
      SELECT COUNT(*) AS total
      FROM (
        SELECT te.id
        FROM theme_entities te
        JOIN theme_daily_views tdv ON tdv.theme_id = te.id
        ${whereClause}
        GROUP BY te.id
      ) counted
      `,
    )
    .get(...params) as { total: number };

  const rows = db
    .prepare(
      `
      SELECT
        te.theme_key AS themeKey,
        te.display_name AS displayName,
        MAX(tdv.date_key) AS latestDate,
        COUNT(*) AS mentionDays,
        COALESCE(SUM(tdv.mention_count), 0) AS totalMentions,
        MAX(tdv.updated_at) AS updatedAt
      FROM theme_entities te
      JOIN theme_daily_views tdv ON tdv.theme_id = te.id
      ${whereClause}
      GROUP BY te.id
      ORDER BY latestDate DESC, totalMentions DESC, te.display_name ASC
      LIMIT ? OFFSET ?
      `,
    )
    .all(...params, pageSize, offset)
    .map((row) => themeListItemSchema.parse(row));

  return toPagedResult(rows, countRow.total, page, pageSize);
}

function getThemeDetailFromDb(
  db: Database.Database,
  themeKey: string,
  page: number,
  pageSize: number,
): ThemeDetailData | null {
  const meta = db
    .prepare(
      `
      SELECT theme_key AS themeKey, display_name AS displayName
      FROM theme_entities
      WHERE theme_key = ?
      LIMIT 1
      `,
    )
    .get(themeKey) as
    | {
        themeKey: string;
        displayName: string;
      }
    | undefined;
  if (!meta) return null;

  const countRow = db
    .prepare(
      "SELECT COUNT(*) AS total FROM theme_daily_views tdv JOIN theme_entities te ON te.id = tdv.theme_id WHERE te.theme_key = ?",
    )
    .get(themeKey) as { total: number };

  const offset = (page - 1) * pageSize;
  const rows = db
    .prepare(
      `
      SELECT
        tdv.date_key AS date,
        tdv.mention_count AS mentionCount,
        tdv.author_views_json AS authorViewsJson,
        tdv.updated_at AS updatedAt
      FROM theme_daily_views tdv
      JOIN theme_entities te ON te.id = tdv.theme_id
      WHERE te.theme_key = ?
      ORDER BY tdv.date_key DESC
      LIMIT ? OFFSET ?
      `,
    )
    .all(themeKey, pageSize, offset) as EntityDayRow[];

  return {
    ...meta,
    timeline: toPagedResult(
      rows.map((row) =>
        themeTimelineDaySchema.parse({
          date: row.date,
          mentionCount: row.mentionCount,
          authorViews: parseJson(row.authorViewsJson, z.array(entityAuthorViewSchema), []),
          updatedAt: row.updatedAt,
        }),
      ),
      countRow.total,
      page,
      pageSize,
    ),
  };
}

export function getOverview(): OverviewData {
  return withDb(
    (db) => {
      const counts = db
        .prepare(
          `
          SELECT
            (SELECT COUNT(*) FROM accounts) AS authorCount,
            (SELECT COUNT(*) FROM security_entities) AS stockCount,
            (SELECT COUNT(*) FROM theme_entities) AS themeCount,
            (SELECT COUNT(*) FROM content_items) AS contentCount,
            (SELECT MAX(run_at) FROM analysis_runs) AS lastRunAt
          `,
        )
        .get() as {
        authorCount: number;
        stockCount: number;
        themeCount: number;
        contentCount: number;
        lastRunAt: string | null;
      };

      return {
        lastRunAt: counts.lastRunAt,
        authorCount: counts.authorCount,
        stockCount: counts.stockCount,
        themeCount: counts.themeCount,
        contentCount: counts.contentCount,
        latestAuthors: getAuthorsPageFromDb(db, 1, 4, "", "").rows,
        latestStocks: getStocksPageFromDb(db, 1, 4, "").rows,
        latestThemes: getThemesPageFromDb(db, 1, 4, "").rows,
      };
    },
    {
      lastRunAt: null,
      authorCount: 0,
      stockCount: 0,
      themeCount: 0,
      contentCount: 0,
      latestAuthors: [],
      latestStocks: [],
      latestThemes: [],
    },
  );
}

export function getAuthorsPage(options: {
  page?: number;
  pageSize?: number;
  q?: string;
  platform?: string;
}) {
  const page = options.page ?? 1;
  const pageSize = options.pageSize ?? 20;
  return withDb(
    (db) => getAuthorsPageFromDb(db, page, pageSize, options.q ?? "", options.platform ?? ""),
    toPagedResult<AuthorListItem>([], 0, page, pageSize),
  );
}

export function getAuthorDetail(options: {
  accountKey: string;
  page?: number;
  pageSize?: number;
}) {
  const page = options.page ?? 1;
  const pageSize = options.pageSize ?? 20;
  return withDb((db) => getAuthorDetailFromDb(db, options.accountKey, page, pageSize), null);
}

export function getStocksPage(options: {
  page?: number;
  pageSize?: number;
  q?: string;
}) {
  const page = options.page ?? 1;
  const pageSize = options.pageSize ?? 20;
  return withDb(
    (db) => getStocksPageFromDb(db, page, pageSize, options.q ?? ""),
    toPagedResult<StockListItem>([], 0, page, pageSize),
  );
}

export function getStockDetail(options: {
  securityKey: string;
  page?: number;
  pageSize?: number;
}) {
  const page = options.page ?? 1;
  const pageSize = options.pageSize ?? 20;
  return withDb((db) => getStockDetailFromDb(db, options.securityKey, page, pageSize), null);
}

export function getThemesPage(options: {
  page?: number;
  pageSize?: number;
  q?: string;
}) {
  const page = options.page ?? 1;
  const pageSize = options.pageSize ?? 20;
  return withDb(
    (db) => getThemesPageFromDb(db, page, pageSize, options.q ?? ""),
    toPagedResult<ThemeListItem>([], 0, page, pageSize),
  );
}

export function getThemeDetail(options: {
  themeKey: string;
  page?: number;
  pageSize?: number;
}) {
  const page = options.page ?? 1;
  const pageSize = options.pageSize ?? 20;
  return withDb((db) => getThemeDetailFromDb(db, options.themeKey, page, pageSize), null);
}
