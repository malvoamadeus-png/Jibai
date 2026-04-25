import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

import type { ViewEntityType, ViewStance } from "@/lib/types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function parsePositiveInt(
  raw: string | undefined,
  fallback: number,
  min = 1,
  max = 100,
) {
  if (!raw) return fallback;
  const value = Number.parseInt(raw, 10);
  if (Number.isNaN(value)) return fallback;
  return Math.max(min, Math.min(max, value));
}

export function formatCount(value: number) {
  return new Intl.NumberFormat("zh-CN").format(value);
}

export function formatDate(value: string | null | undefined) {
  if (!value) return "暂无";
  return value.slice(0, 10);
}

export function stripTime(value: string | null | undefined) {
  if (!value) return "暂无时间";
  return value.replace("T", " ").replace("+08:00", "");
}

export function makeAccountKey(platform: string, accountName: string) {
  return `${platform}::${accountName}`;
}

export function platformLabel(platform: string | null | undefined) {
  if (!platform) return "";

  const normalized = platform.trim().toLowerCase();
  if (normalized === "xiaohongshu") return "小红书";
  if (normalized === "x") return "X";

  return platform;
}

export function stanceLabel(stance: ViewStance) {
  const mapping: Record<ViewStance, string> = {
    strong_bullish: "强烈看多",
    bullish: "看多",
    neutral: "中性",
    bearish: "看空",
    strong_bearish: "强烈看空",
    mixed: "分歧",
    mention_only: "仅提及",
    unknown: "不明确",
  };
  return mapping[stance];
}

export function entityTypeLabel(entityType: ViewEntityType) {
  const mapping: Record<ViewEntityType, string> = {
    stock: "股票",
    theme: "Theme",
    macro: "宏观",
    other: "其他",
  };
  return mapping[entityType];
}
