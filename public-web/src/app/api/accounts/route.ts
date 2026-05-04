import { NextRequest, NextResponse } from "next/server";

import { apiError } from "@/lib/api";
import { requireProfile } from "@/lib/auth";
import { listAccounts } from "@/lib/data";

export async function GET(request: NextRequest) {
  try {
    const profile = await requireProfile();
    const query = request.nextUrl.searchParams.get("q") || "";
    return NextResponse.json({ accounts: await listAccounts(profile, query) });
  } catch (error) {
    return apiError(error);
  }
}
