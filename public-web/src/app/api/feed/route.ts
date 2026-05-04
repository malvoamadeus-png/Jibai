import { NextResponse } from "next/server";

import { apiError } from "@/lib/api";
import { requireProfile } from "@/lib/auth";
import { listFeed } from "@/lib/data";

export async function GET() {
  try {
    const profile = await requireProfile();
    return NextResponse.json({ feed: await listFeed(profile) });
  } catch (error) {
    return apiError(error);
  }
}
