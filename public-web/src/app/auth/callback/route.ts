import { NextResponse } from "next/server";

import { createSupabaseServerClient } from "@/lib/supabase/server";

function safeNextPath(value: string | null) {
  if (!value || !value.startsWith("/") || value.startsWith("//")) {
    return "/";
  }
  return value;
}

function redirectOrigin(request: Request, fallbackOrigin: string) {
  if (process.env.NODE_ENV === "development") {
    return fallbackOrigin;
  }

  const forwardedHost = request.headers.get("x-forwarded-host");
  if (!forwardedHost) {
    return fallbackOrigin;
  }

  const forwardedProto = request.headers.get("x-forwarded-proto") || "https";
  return `${forwardedProto}://${forwardedHost}`;
}

export async function GET(request: Request) {
  const requestUrl = new URL(request.url);
  const code = requestUrl.searchParams.get("code");
  const next = safeNextPath(requestUrl.searchParams.get("next"));
  const origin = redirectOrigin(request, requestUrl.origin);

  if (code) {
    const supabase = await createSupabaseServerClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);

    if (!error) {
      return NextResponse.redirect(`${origin}${next}`);
    }
  }

  return NextResponse.redirect(`${origin}/auth/auth-code-error`);
}
