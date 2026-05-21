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

export function getGmgnLabelApiUrl() {
  const value = process.env.NEXT_PUBLIC_GMGN_LABEL_API_URL;
  if (!value) throw new Error("Missing NEXT_PUBLIC_GMGN_LABEL_API_URL");
  return value.replace(/\/+$/, "");
}
