import { NextRequest, NextResponse } from "next/server";

import { getSiteUrl } from "@/lib/env";
import { createServerSupabaseClient } from "@/lib/supabase/server";

export async function GET(request: NextRequest) {
  const url = new URL(request.url);
  const code = url.searchParams.get("code");
  if (code) {
    const supabase = await createServerSupabaseClient();
    await supabase.auth.exchangeCodeForSession(code);
  }
  return NextResponse.redirect(getSiteUrl());
}
