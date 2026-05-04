import { NextRequest, NextResponse } from "next/server";

import { apiError } from "@/lib/api";
import { requireProfile } from "@/lib/auth";
import { setSubscription } from "@/lib/data";

type Params = { params: Promise<{ accountId: string }> };

export async function POST(_request: NextRequest, { params }: Params) {
  try {
    const profile = await requireProfile();
    const { accountId } = await params;
    await setSubscription(profile, accountId, true);
    return NextResponse.json({ ok: true });
  } catch (error) {
    return apiError(error);
  }
}

export async function DELETE(_request: NextRequest, { params }: Params) {
  try {
    const profile = await requireProfile();
    const { accountId } = await params;
    await setSubscription(profile, accountId, false);
    return NextResponse.json({ ok: true });
  } catch (error) {
    return apiError(error);
  }
}
