import { NextRequest, NextResponse } from "next/server";

import { apiError } from "@/lib/api";
import { requireAdminProfile } from "@/lib/auth";
import { approveRequest } from "@/lib/data";

type Params = { params: Promise<{ requestId: string }> };

export async function POST(_request: NextRequest, { params }: Params) {
  try {
    const profile = await requireAdminProfile();
    const { requestId } = await params;
    await approveRequest(profile, requestId);
    return NextResponse.json({ ok: true });
  } catch (error) {
    return apiError(error);
  }
}
