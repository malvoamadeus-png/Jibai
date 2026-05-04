import { NextResponse } from "next/server";

export function apiError(error: unknown) {
  if (error && typeof error === "object" && "issues" in error) {
    return NextResponse.json({ message: "Invalid request payload." }, { status: 400 });
  }
  const status =
    error && typeof error === "object" && "status" in error
      ? Number((error as { status: unknown }).status)
      : 500;
  const message = error instanceof Error ? error.message : "Request failed.";
  return NextResponse.json({ message }, { status: Number.isFinite(status) ? status : 500 });
}
