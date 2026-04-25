import { NextRequest, NextResponse } from "next/server";

import { getStockDetail } from "@/lib/queries";
import { parsePositiveInt } from "@/lib/utils";

export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ securityKey: string }> },
) {
  const { securityKey } = await context.params;
  const searchParams = request.nextUrl.searchParams;
  const page = parsePositiveInt(searchParams.get("page") ?? undefined, 1, 1, 9999);
  const pageSize = parsePositiveInt(searchParams.get("pageSize") ?? undefined, 20, 1, 100);
  const data = getStockDetail({
    securityKey: decodeURIComponent(securityKey),
    page,
    pageSize,
  });
  return NextResponse.json(data, { status: data ? 200 : 404 });
}
