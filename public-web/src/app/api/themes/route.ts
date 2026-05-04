import { NextResponse } from "next/server";

import { apiError } from "@/lib/api";
import { requireProfile } from "@/lib/auth";
import { listEntities } from "@/lib/data";

export async function GET() {
  try {
    const profile = await requireProfile();
    return NextResponse.json({ themes: await listEntities(profile, "theme") });
  } catch (error) {
    return apiError(error);
  }
}
