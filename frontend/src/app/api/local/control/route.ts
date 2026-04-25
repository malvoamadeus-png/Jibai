import { NextRequest, NextResponse } from "next/server";
import { ZodError } from "zod";

import { getControlPanelData, saveControlSettings } from "@/lib/control";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  return NextResponse.json(getControlPanelData());
}

export async function PUT(request: NextRequest) {
  try {
    const payload = await request.json();
    return NextResponse.json(saveControlSettings(payload));
  } catch (error) {
    if (error instanceof ZodError) {
      return NextResponse.json(
        {
          message: "配置校验失败",
          issues: error.issues,
        },
        { status: 400 },
      );
    }
    return NextResponse.json(
      {
        message: error instanceof Error ? error.message : "保存配置失败",
      },
      { status: 500 },
    );
  }
}
