import "server-only";

import { getAdminEmails } from "@/lib/env";
import { getSupabaseAdmin } from "@/lib/supabase/admin";
import { createServerSupabaseClient } from "@/lib/supabase/server";
import type { UserProfile } from "@/lib/types";

export class AuthError extends Error {
  status = 401;
}

export class AdminError extends Error {
  status = 403;
}

export async function getCurrentProfile(): Promise<UserProfile | null> {
  const supabase = await createServerSupabaseClient();
  const { data, error } = await supabase.auth.getUser();
  if (error || !data.user?.email) return null;

  const user = data.user;
  const email = data.user.email.toLowerCase();
  const isAdmin = getAdminEmails().has(email);
  const displayName =
    typeof user.user_metadata?.full_name === "string"
      ? user.user_metadata.full_name
      : email.split("@")[0];
  const avatarUrl =
    typeof user.user_metadata?.avatar_url === "string" ? user.user_metadata.avatar_url : "";

  const admin = getSupabaseAdmin();
  await admin.from("profiles").upsert(
    {
      id: user.id,
      email,
      display_name: displayName,
      avatar_url: avatarUrl,
      is_admin: isAdmin,
      updated_at: new Date().toISOString(),
    },
    { onConflict: "id" },
  );

  return {
    id: user.id,
    email,
    displayName,
    avatarUrl,
    isAdmin,
  };
}

export async function requireProfile() {
  const profile = await getCurrentProfile();
  if (!profile) throw new AuthError("Authentication required.");
  return profile;
}

export async function requireAdminProfile() {
  const profile = await requireProfile();
  if (!profile.isAdmin) throw new AdminError("Admin access required.");
  return profile;
}
