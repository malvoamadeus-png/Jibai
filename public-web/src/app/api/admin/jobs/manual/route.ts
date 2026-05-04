import { NextResponse } from "next/server";

import { apiError } from "@/lib/api";
import { requireAdminProfile } from "@/lib/auth";
import { enqueueManualCrawl } from "@/lib/data";

export async function POST() {
  try {
    const profile = await requireAdminProfile();
    await enqueueManualCrawl(profile);
    return NextResponse.json({ ok: true }, { status: 202 });
  } catch (error) {
    return apiError(error);
  }
}
