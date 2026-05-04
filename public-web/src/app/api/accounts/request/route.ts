import { NextRequest, NextResponse } from "next/server";

import { apiError } from "@/lib/api";
import { requireProfile } from "@/lib/auth";
import { submitAccount } from "@/lib/data";
import { submitAccountSchema } from "@/lib/x";

export async function POST(request: NextRequest) {
  try {
    const profile = await requireProfile();
    const payload = submitAccountSchema.parse(await request.json());
    await submitAccount(profile, payload.account);
    return NextResponse.json({ ok: true }, { status: 202 });
  } catch (error) {
    return apiError(error);
  }
}
