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

export function getPublicApiBaseUrl() {
  const explicitValue = process.env.NEXT_PUBLIC_PUBLIC_API_BASE_URL;
  if (explicitValue) return explicitValue.replace(/\/$/, "");

  if (process.env.NODE_ENV === "production") {
    return "https://api.47.76.243.147.sslip.io";
  }

  throw new Error("Missing NEXT_PUBLIC_PUBLIC_API_BASE_URL");
}
