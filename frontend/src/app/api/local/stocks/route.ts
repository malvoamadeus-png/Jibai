import { NextRequest, NextResponse } from "next/server";

import { getStocksPage } from "@/lib/queries";
import { parsePositiveInt } from "@/lib/utils";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const page = parsePositiveInt(searchParams.get("page") ?? undefined, 1, 1, 9999);
  const pageSize = parsePositiveInt(searchParams.get("pageSize") ?? undefined, 20, 1, 100);
  const q = searchParams.get("q") ?? "";
  return NextResponse.json(getStocksPage({ page, pageSize, q }));
}
