import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

import type { ViewDirection, ViewEntityType, ViewJudgmentType, ViewSignalType, ViewStance } from "@/lib/types";

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

function directionFromStance(stance: ViewStance): ViewDirection {
  if (stance === "strong_bullish" || stance === "bullish") return "positive";
  if (stance === "strong_bearish" || stance === "bearish") return "negative";
  if (stance === "neutral") return "neutral";
  if (stance === "mixed") return "mixed";
  return "unknown";
}

export function directionLabel(direction: ViewDirection) {
  const mapping: Record<ViewDirection, string> = {
    positive: "正向",
    negative: "负向",
    neutral: "中性",
    mixed: "多空混合",
    unknown: "方向不明",
  };
  return mapping[direction];
}

export function judgmentTypeLabel(judgmentType: ViewJudgmentType) {
  const mapping: Record<ViewJudgmentType, string> = {
    direct: "明确判断",
    implied: "隐含判断",
    factual_only: "事实陈述",
    quoted: "转述观点",
    mention_only: "仅提及",
    unknown: "判断不明",
  };
  return mapping[judgmentType];
}

export function signalTypeLabel(signalType: ViewSignalType) {
  const mapping: Record<ViewSignalType, string> = {
    explicit_stance: "明确表态",
    logic_based: "逻辑判断",
    unknown: "判断不明",
  };
  return mapping[signalType];
}

type ViewSignal = {
  stance: ViewStance;
  direction?: ViewDirection;
  signalType?: ViewSignalType;
  signal_type?: ViewSignalType;
  judgmentType?: ViewJudgmentType;
  judgment_type?: ViewJudgmentType;
};

export function viewSignalLabel(view: ViewSignal) {
  const signalType = view.signalType ?? view.signal_type ?? "unknown";
  const direction = view.direction ?? directionFromStance(view.stance);
  if (signalType !== "unknown") {
    return `${directionLabel(direction)} · ${signalTypeLabel(signalType)}`;
  }
  const judgmentType = view.judgmentType ?? view.judgment_type ?? "unknown";
  if (judgmentType === "mention_only") {
    return "仅提及";
  }
  if (direction === "unknown" && judgmentType === "unknown") {
    return stanceLabel(view.stance);
  }
  return `${directionLabel(direction)} · ${judgmentTypeLabel(judgmentType)}`;
}

export function viewSignalVariant(view: ViewSignal) {
  const direction = view.direction ?? directionFromStance(view.stance);
  if (direction === "positive") return "positive" as const;
  if (direction === "negative") return "danger" as const;
  if (direction === "mixed") return "warm" as const;
  return "neutral" as const;
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
