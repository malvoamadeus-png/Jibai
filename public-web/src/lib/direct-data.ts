import type { SupabaseClient } from "@supabase/supabase-js";

import type {
  AccountListItem,
  AdminAccountItem,
  AdminJobItem,
  AdminRequestItem,
  AuthorDayViewpoint,
  AuthorDetailData,
  AuthorListItem,
  AuthorTimelineDay,
  EntityAuthorView,
  EntityDetailData,
  EntityListItem,
  FeedDay,
  PagedResult,
  RequestListItem,
  StockKlineCandle,
  StockKlineData,
  StockKlineMarker,
  TimelineNote,
  UserProfile,
  ViewConviction,
  ViewDirection,
  ViewEntityType,
  ViewEvidenceType,
  ViewJudgmentType,
  ViewStance,
} from "@/lib/types";
import { makeAccountKey } from "@/lib/utils";
import { normalizeXUsername } from "@/lib/x";

type JsonRecord = Record<string, unknown>;

function assertNoError(error: unknown) {
  if (error && typeof error === "object" && "message" in error) {
    throw new Error(String((error as { message: unknown }).message));
  }
}

function asArray<T = unknown>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

function asRecord(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as JsonRecord) : {};
}

function asString(value: unknown, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function asNullableString(value: unknown) {
  return typeof value === "string" && value ? value : null;
}

function asNumber(value: unknown, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function asNullableNumber(value: unknown) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function normalizeStringArray(value: unknown) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item)).filter(Boolean);
  }
  if (typeof value === "string" && value.trim()) {
    return [value.trim()];
  }
  return [];
}

function normalizeViewpoint(rawValue: unknown): AuthorDayViewpoint | null {
  const raw = asRecord(rawValue);
  const stance = asString(raw.stance, "unknown") as ViewStance;
  if (stance === "mention_only") return null;

  return {
    entityType: asString(raw.entity_type ?? raw.entityType, "other") as ViewEntityType,
    entityKey: asString(raw.entity_key ?? raw.entityKey),
    entityName: asString(raw.entity_name ?? raw.entityName),
    stance,
    direction: asString(raw.direction, "unknown") as ViewDirection,
    judgmentType: asString(raw.judgment_type ?? raw.judgmentType, "unknown") as ViewJudgmentType,
    conviction: asString(raw.conviction, "unknown") as ViewConviction,
    evidenceType: asString(raw.evidence_type ?? raw.evidenceType, "unknown") as ViewEvidenceType,
    logic: asString(raw.logic),
    evidence: normalizeStringArray(raw.evidence),
    noteIds: normalizeStringArray(raw.note_ids ?? raw.noteIds),
    noteUrls: normalizeStringArray(raw.note_urls ?? raw.noteUrls),
    timeHorizons: normalizeStringArray(raw.time_horizons ?? raw.timeHorizons),
  };
}

function normalizeEntityAuthorView(rawValue: unknown): EntityAuthorView {
  const raw = asRecord(rawValue);
  const accountName = asString(raw.account_name ?? raw.author_name ?? raw.username).trim().replace(/^@/, "").toLowerCase();

  return {
    platform: asString(raw.platform, "x"),
    account_name: accountName,
    author_nickname: asString(raw.author_nickname ?? raw.display_name),
    stance: asString(raw.stance, "unknown") as ViewStance,
    direction: asString(raw.direction, "unknown") as ViewDirection,
    judgment_type: asString(raw.judgment_type, "unknown") as ViewJudgmentType,
    conviction: asString(raw.conviction, "unknown") as ViewConviction,
    evidence_type: asString(raw.evidence_type, "unknown") as ViewEvidenceType,
    logic: asString(raw.logic),
    note_ids: normalizeStringArray(raw.note_ids),
    note_urls: normalizeStringArray(raw.note_urls),
    evidence: normalizeStringArray(raw.evidence),
    time_horizons: normalizeStringArray(raw.time_horizons),
  };
}

function normalizeAuthorDay(rawValue: unknown): AuthorTimelineDay {
  const raw = asRecord(rawValue);
  const viewpoints = asArray(raw.viewpoints)
    .map(normalizeViewpoint)
    .filter((item): item is AuthorDayViewpoint => item !== null);

  return {
    date: asString(raw.date),
    status: asString(raw.status, "has_update_today") as AuthorTimelineDay["status"],
    noteCountToday: asNumber(raw.noteCountToday ?? raw.note_count_today),
    summaryText: asString(raw.summaryText ?? raw.summary_text),
    noteIds: normalizeStringArray(raw.noteIds ?? raw.note_ids),
    notes: asArray(raw.notes).map((item): TimelineNote => {
      const note = asRecord(item);
      return {
        note_id: asString(note.note_id),
        url: asString(note.url),
        title: asString(note.title),
        publish_time: asNullableString(note.publish_time),
      };
    }),
    viewpoints,
    mentionedStocks: normalizeStringArray(raw.mentionedStocks ?? raw.mentioned_stocks),
    mentionedThemes: normalizeStringArray(raw.mentionedThemes ?? raw.mentioned_themes),
    updatedAt: asString(raw.updatedAt ?? raw.updated_at),
  };
}

function normalizeEntityDay(rawValue: unknown) {
  const raw = asRecord(rawValue);
  const authorViews = asArray(raw.authorViews ?? raw.author_views).map(normalizeEntityAuthorView);

  return {
    date: asString(raw.date),
    mentionCount: asNumber(raw.mentionCount ?? raw.mention_count, authorViews.length),
    authorViews,
    updatedAt: asString(raw.updatedAt ?? raw.updated_at),
  };
}

function normalizeStockCandle(rawValue: unknown): StockKlineCandle | null {
  const raw = asRecord(rawValue);
  const open = asNullableNumber(raw.open ?? raw.open_price);
  const high = asNullableNumber(raw.high ?? raw.high_price);
  const low = asNullableNumber(raw.low ?? raw.low_price);
  const close = asNullableNumber(raw.close ?? raw.close_price);
  const date = asString(raw.date ?? raw.date_key);
  if (!date || open === null || high === null || low === null || close === null) {
    return null;
  }
  return {
    date,
    open,
    high,
    low,
    close,
    volume: asNullableNumber(raw.volume),
  };
}

function normalizeStockMarker(rawValue: unknown): StockKlineMarker | null {
  const raw = asRecord(rawValue);
  const date = asString(raw.date ?? raw.date_key);
  if (!date) return null;
  const authorViews = asArray(raw.authorViews ?? raw.author_views).map(normalizeEntityAuthorView);
  return {
    date,
    mentionCount: asNumber(raw.mentionCount ?? raw.mention_count, authorViews.length),
    authorViews,
  };
}

function normalizeStockChart(rawValue: unknown): StockKlineData | null {
  const raw = asRecord(rawValue);
  if (Object.keys(raw).length === 0) return null;
  const candles = asArray(raw.candles)
    .map(normalizeStockCandle)
    .filter((item): item is StockKlineCandle => item !== null)
    .sort((left, right) => left.date.localeCompare(right.date));
  const markers = asArray(raw.markers)
    .map(normalizeStockMarker)
    .filter((item): item is StockKlineMarker => item !== null)
    .sort((left, right) => left.date.localeCompare(right.date));
  return {
    sourceLabel: asNullableString(raw.sourceLabel ?? raw.source_label),
    message: asNullableString(raw.message),
    candles,
    markers,
  };
}

function normalizePaged<T>(
  rawValue: unknown,
  normalizeRow: (value: unknown) => T,
): PagedResult<T> {
  const raw = asRecord(rawValue);
  const rows = asArray(raw.rows).map(normalizeRow);
  const page = asNumber(raw.page, 1);
  const pageSize = asNumber(raw.pageSize ?? raw.page_size, rows.length || 1);
  const total = asNumber(raw.total, rows.length);

  return {
    rows,
    total,
    page,
    pageSize,
    totalPages: Math.max(1, asNumber(raw.totalPages ?? raw.total_pages, Math.ceil(total / pageSize))),
  };
}

function mapAccountRow(item: any): AccountListItem {
  return {
    id: String(item.id),
    username: String(item.username),
    displayName: String(item.display_name || item.displayName || item.username),
    profileUrl: String(item.profile_url || item.profileUrl || ""),
    subscribed: Boolean(item.subscribed),
    backfillCompletedAt: item.backfill_completed_at || item.backfillCompletedAt ? String(item.backfill_completed_at || item.backfillCompletedAt) : null,
  };
}

function mapAuthorRow(item: any): AuthorListItem {
  const accountName = String(item.account_name || item.accountName || item.username || "");
  const platform = String(item.platform || "x");
  return {
    accountId: String(item.account_id || item.accountId || item.id || ""),
    platform,
    accountKey: String(item.account_key || item.accountKey || makeAccountKey(platform, accountName)),
    accountName,
    authorNickname: String(item.author_nickname || item.authorNickname || item.display_name || accountName),
    profileUrl: String(item.profile_url || item.profileUrl || ""),
    latestDate: item.latest_date || item.latestDate ? String(item.latest_date || item.latestDate) : null,
    latestStatus: item.latest_status || item.latestStatus ? String(item.latest_status || item.latestStatus) : null,
    totalDays: Number(item.total_days || item.totalDays || 0),
    totalNotes: Number(item.total_notes || item.totalNotes || 0),
    updatedAt: item.updated_at || item.updatedAt ? String(item.updated_at || item.updatedAt) : null,
  };
}

function mapEntityRow(item: any): EntityListItem {
  return {
    key: String(item.entity_key || item.key || item.security_key || item.theme_key || ""),
    displayName: String(item.display_name || item.displayName || item.entity_key || item.key || ""),
    ticker: item.ticker ? String(item.ticker) : null,
    market: item.market ? String(item.market) : null,
    latestDate: item.latest_date || item.latestDate ? String(item.latest_date || item.latestDate) : null,
    mentionDays: Number(item.mention_days || item.mentionDays || 0),
    totalMentions: Number(item.total_mentions || item.totalMentions || item.mention_count || 0),
    updatedAt: item.updated_at || item.updatedAt ? String(item.updated_at || item.updatedAt) : null,
  };
}

export async function listAccounts(
  supabase: SupabaseClient,
  profile: UserProfile | null,
  query = "",
): Promise<AccountListItem[]> {
  const { data, error } = await supabase.rpc("list_public_accounts", {
    query_arg: query,
    limit_arg: 100,
  });
  assertNoError(error);

  const rows = (data || []).map(mapAccountRow);
  if (!profile) return rows;
  return rows;
}

export async function listVisibleAuthors(
  supabase: SupabaseClient,
  profile: UserProfile | null,
  query = "",
  limit = 100,
): Promise<AuthorListItem[]> {
  const { data, error } = await supabase.rpc("list_visible_authors", {
    query_arg: query,
    limit_arg: profile ? limit : 1,
  });
  assertNoError(error);
  return (data || []).map(mapAuthorRow);
}

export async function getVisibleAuthorTimeline(
  supabase: SupabaseClient,
  profile: UserProfile | null,
  accountId: string,
  page = 1,
): Promise<AuthorDetailData | null> {
  if (!accountId) return null;
  const { data, error } = await supabase.rpc("get_visible_author_timeline", {
    account_id_arg: accountId,
    page_arg: page,
    page_size_arg: profile ? 20 : 3,
  });
  assertNoError(error);

  const payload = asRecord(data);
  if (!payload.meta) return null;
  const meta = asRecord(payload.meta);
  const platform = asString(meta.platform, "x");
  const accountName = asString(meta.accountName ?? meta.account_name);

  return {
    accountId,
    platform,
    accountKey: makeAccountKey(platform, accountName),
    accountName,
    authorNickname: asString(meta.authorNickname ?? meta.author_nickname, accountName),
    authorId: asString(meta.authorId ?? meta.author_id),
    profileUrl: asString(meta.profileUrl ?? meta.profile_url),
    timeline: normalizePaged(payload.timeline, normalizeAuthorDay),
  } satisfies AuthorDetailData;
}

export async function listEntities(
  supabase: SupabaseClient,
  type: "stock" | "theme",
  profile: UserProfile | null,
  query = "",
  limit = 100,
): Promise<EntityListItem[]> {
  const { data, error } = await supabase.rpc("list_visible_entities", {
    entity_type_arg: type,
    query_arg: query,
    limit_arg: profile ? limit : 1,
  });
  assertNoError(error);
  return (data || []).map(mapEntityRow);
}

export async function getVisibleEntityTimeline(
  supabase: SupabaseClient,
  profile: UserProfile | null,
  type: "stock" | "theme",
  entityKey: string,
  page = 1,
): Promise<EntityDetailData | null> {
  if (!entityKey) return null;
  const { data, error } = await supabase.rpc("get_visible_entity_timeline", {
    entity_type_arg: type,
    entity_key_arg: entityKey,
    page_arg: page,
    page_size_arg: profile ? 20 : 3,
  });
  assertNoError(error);

  const payload = asRecord(data);
  if (!payload.meta) return null;
  const meta = asRecord(payload.meta);

  return {
    key: asString(meta.key ?? meta.entityKey ?? meta.entity_key, entityKey),
    displayName: asString(meta.displayName ?? meta.display_name, entityKey),
    ticker: asNullableString(meta.ticker),
    market: asNullableString(meta.market),
    timeline: normalizePaged(payload.timeline, normalizeEntityDay),
    chart: type === "stock" ? normalizeStockChart(payload.chart) : null,
  } satisfies EntityDetailData;
}

export async function listMyRequests(
  supabase: SupabaseClient,
  profile: UserProfile | null,
): Promise<RequestListItem[]> {
  if (!profile) return [];
  const { data, error } = await supabase
    .from("account_requests")
    .select("id, status, raw_input, normalized_username, created_at")
    .eq("requester_id", profile.id)
    .order("created_at", { ascending: false })
    .limit(20);
  assertNoError(error);
  return (data || []).map(
    (item: any): RequestListItem => ({
      id: String(item.id),
      status: String(item.status),
      rawInput: String(item.raw_input),
      normalizedUsername: String(item.normalized_username),
      createdAt: String(item.created_at),
    }),
  );
}

export async function submitAccount(supabase: SupabaseClient, rawInput: string) {
  const username = normalizeXUsername(rawInput);
  const { error } = await supabase.rpc("submit_x_account", {
    raw_input_arg: rawInput,
    username_arg: username,
  });
  assertNoError(error);
}

export async function setSubscription(
  supabase: SupabaseClient,
  profile: UserProfile,
  accountId: string,
  subscribed: boolean,
) {
  if (subscribed) {
    const { error } = await supabase.from("user_subscriptions").upsert(
      {
        account_id: accountId,
        user_id: profile.id,
      },
      { onConflict: "user_id,account_id" },
    );
    assertNoError(error);
    return;
  }

  const { error } = await supabase.from("user_subscriptions").delete().eq("user_id", profile.id).eq("account_id", accountId);
  assertNoError(error);
}

export async function listFeed(
  supabase: SupabaseClient,
  profile: UserProfile | null,
  limit = 40,
): Promise<FeedDay[]> {
  const authors = await listVisibleAuthors(supabase, profile, "", limit);
  const items = await Promise.all(
    authors.slice(0, Math.min(authors.length, limit)).map(async (author) => {
      const detail = await getVisibleAuthorTimeline(supabase, profile, author.accountId, 1);
      return { author, detail };
    }),
  );

  return items.flatMap(({ author, detail }) =>
    (detail?.timeline.rows ?? []).map(
      (day): FeedDay => ({
        id: `${author.accountId}-${day.date}`,
        username: author.accountName,
        displayName: author.authorNickname || author.accountName,
        profileUrl: author.profileUrl,
        date: day.date,
        status: day.status,
        noteCount: day.noteCountToday,
        summary: day.summaryText,
        notes: day.notes,
        viewpoints: day.viewpoints as unknown as Array<Record<string, unknown>>,
        updatedAt: day.updatedAt,
      }),
    ),
  );
}

export async function listAdminDashboard(supabase: SupabaseClient) {
  const [requests, accountCount, approvedAccounts, jobs] = await Promise.all([
    supabase
      .from("account_requests")
      .select("id, raw_input, normalized_username, created_at, requester_id, x_accounts(id, username, display_name, profile_url, status)")
      .eq("status", "pending")
      .order("created_at", { ascending: true })
      .limit(50),
    supabase.from("x_accounts").select("id", { count: "exact" }).eq("status", "approved"),
    supabase
      .from("x_accounts")
      .select("id, username, display_name, profile_url, backfill_completed_at")
      .eq("status", "approved")
      .order("approved_at", { ascending: false, nullsFirst: false })
      .limit(100),
    supabase
      .from("crawl_jobs")
      .select("id, kind, status, summary, error_text, created_at, finished_at")
      .order("created_at", { ascending: false })
      .limit(20),
  ]);
  assertNoError(requests.error);
  assertNoError(accountCount.error);
  assertNoError(approvedAccounts.error);
  assertNoError(jobs.error);

  const requesterIds = Array.from(new Set((requests.data || []).map((item: any) => String(item.requester_id))));
  const { data: profiles, error: profileError } = requesterIds.length
    ? await supabase.from("profiles").select("id, email").in("id", requesterIds)
    : { data: [], error: null };
  assertNoError(profileError);
  const profileMap = new Map((profiles || []).map((item: any) => [String(item.id), String(item.email)]));

  return {
    approvedCount: accountCount.count || 0,
    approvedAccounts: (approvedAccounts.data || []).map(
      (item: any): AdminAccountItem => ({
        id: String(item.id),
        username: String(item.username),
        displayName: String(item.display_name || item.username),
        profileUrl: String(item.profile_url || ""),
        backfillCompletedAt: item.backfill_completed_at ? String(item.backfill_completed_at) : null,
      }),
    ),
    jobs: (jobs.data || []).map(
      (item: any): AdminJobItem => ({
        id: String(item.id),
        kind: String(item.kind),
        status: String(item.status),
        summary: String(item.summary || ""),
        errorText: item.error_text ? String(item.error_text) : null,
        createdAt: String(item.created_at),
        finishedAt: item.finished_at ? String(item.finished_at) : null,
      }),
    ),
    requests: (requests.data || []).map((item: any): AdminRequestItem => {
      const account = Array.isArray(item.x_accounts) ? item.x_accounts[0] : item.x_accounts;
      return {
        id: String(item.id),
        rawInput: String(item.raw_input),
        normalizedUsername: String(item.normalized_username),
        requesterEmail: profileMap.get(String(item.requester_id)) || "unknown",
        createdAt: String(item.created_at),
        account: {
          id: String(account?.id || ""),
          username: String(account?.username || item.normalized_username),
          displayName: String(account?.display_name || item.normalized_username),
          profileUrl: String(account?.profile_url || ""),
          status: String(account?.status || "pending"),
        },
      };
    }),
  };
}

export async function approveRequest(supabase: SupabaseClient, requestId: string) {
  const { error } = await supabase.rpc("approve_account_request", { request_id_arg: requestId });
  assertNoError(error);
}

export async function rejectRequest(supabase: SupabaseClient, requestId: string) {
  const { error } = await supabase.rpc("reject_account_request", { request_id_arg: requestId });
  assertNoError(error);
}

export async function disableAccount(supabase: SupabaseClient, accountId: string) {
  const { error } = await supabase.rpc("disable_x_account", { account_id_arg: accountId });
  assertNoError(error);
}

export async function enqueueManualCrawl(supabase: SupabaseClient) {
  const { error } = await supabase.rpc("enqueue_manual_crawl");
  assertNoError(error);
}
