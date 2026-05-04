import { NextRequest, NextResponse } from "next/server";

import { apiError } from "@/lib/api";
import { requireAdminProfile } from "@/lib/auth";
import { disableAccount } from "@/lib/data";

type Params = { params: Promise<{ accountId: string }> };

export async function POST(_request: NextRequest, { params }: Params) {
  try {
    await requireAdminProfile();
    const { accountId } = await params;
    await disableAccount(accountId);
    return NextResponse.json({ ok: true });
  } catch (error) {
    return apiError(error);
  }
}
