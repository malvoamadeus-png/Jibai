import "server-only";

import { getSupabaseAdmin } from "@/lib/supabase/admin";
import type {
  AccountListItem,
  AdminJobItem,
  AdminRequestItem,
  EntityListItem,
  FeedDay,
  RequestListItem,
  UserProfile,
} from "@/lib/types";
import { normalizeXUsername, profileUrlForUsername } from "@/lib/x";

function assertNoError(error: unknown) {
  if (error && typeof error === "object" && "message" in error) {
    throw new Error(String((error as { message: unknown }).message));
  }
}

function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

export async function listAccounts(profile: UserProfile, query = "") {
  const admin = getSupabaseAdmin();
  let accountQuery = admin
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
    admin.from("user_subscriptions").select("account_id").eq("user_id", profile.id),
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

export async function listMyRequests(profile: UserProfile) {
  const { data, error } = await getSupabaseAdmin()
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

export async function submitAccount(profile: UserProfile, rawInput: string) {
  const username = normalizeXUsername(rawInput);
  const profileUrl = profileUrlForUsername(username);
  const admin = getSupabaseAdmin();

  const { data: existing, error: lookupError } = await admin
    .from("x_accounts")
    .select("id, status")
    .eq("username", username)
    .maybeSingle();
  assertNoError(lookupError);

  let account = existing as { id: string; status: string } | null;
  if (!account) {
    const { data: inserted, error } = await admin
      .from("x_accounts")
      .insert({
        username,
        display_name: username,
        profile_url: profileUrl,
        status: "pending",
        submitted_by: profile.id,
      })
      .select("id, status")
      .single();
    assertNoError(error);
    account = inserted as { id: string; status: string };
  }

  const requestStatus = account.status === "approved" ? "approved" : "pending";
  const { error: requestError } = await admin.from("account_requests").upsert(
    {
      account_id: account.id,
      requester_id: profile.id,
      raw_input: rawInput,
      normalized_username: username,
      status: requestStatus,
      reviewed_at: requestStatus === "approved" ? new Date().toISOString() : null,
    },
    { onConflict: "account_id,requester_id" },
  );
  assertNoError(requestError);

  if (account.status === "approved") {
    await setSubscription(profile, account.id, true);
  }
}

export async function setSubscription(profile: UserProfile, accountId: string, subscribed: boolean) {
  const admin = getSupabaseAdmin();
  if (subscribed) {
    const { data: account, error: accountError } = await admin
      .from("x_accounts")
      .select("id")
      .eq("id", accountId)
      .eq("status", "approved")
      .maybeSingle();
    assertNoError(accountError);
    if (!account) throw new Error("Account is not available.");
    const { error } = await admin.from("user_subscriptions").upsert(
      {
        user_id: profile.id,
        account_id: accountId,
      },
      { onConflict: "user_id,account_id" },
    );
    assertNoError(error);
    return;
  }
  const { error } = await admin
    .from("user_subscriptions")
    .delete()
    .eq("user_id", profile.id)
    .eq("account_id", accountId);
  assertNoError(error);
}

export async function listFeed(profile: UserProfile, limit = 40) {
  const admin = getSupabaseAdmin();
  const { data: subscriptions, error: subError } = await admin
    .from("user_subscriptions")
    .select("account_id")
    .eq("user_id", profile.id);
  assertNoError(subError);
  const accountIds = (subscriptions || []).map((item: any) => String(item.account_id));
  if (!accountIds.length) return [];

  const [{ data: accounts, error: accountError }, { data: rows, error }] = await Promise.all([
    admin.from("x_accounts").select("id, username, display_name, profile_url").in("id", accountIds),
    admin
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

async function subscribedUsernames(profile: UserProfile) {
  const { data, error } = await getSupabaseAdmin()
    .from("user_subscriptions")
    .select("x_accounts(username)")
    .eq("user_id", profile.id);
  assertNoError(error);
  return new Set(
    (data || [])
      .map((item: any) => item.x_accounts?.username)
      .filter(Boolean)
      .map((value: string) => value.toLowerCase()),
  );
}

export async function listEntities(profile: UserProfile, type: "stock" | "theme") {
  const admin = getSupabaseAdmin();
  const usernames = await subscribedUsernames(profile);
  if (!usernames.size) return [];

  const table = type === "stock" ? "security_daily_views" : "theme_daily_views";
  const nested =
    type === "stock"
      ? "security_entities(security_key, display_name)"
      : "theme_entities(theme_key, display_name)";
  const { data, error } = await admin
    .from(table)
    .select(`date_key, mention_count, author_views_json, ${nested}`)
    .order("date_key", { ascending: false })
    .limit(500);
  assertNoError(error);

  const grouped = new Map<string, EntityListItem>();
  const authorSets = new Map<string, Set<string>>();
  for (const row of data || []) {
    const entity = type === "stock" ? (row as any).security_entities : (row as any).theme_entities;
    const key = String(type === "stock" ? entity?.security_key : entity?.theme_key);
    if (!key || key === "undefined") continue;
    const authorViews = asArray<any>((row as any).author_views_json).filter((view) =>
      usernames.has(String(view.account_name || "").toLowerCase()),
    );
    if (!authorViews.length) continue;
    const current =
      grouped.get(key) ||
      ({
        key,
        displayName: String(entity?.display_name || key),
        latestDate: null,
        mentionCount: 0,
        authorCount: 0,
      } satisfies EntityListItem);
    current.latestDate = current.latestDate && current.latestDate > String((row as any).date_key)
      ? current.latestDate
      : String((row as any).date_key);
    current.mentionCount += authorViews.length;
    const authors = authorSets.get(key) || new Set<string>();
    authorViews.forEach((view) => authors.add(String(view.account_name || "")));
    authorSets.set(key, authors);
    current.authorCount = authors.size;
    grouped.set(key, current);
  }
  return Array.from(grouped.values()).sort((left, right) => {
    const dateCompare = String(right.latestDate || "").localeCompare(String(left.latestDate || ""));
    return dateCompare || right.mentionCount - left.mentionCount;
  });
}

export async function listAdminDashboard() {
  const admin = getSupabaseAdmin();
  const [requests, accounts, jobs] = await Promise.all([
    admin
      .from("account_requests")
      .select("id, raw_input, normalized_username, created_at, requester_id, x_accounts(id, username, display_name, profile_url, status)")
      .eq("status", "pending")
      .order("created_at", { ascending: true })
      .limit(50),
    admin.from("x_accounts").select("id, status").eq("status", "approved"),
    admin
      .from("crawl_jobs")
      .select("id, kind, status, summary, error_text, created_at, finished_at")
      .order("created_at", { ascending: false })
      .limit(20),
  ]);
  assertNoError(requests.error);
  assertNoError(accounts.error);
  assertNoError(jobs.error);

  const requesterIds = Array.from(new Set((requests.data || []).map((item: any) => String(item.requester_id))));
  const { data: profiles, error: profileError } = requesterIds.length
    ? await admin.from("profiles").select("id, email").in("id", requesterIds)
    : { data: [], error: null };
  assertNoError(profileError);
  const profileMap = new Map((profiles || []).map((item: any) => [String(item.id), String(item.email)]));

  return {
    approvedCount: accounts.data?.length || 0,
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
  };
}

export async function approveRequest(adminProfile: UserProfile, requestId: string) {
  const admin = getSupabaseAdmin();
  const { data: request, error } = await admin
    .from("account_requests")
    .select("id, account_id")
    .eq("id", requestId)
    .maybeSingle();
  assertNoError(error);
  if (!request) throw new Error("Request not found.");

  const { count, error: countError } = await admin
    .from("x_accounts")
    .select("id", { count: "exact", head: true })
    .eq("status", "approved");
  assertNoError(countError);
  if ((count || 0) >= 100) throw new Error("Approved X account limit reached.");

  const now = new Date().toISOString();
  const { error: accountError } = await admin
    .from("x_accounts")
    .update({
      status: "approved",
      approved_by: adminProfile.id,
      approved_at: now,
      rejected_at: null,
      disabled_at: null,
    })
    .eq("id", (request as any).account_id);
  assertNoError(accountError);

  const { data: requesters, error: requesterError } = await admin
    .from("account_requests")
    .select("requester_id")
    .eq("account_id", (request as any).account_id)
    .eq("status", "pending");
  assertNoError(requesterError);

  const { error: requestUpdateError } = await admin
    .from("account_requests")
    .update({
      status: "approved",
      reviewed_by: adminProfile.id,
      reviewed_at: now,
    })
    .eq("account_id", (request as any).account_id)
    .eq("status", "pending");
  assertNoError(requestUpdateError);

  const subscriptionRows = (requesters || []).map((item: any) => ({
    user_id: item.requester_id,
    account_id: (request as any).account_id,
  }));
  if (subscriptionRows.length) {
    const { error: subscriptionError } = await admin
      .from("user_subscriptions")
      .upsert(subscriptionRows, { onConflict: "user_id,account_id" });
    assertNoError(subscriptionError);
  }

  const { error: jobError } = await admin.from("crawl_jobs").upsert(
    {
      kind: "initial_backfill",
      status: "pending",
      account_id: (request as any).account_id,
      requested_by: adminProfile.id,
      dedupe_key: `initial_backfill:${(request as any).account_id}`,
      metadata_json: { window_days: 30, target_count: 30 },
    },
    { onConflict: "dedupe_key" },
  );
  assertNoError(jobError);
}

export async function rejectRequest(adminProfile: UserProfile, requestId: string) {
  const admin = getSupabaseAdmin();
  const { data: request, error } = await admin
    .from("account_requests")
    .select("id, account_id")
    .eq("id", requestId)
    .maybeSingle();
  assertNoError(error);
  if (!request) throw new Error("Request not found.");
  const now = new Date().toISOString();
  await admin
    .from("account_requests")
    .update({ status: "rejected", reviewed_by: adminProfile.id, reviewed_at: now })
    .eq("id", requestId);
  await admin
    .from("x_accounts")
    .update({ status: "rejected", rejected_at: now })
    .eq("id", (request as any).account_id)
    .eq("status", "pending");
}

export async function disableAccount(accountId: string) {
  const { error } = await getSupabaseAdmin()
    .from("x_accounts")
    .update({ status: "disabled", disabled_at: new Date().toISOString() })
    .eq("id", accountId);
  assertNoError(error);
}

export async function enqueueManualCrawl(profile: UserProfile) {
  const { error } = await getSupabaseAdmin().from("crawl_jobs").insert({
    kind: "manual_crawl",
    status: "pending",
    requested_by: profile.id,
    metadata_json: { source: "admin-ui" },
  });
  assertNoError(error);
}
