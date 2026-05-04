import { NextResponse } from "next/server";

import { apiError } from "@/lib/api";
import { getCurrentProfile } from "@/lib/auth";

export async function GET() {
  try {
    return NextResponse.json({ profile: await getCurrentProfile() });
  } catch (error) {
    return apiError(error);
  }
}
