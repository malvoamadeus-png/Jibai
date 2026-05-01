import "server-only";

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

import { z } from "zod";

import { getServerEnv } from "@/lib/server-env";
import type { AiProvider, AiSavePayload, AiSettings } from "@/lib/types";

const DEFAULT_OPENAI_MODEL = "gpt-5.4";
const DEFAULT_OPENAI_FALLBACK_MODELS = ["gpt-4.1"];

const aiProviderSchema = z.enum(["openai-compatible", "anthropic"]);

const aiSettingsSchema = z
  .object({
    provider: aiProviderSchema,
    model: z.string().trim().min(1, "AI model 不能为空"),
    fallbackModels: z.array(z.string().trim().min(1)).default([]),
    reasoningEffort: z.string().trim().min(1).nullable(),
    baseUrl: z.string().trim().url("Base URL 必须是完整链接").nullable(),
    hasApiKey: z.boolean(),
  })
  .superRefine(() => {});

export const aiSaveSchema = z
  .object({
    provider: aiProviderSchema,
    model: z.string().trim().min(1, "AI model 不能为空"),
    fallbackModels: z.array(z.string().trim().min(1)).default([]),
    reasoningEffort: z.string().trim().nullable(),
    baseUrl: z.string().trim().nullable(),
    apiKey: z.string().default(""),
  })
  .superRefine((value, ctx) => {
    const normalizedBaseUrl = normalizeOptionalText(value.baseUrl);
    if (normalizedBaseUrl) {
      try {
        new URL(normalizedBaseUrl);
      } catch {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "Base URL 必须是完整链接",
          path: ["baseUrl"],
        });
      }
    }
  });

function readJsonFile(filePath: string) {
  if (!existsSync(filePath)) {
    return {};
  }
  try {
    const raw = readFileSync(filePath, "utf-8").replace(/^\uFEFF/, "");
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : {};
  } catch {
    return {};
  }
}

function normalizeOptionalText(value: unknown) {
  const text = String(value ?? "").trim();
  return text ? text : null;
}

function splitModelList(value: unknown) {
  if (Array.isArray(value)) {
    return dedupeStrings(value.map((item) => String(item)));
  }
  const raw = normalizeOptionalText(value);
  if (!raw) {
    return [];
  }
  return dedupeStrings(raw.split(/[,\n]/));
}

function dedupeStrings(values: string[]) {
  const deduped: string[] = [];
  for (const value of values) {
    const trimmed = value.trim();
    if (trimmed && !deduped.includes(trimmed)) {
      deduped.push(trimmed);
    }
  }
  return deduped;
}

function normalizeProvider(value: unknown): AiProvider | null {
  const raw = String(value ?? "").trim().toLowerCase();
  if (!raw) {
    return null;
  }
  if (["openai", "openai-compatible", "openai_compatible"].includes(raw)) {
    return "openai-compatible";
  }
  if (["anthropic", "claude"].includes(raw)) {
    return "anthropic";
  }
  return null;
}

function pickFirst(...values: Array<unknown>) {
  for (const value of values) {
    const normalized = normalizeOptionalText(value);
    if (normalized) {
      return normalized;
    }
  }
  return null;
}

function resolveProvider(localConfig: Record<string, unknown>): AiProvider {
  return (
    normalizeProvider(localConfig.provider) ??
    normalizeProvider(getServerEnv("AI_PROVIDER")) ??
    (pickFirst(getServerEnv("ANTHROPIC_API_KEY")) ? "anthropic" : "openai-compatible")
  );
}

function resolveApiKey(localConfig: Record<string, unknown>, provider: AiProvider) {
  if (provider === "anthropic") {
    return pickFirst(localConfig.api_key, getServerEnv("AI_API_KEY"), getServerEnv("ANTHROPIC_API_KEY"));
  }
  return pickFirst(
    localConfig.api_key,
    getServerEnv("AI_API_KEY"),
    getServerEnv("OPENAI_API_KEY"),
    getServerEnv("GPT_API_KEY"),
  );
}

function readEffectiveSettings(localConfig: Record<string, unknown>) {
  const provider = resolveProvider(localConfig);

  if (provider === "anthropic") {
    return {
      provider,
      model:
        pickFirst(
          localConfig.model,
          getServerEnv("AI_MODEL"),
          getServerEnv("ANTHROPIC_MODEL"),
          getServerEnv("ANTHROPIC_MODEL_NAME"),
        ) ?? DEFAULT_OPENAI_MODEL,
      fallbackModels: splitModelList(
        localConfig.fallback_models ??
          getServerEnv("AI_FALLBACK_MODELS") ??
          getServerEnv("ANTHROPIC_FALLBACK_MODELS"),
      ),
      reasoningEffort: pickFirst(
        localConfig.reasoning_effort,
        getServerEnv("AI_REASONING_EFFORT"),
      ),
      baseUrl: null,
      apiKey: resolveApiKey(localConfig, provider),
    };
  }

  return {
    provider,
    model:
      pickFirst(
        localConfig.model,
        getServerEnv("AI_MODEL"),
        getServerEnv("OPENAI_MODEL_NAME"),
        getServerEnv("OPENAI_RESEARCH_MODEL"),
        getServerEnv("GPT_SUMMARY_MODEL"),
      ) ?? DEFAULT_OPENAI_MODEL,
    fallbackModels: (() => {
      const values = splitModelList(
        localConfig.fallback_models ??
          getServerEnv("AI_FALLBACK_MODELS") ??
          getServerEnv("OPENAI_FALLBACK_MODELS"),
      );
      return values.length > 0 ? values : [...DEFAULT_OPENAI_FALLBACK_MODELS];
    })(),
    reasoningEffort: pickFirst(
      localConfig.reasoning_effort,
      getServerEnv("AI_REASONING_EFFORT"),
      getServerEnv("OPENAI_REASONING_EFFORT"),
      getServerEnv("GPT_REASONING_EFFORT"),
    ),
    baseUrl:
      pickFirst(
        localConfig.base_url,
        getServerEnv("AI_BASE_URL"),
        getServerEnv("OPENAI_BASE_URL"),
        getServerEnv("GPT_BASE_URL"),
      ) ?? null,
    apiKey: resolveApiKey(localConfig, provider),
  };
}

export function readAiSettings(filePath: string): AiSettings {
  const localConfig = readJsonFile(filePath);
  const resolved = readEffectiveSettings(localConfig);

  return aiSettingsSchema.parse({
    provider: resolved.provider,
    model: resolved.model,
    fallbackModels: resolved.fallbackModels,
    reasoningEffort: normalizeOptionalText(resolved.reasoningEffort),
    baseUrl:
      resolved.provider === "openai-compatible"
        ? normalizeOptionalText(resolved.baseUrl)
        : null,
    hasApiKey: Boolean(resolved.apiKey),
  });
}

export function writeAiSettings(filePath: string, payload: AiSavePayload) {
  const parsed = aiSaveSchema.parse(payload);
  const localConfig = readJsonFile(filePath);
  const currentSettings = readEffectiveSettings(localConfig);
  const currentKey = currentSettings.apiKey;
  const currentBaseUrl = normalizeOptionalText(currentSettings.baseUrl);
  const nextKey = normalizeOptionalText(parsed.apiKey) ?? currentKey;
  const nextBaseUrl =
    parsed.provider === "openai-compatible"
      ? normalizeOptionalText(parsed.baseUrl) ?? currentBaseUrl
      : null;

  if (parsed.provider === "openai-compatible" && !nextBaseUrl) {
    throw new Error("OpenAI-compatible 模式必须提供 Base URL");
  }

  const normalizedPayload: Record<string, unknown> = {
    provider: parsed.provider,
    model: parsed.model.trim(),
    fallback_models: dedupeStrings(parsed.fallbackModels),
    reasoning_effort: normalizeOptionalText(parsed.reasoningEffort),
  };

  if (parsed.provider === "openai-compatible") {
    normalizedPayload.base_url = nextBaseUrl;
  }
  if (nextKey) {
    normalizedPayload.api_key = nextKey;
  }

  mkdirSync(path.dirname(filePath), { recursive: true });
  writeFileSync(filePath, `${JSON.stringify(normalizedPayload, null, 2)}\n`, "utf-8");
}
