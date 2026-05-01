import { z } from "zod";

export const timelineNoteSchema = z.object({
  note_id: z.string(),
  url: z.string(),
  title: z.string().default(""),
  publish_time: z.string().nullable().default(null),
});

const stanceSchema = z.enum([
  "strong_bullish",
  "bullish",
  "neutral",
  "bearish",
  "strong_bearish",
  "mixed",
  "mention_only",
  "unknown",
]);
const directionSchema = z
  .enum(["positive", "negative", "neutral", "mixed", "unknown"])
  .default("unknown");
const judgmentTypeSchema = z
  .enum(["direct", "implied", "factual_only", "quoted", "mention_only", "unknown"])
  .default("unknown");
const convictionSchema = z.enum(["strong", "medium", "weak", "none", "unknown"]).default("unknown");
const evidenceTypeSchema = z
  .enum([
    "price_action",
    "earnings",
    "guidance",
    "management_commentary",
    "valuation",
    "policy",
    "rumor",
    "position",
    "capital_flow",
    "technical",
    "macro",
    "other",
    "unknown",
  ])
  .default("unknown");

export const authorDayViewpointSchema = z.object({
  entityType: z.enum(["stock", "theme", "macro", "other"]),
  entityKey: z.string(),
  entityName: z.string(),
  stance: stanceSchema,
  direction: directionSchema,
  judgmentType: judgmentTypeSchema,
  conviction: convictionSchema,
  evidenceType: evidenceTypeSchema,
  logic: z.string().default(""),
  evidence: z.array(z.string()).default([]),
  noteIds: z.array(z.string()).default([]),
  noteUrls: z.array(z.string()).default([]),
  timeHorizons: z.array(z.string()).default([]),
});

export const entityAuthorViewSchema = z.object({
  platform: z.string().default(""),
  account_name: z.string(),
  author_nickname: z.string().default(""),
  stance: stanceSchema,
  direction: directionSchema,
  judgment_type: judgmentTypeSchema,
  conviction: convictionSchema,
  evidence_type: evidenceTypeSchema,
  logic: z.string().default(""),
  note_ids: z.array(z.string()).default([]),
  note_urls: z.array(z.string()).default([]),
  evidence: z.array(z.string()).default([]),
  time_horizons: z.array(z.string()).default([]),
});

export const authorListItemSchema = z.object({
  platform: z.string(),
  accountKey: z.string(),
  accountName: z.string(),
  authorNickname: z.string(),
  profileUrl: z.string(),
  latestDate: z.string().nullable(),
  latestStatus: z.string().nullable(),
  totalDays: z.number().int(),
  totalNotes: z.number().int(),
  updatedAt: z.string().nullable(),
});

export const stockListItemSchema = z.object({
  securityKey: z.string(),
  displayName: z.string(),
  ticker: z.string().nullable(),
  market: z.string().nullable(),
  latestDate: z.string().nullable(),
  mentionDays: z.number().int(),
  totalMentions: z.number().int(),
  updatedAt: z.string().nullable(),
});

export const themeListItemSchema = z.object({
  themeKey: z.string(),
  displayName: z.string(),
  latestDate: z.string().nullable(),
  mentionDays: z.number().int(),
  totalMentions: z.number().int(),
  updatedAt: z.string().nullable(),
});

export const authorTimelineDaySchema = z.object({
  date: z.string(),
  status: z.enum(["has_update_today", "no_update_today", "crawl_failed"]),
  noteCountToday: z.number().int(),
  summaryText: z.string(),
  noteIds: z.array(z.string()),
  notes: z.array(timelineNoteSchema),
  viewpoints: z.array(authorDayViewpointSchema),
  mentionedStocks: z.array(z.string()),
  mentionedThemes: z.array(z.string()),
  updatedAt: z.string(),
});

export const stockTimelineDaySchema = z.object({
  date: z.string(),
  mentionCount: z.number().int(),
  authorViews: z.array(entityAuthorViewSchema),
  updatedAt: z.string(),
});

export const themeTimelineDaySchema = z.object({
  date: z.string(),
  mentionCount: z.number().int(),
  authorViews: z.array(entityAuthorViewSchema),
  updatedAt: z.string(),
});
