import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { getControlPanelData, startManualRun } from "@/lib/control";

const runRequestSchema = z.object({
  target: z.enum(["enabled", "xiaohongshu", "x"]).default("enabled"),
});

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  try {
    const rawBody = await request.text();
    const payload = rawBody ? JSON.parse(rawBody) : {};
    const parsed = runRequestSchema.parse(payload);
    const result = startManualRun(parsed.target);
    return NextResponse.json(
      {
        accepted: result.accepted,
        data: getControlPanelData(),
      },
      { status: result.accepted ? 202 : 409 },
    );
  } catch (error) {
    return NextResponse.json(
      {
        message: error instanceof Error ? error.message : "触发运行失败",
      },
      { status: 500 },
    );
  }
}
