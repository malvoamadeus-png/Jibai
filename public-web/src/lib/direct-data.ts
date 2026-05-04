import type { SupabaseClient } from "@supabase/supabase-js";

import type {
  AccountListItem,
  AdminAccountItem,
  AdminJobItem,
  AdminRequestItem,
  EntityListItem,
  FeedDay,
  RequestListItem,
  UserProfile,
} from "@/lib/types";
import { normalizeXUsername } from "@/lib/x";

function assertNoError(error: unknown) {
  if (error && typeof error === "object" && "message" in error) {
    throw new Error(String((error as { message: unknown }).message));
  }
}

function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

export async function listAccounts(supabase: SupabaseClient, profile: UserProfile, query = "") {
  let accountQuery = supabase
    .from("x_accounts")
    .select("id, username, display_name, profile_url, backfill_completed_at")
    .eq("status", "approved")
    .order("username", { ascending: true })
    .limit(100);
  if (query.trim()) {
    accountQuery = accountQuery.ilike("username", `%${query.trim()}%`);
  }

  const [{ data: accounts, error }, { data: subscriptions, error: subError }] = await Promise.all([
    accountQuery,
    supabase.from("user_subscriptions").select("account_id").eq("user_id", profile.id),
  ]);
  assertNoError(error);
  assertNoError(subError);

  const subscribedIds = new Set((subscriptions || []).map((item: any) => String(item.account_id)));
  return (accounts || []).map(
    (item: any): AccountListItem => ({
      id: String(item.id),
      username: String(item.username),
      displayName: String(item.display_name || item.username),
      profileUrl: String(item.profile_url),
      subscribed: subscribedIds.has(String(item.id)),
      backfillCompletedAt: item.backfill_completed_at ? String(item.backfill_completed_at) : null,
    }),
  );
}

export async function listMyRequests(supabase: SupabaseClient, profile: UserProfile) {
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

export async function listFeed(supabase: SupabaseClient, profile: UserProfile, limit = 40) {
  const { data: subscriptions, error: subError } = await supabase
    .from("user_subscriptions")
    .select("account_id")
    .eq("user_id", profile.id);
  assertNoError(subError);
  const accountIds = (subscriptions || []).map((item: any) => String(item.account_id));
  if (!accountIds.length) return [];

  const [{ data: accounts, error: accountError }, { data: rows, error }] = await Promise.all([
    supabase.from("x_accounts").select("id, username, display_name, profile_url").in("id", accountIds),
    supabase
      .from("author_daily_summaries")
      .select("id, account_id, date_key, status, note_count_today, summary_text, notes_json, viewpoints_json, updated_at")
      .in("account_id", accountIds)
      .order("date_key", { ascending: false })
      .order("updated_at", { ascending: false })
      .limit(limit),
  ]);
  assertNoError(accountError);
  assertNoError(error);

  const accountMap = new Map((accounts || []).map((item: any) => [String(item.id), item]));
  return (rows || []).map((item: any): FeedDay => {
    const account = accountMap.get(String(item.account_id)) || {};
    return {
      id: String(item.id),
      username: String(account.username || ""),
      displayName: String(account.display_name || account.username || ""),
      profileUrl: String(account.profile_url || ""),
      date: String(item.date_key),
      status: String(item.status),
      noteCount: Number(item.note_count_today || 0),
      summary: String(item.summary_text || ""),
      notes: asArray(item.notes_json),
      viewpoints: asArray(item.viewpoints_json),
      updatedAt: String(item.updated_at),
    };
  });
}

export async function listEntities(supabase: SupabaseClient, type: "stock" | "theme") {
  const { data, error } = await supabase.rpc("list_my_entities", { entity_type_arg: type });
  assertNoError(error);
  return (data || []).map(
    (item: any): EntityListItem => ({
      key: String(item.entity_key),
      displayName: String(item.display_name || item.entity_key),
      latestDate: item.latest_date ? String(item.latest_date) : null,
      mentionCount: Number(item.mention_count || 0),
      authorCount: Number(item.author_count || 0),
    }),
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
