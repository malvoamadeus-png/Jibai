import { NextResponse } from "next/server";

import { getSiteUrl } from "@/lib/env";
import { createServerSupabaseClient } from "@/lib/supabase/server";

export async function POST() {
  const supabase = await createServerSupabaseClient();
  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: "google",
    options: {
      redirectTo: `${getSiteUrl()}/api/auth/callback`,
    },
  });
  if (error || !data.url) {
    return NextResponse.json({ message: error?.message || "Unable to start Google login." }, { status: 500 });
  }
  return NextResponse.redirect(data.url, 303);
}
