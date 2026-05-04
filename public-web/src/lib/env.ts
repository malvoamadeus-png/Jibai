export function getSupabaseUrl() {
  const value = process.env.NEXT_PUBLIC_SUPABASE_URL;
  if (!value) throw new Error("Missing NEXT_PUBLIC_SUPABASE_URL");
  return value;
}

export function getSupabaseAnonKey() {
  const value = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!value) throw new Error("Missing NEXT_PUBLIC_SUPABASE_ANON_KEY");
  return value;
}

export function getSupabaseServiceRoleKey() {
  const value = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!value) throw new Error("Missing SUPABASE_SERVICE_ROLE_KEY");
  return value;
}

export function getSiteUrl() {
  return process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000";
}

export function getAdminEmails() {
  return new Set(
    (process.env.ADMIN_EMAILS || "")
      .split(",")
      .map((item) => item.trim().toLowerCase())
      .filter(Boolean),
  );
}
