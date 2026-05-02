import "server-only";

import { spawn } from "node:child_process";
import {
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import path from "node:path";

import type Database from "better-sqlite3";
import { z } from "zod";

import { aiSaveSchema, readAiSettings, writeAiSettings } from "@/lib/ai-settings";
import { getDb } from "@/lib/db";
import { getLocalProjectPaths, toRelativeProjectPath } from "@/lib/local-paths";
import type {
  ControlAccountConfig,
  ControlAccountStatus,
  ControlPanelData,
  ControlStats,
  ManualRunCommandState,
  ManualRunState,
  ManualRunTarget,
  PlatformKey,
  XSettings,
  XiaohongshuSettings,
} from "@/lib/types";

const DEFAULT_XIAOHONGSHU_SCHEDULE_TIMES = ["10:00", "22:00"];
const DEFAULT_X_SCHEDULE_TIMES = ["10:00", "22:00"];
const DEFAULT_ACCOUNT_FETCH_LIMIT = 5;
const MAX_ACCOUNT_FETCH_LIMIT = 20;
const DEFAULT_XHS_SETTINGS: XiaohongshuSettings = {
  enabled: true,
  browserChannel: "chrome",
  headless: false,
  interAccountDelaySec: 5,
  interAccountDelayJitterSec: 3,
  detailDelaySec: 0.8,
  detailFallbackEnabled: true,
  detailFallbackLimitPerAccount: 2,
  excludeOldPosts: true,
  maxPostAgeDays: 5,
  accounts: [],
};
const DEFAULT_X_SETTINGS: XSettings = {
  enabled: true,
  headless: true,
  pageWaitSec: 6,
  interAccountDelaySec: 1.5,
  interAccountDelayJitterSec: 1,
  excludeOldPosts: true,
  maxPostAgeDays: 5,
  nitterInstances: ["nitter.tiekoetter.com", "xcancel.com", "nitter.catsarch.com"],
  accounts: [],
};

const scheduleTimeSchema = z
  .string()
  .trim()
  .regex(/^([01]\d|2[0-3]):([0-5]\d)$/, "时间必须使用 HH:MM 格式");
const scheduleTimesSchema = z.array(scheduleTimeSchema).min(1);

function ensureUrlScheme(value: string) {
  const trimmed = value.trim();
  if (!trimmed || /^[a-z]+:\/\//i.test(trimmed)) {
    return trimmed;
  }
  return `https://${trimmed.replace(/^\/+/, "")}`;
}

const xhsAccountSchema = z.object({
  name: z.string().trim().min(1, "小红书账号名称不能为空"),
  profileUrl: z.preprocess(
    (value) => (typeof value === "string" ? ensureUrlScheme(value) : value),
    z
      .string()
      .trim()
      .url("小红书主页链接格式不正确")
      .refine(
        (value) => value.includes("/user/profile/") && /(?:\?|&)xsec_token=/.test(value),
        "小红书主页链接需要是完整 profile_url，并包含 xsec_token",
      ),
  ),
  limit: z.coerce.number().int().min(1).max(MAX_ACCOUNT_FETCH_LIMIT),
});

const xAccountSchema = z.object({
  name: z.string().trim().min(1, "X 账号名称不能为空"),
  profileUrl: z.preprocess(
    (value) => (typeof value === "string" ? ensureUrlScheme(value) : value),
    z
      .string()
      .trim()
      .url("X 主页链接格式不正确")
      .refine(
        (value) => /^https?:\/\/(www\.)?(x|twitter)\.com\/[^/?#]+\/?$/i.test(value),
        "X 主页链接需要是 x.com 或 twitter.com 的直接用户主页",
      ),
  ),
  limit: z.coerce.number().int().min(1).max(MAX_ACCOUNT_FETCH_LIMIT),
});

const xhsSettingsSchema = z
  .object({
    enabled: z.boolean(),
    browserChannel: z.string().trim().min(1).default("chrome"),
    headless: z.boolean(),
    interAccountDelaySec: z.coerce.number().min(0),
    interAccountDelayJitterSec: z.coerce.number().min(0),
    detailDelaySec: z.coerce.number().min(0),
    detailFallbackEnabled: z.boolean(),
    detailFallbackLimitPerAccount: z.coerce.number().int().min(0).max(5),
    excludeOldPosts: z.boolean(),
    maxPostAgeDays: z.coerce.number().int().min(1).max(30),
    accounts: z.array(xhsAccountSchema),
  })
  .superRefine((value, ctx) => {
    if (value.enabled && value.accounts.length === 0) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "启用小红书后至少需要一个账号",
        path: ["accounts"],
      });
    }
  });

const xSettingsSchema = z
  .object({
    enabled: z.boolean(),
    headless: z.boolean(),
    pageWaitSec: z.coerce.number().min(0),
    interAccountDelaySec: z.coerce.number().min(0),
    interAccountDelayJitterSec: z.coerce.number().min(0),
    excludeOldPosts: z.boolean(),
    maxPostAgeDays: z.coerce.number().int().min(1).max(30),
    nitterInstances: z.array(z.string().trim().min(1)).min(1),
    accounts: z.array(xAccountSchema),
  })
  .superRefine((value, ctx) => {
    if (value.enabled && value.accounts.length === 0) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "启用 X 后至少需要一个账号",
        path: ["accounts"],
      });
    }
  });

const controlSaveSchema = z.object({
  xiaohongshuScheduleTimes: scheduleTimesSchema,
  xScheduleTimes: scheduleTimesSchema,
  xiaohongshu: xhsSettingsSchema,
  x: xSettingsSchema,
  ai: aiSaveSchema,
});

type MonitorBucket = {
  seen_note_ids?: unknown;
  last_run_at?: unknown;
  last_error?: unknown;
};

type MonitorState = {
  accounts?: Record<string, MonitorBucket>;
};

type LatestCrawlRun = {
  status: "success" | "failed";
  runAt: string;
  candidateCount: number;
  newNoteCount: number;
  errorText: string | null;
};

let manualRunState: ManualRunState = {
  status: "idle",
  target: null,
  startedAt: null,
  finishedAt: null,
  currentStage: null,
  summary: "尚未手动运行",
  commands: [],
};
let activeManualRun: Promise<void> | null = null;

function readJsonFile<T>(filePath: string, fallback: T): T {
  if (!existsSync(filePath)) {
    return fallback;
  }
  try {
    const raw = readFileSync(filePath, "utf-8").replace(/^\uFEFF/, "");
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function writeJsonFile(filePath: string, payload: unknown) {
  mkdirSync(path.dirname(filePath), { recursive: true });
  writeFileSync(filePath, `${JSON.stringify(payload, null, 2)}\n`, "utf-8");
}

function normalizeScheduleTimes(values: string[]) {
  const parsed = z.array(scheduleTimeSchema).min(1).parse(values);
  const deduped: string[] = [];
  for (const value of parsed) {
    if (!deduped.includes(value)) {
      deduped.push(value);
    }
  }
  return deduped.sort((left, right) => left.localeCompare(right));
}

function normalizeStringList(values: string[]) {
  const deduped: string[] = [];
  for (const value of values) {
    const trimmed = value.trim();
    if (trimmed && !deduped.includes(trimmed)) {
      deduped.push(trimmed);
    }
  }
  return deduped;
}

function normalizeAccounts(accounts: ControlAccountConfig[]) {
  const deduped: ControlAccountConfig[] = [];
  for (const account of accounts) {
    if (!deduped.some((item) => item.name === account.name)) {
      deduped.push({
        ...account,
        profileUrl: ensureUrlScheme(account.profileUrl),
      });
    }
  }
  return deduped;
}

function toRawAccounts(accounts: unknown) {
  if (!Array.isArray(accounts)) {
    return [];
  }
  return accounts.map((item) => {
    const record = (item ?? {}) as Record<string, unknown>;
    return {
      name: String(record.name ?? ""),
      profileUrl: String(record.profile_url ?? ""),
      limit: Number(record.limit ?? DEFAULT_ACCOUNT_FETCH_LIMIT),
    };
  });
}

function platformLabel(platform: PlatformKey | string) {
  if (platform === "xiaohongshu") return "小红书";
  if (platform === "x") return "X";
  return platform;
}

function humanizeCrawlError(errorText: string | null, platform: PlatformKey | string) {
  if (!errorText) {
    return null;
  }
  const lowered = errorText.toLowerCase();

  if (
    lowered.includes("missing persistent xiaohongshu login") ||
    lowered.includes("saved login state failed validation") ||
    lowered.includes("missing login cookie")
  ) {
    return "登录态已失效，请重新登录后再试。";
  }
  if (
    lowered.includes("security restriction") ||
    lowered.includes("website-login/error") ||
    lowered.includes("300012")
  ) {
    return "触发了平台安全限制，请稍后重试，必要时重新登录。";
  }
  if (lowered.includes("budget exhausted")) {
    return "该账号近期帖子大多需要登录态补抓，当前补抓上限不够。";
  }
  if (lowered.includes("login fallback failed")) {
    return "帖子详情受限，且本次登录态补抓没有成功。";
  }
  if (
    lowered.includes("anonymous detail access restricted") ||
    lowered.includes("xhs_404_-510001")
  ) {
    return "该账号的帖子详情对匿名访问受限，需要依赖登录态补抓。";
  }
  if (lowered.includes("note payload not found in detail page state")) {
    return "详情页返回异常或受限页面，暂时没能解析出正文。";
  }
  if (lowered.includes("x_fetch_failed")) {
    return "没抓到：所有公开 Nitter 镜像主页请求失败。";
  }
  if (lowered.includes("x_runtime_failed")) {
    return "运行环境错误：Playwright Chromium 未安装。";
  }
  if (lowered.includes("x_parse_empty")) {
    return "解析问题：公开 Nitter 页面已返回，但没有解析到可用 tweet。";
  }
  if (lowered.includes("x_other")) {
    return "其他：X 抓取未解析到 tweet，但失败类型不明确。";
  }
  if (
    lowered.includes("could not resolve any real note links from the first screen") ||
    lowered.includes("could not resolve any tweets from public nitter pages")
  ) {
    if (platform === "x") {
      return "解析问题：公开 Nitter 页面没有解析到可用 tweet。";
    }
    return "主页首屏暂时没有解析到可用内容。";
  }
  if (platform === "x" && lowered.includes("nitter")) {
    return "公开镜像当前不稳定，建议稍后重试。";
  }
  return "本次抓取遇到平台限制或页面结构变化，建议稍后重试。";
}

function formatLatestError(
  platform: PlatformKey | string,
  accountName: string,
  errorText: string | null,
) {
  if (!errorText) {
    return null;
  }
  return `${platformLabel(platform)} / ${accountName}: ${errorText}`;
}

function readXhsSettings(filePath: string): XiaohongshuSettings {
  const raw = readJsonFile<Record<string, unknown>>(filePath, {});
  const rawAccounts = toRawAccounts(raw.accounts);
  const enabled = Boolean(
    raw.enabled ?? (rawAccounts.length > 0 ? DEFAULT_XHS_SETTINGS.enabled : false),
  );
  const parsed = xhsSettingsSchema.parse({
    enabled,
    browserChannel: raw.browser_channel ?? DEFAULT_XHS_SETTINGS.browserChannel,
    headless: raw.headless ?? DEFAULT_XHS_SETTINGS.headless,
    interAccountDelaySec:
      raw.inter_account_delay_sec ?? DEFAULT_XHS_SETTINGS.interAccountDelaySec,
    interAccountDelayJitterSec:
      raw.inter_account_delay_jitter_sec ?? DEFAULT_XHS_SETTINGS.interAccountDelayJitterSec,
    detailDelaySec: raw.detail_delay_sec ?? DEFAULT_XHS_SETTINGS.detailDelaySec,
    detailFallbackEnabled:
      raw.detail_fallback_enabled ?? DEFAULT_XHS_SETTINGS.detailFallbackEnabled,
    detailFallbackLimitPerAccount:
      raw.detail_fallback_limit_per_account ??
      DEFAULT_XHS_SETTINGS.detailFallbackLimitPerAccount,
    excludeOldPosts: raw.exclude_old_posts ?? DEFAULT_XHS_SETTINGS.excludeOldPosts,
    maxPostAgeDays: raw.max_post_age_days ?? DEFAULT_XHS_SETTINGS.maxPostAgeDays,
    accounts: rawAccounts,
  });

  return {
    ...parsed,
    accounts: normalizeAccounts(parsed.accounts),
  };
}

function readXSettings(filePath: string): XSettings {
  const raw = readJsonFile<Record<string, unknown>>(filePath, {});
  const rawAccounts = toRawAccounts(raw.accounts);
  const enabled = Boolean(
    raw.enabled ?? (rawAccounts.length > 0 ? DEFAULT_X_SETTINGS.enabled : false),
  );
  const parsed = xSettingsSchema.parse({
    enabled,
    headless: raw.headless ?? DEFAULT_X_SETTINGS.headless,
    pageWaitSec: raw.page_wait_sec ?? DEFAULT_X_SETTINGS.pageWaitSec,
    interAccountDelaySec:
      raw.inter_account_delay_sec ?? DEFAULT_X_SETTINGS.interAccountDelaySec,
    interAccountDelayJitterSec:
      raw.inter_account_delay_jitter_sec ?? DEFAULT_X_SETTINGS.interAccountDelayJitterSec,
    excludeOldPosts: raw.exclude_old_posts ?? DEFAULT_X_SETTINGS.excludeOldPosts,
    maxPostAgeDays: raw.max_post_age_days ?? DEFAULT_X_SETTINGS.maxPostAgeDays,
    nitterInstances: Array.isArray(raw.nitter_instances)
      ? raw.nitter_instances.map((item) => String(item))
      : DEFAULT_X_SETTINGS.nitterInstances,
    accounts: rawAccounts,
  });

  return {
    ...parsed,
    nitterInstances: normalizeStringList(parsed.nitterInstances),
    accounts: normalizeAccounts(parsed.accounts),
  };
}

function readRuntimeScheduleTimes(filePath: string) {
  const raw = readJsonFile<Record<string, unknown>>(filePath, {});
  const legacyScheduleTimes = Array.isArray(raw.schedule_times)
    ? raw.schedule_times.map((item) => String(item))
    : null;
  const xiaohongshuRaw = Array.isArray(raw.xiaohongshu_schedule_times)
    ? raw.xiaohongshu_schedule_times
    : Array.isArray(raw.xhs_schedule_times)
      ? raw.xhs_schedule_times
      : null;
  const xRaw = Array.isArray(raw.x_schedule_times) ? raw.x_schedule_times : null;

  return {
    xiaohongshuScheduleTimes: normalizeScheduleTimes(
      (xiaohongshuRaw ?? legacyScheduleTimes ?? DEFAULT_XIAOHONGSHU_SCHEDULE_TIMES).map(
        (item) => String(item),
      ),
    ),
    xScheduleTimes: normalizeScheduleTimes(
      (xRaw ?? legacyScheduleTimes ?? DEFAULT_X_SCHEDULE_TIMES).map((item) => String(item)),
    ),
  };
}

function readMonitorState(filePath: string): MonitorState {
  return readJsonFile<MonitorState>(filePath, { accounts: {} });
}

function hasPersistentLogin(userDataDir: string) {
  if (!existsSync(userDataDir)) {
    return false;
  }
  try {
    return readdirSync(userDataDir).length > 0;
  } catch {
    return false;
  }
}

function getStatsFromDb(db: Database.Database | null): ControlStats {
  if (!db) {
    return { authorCount: 0, stockCount: 0, themeCount: 0, contentCount: 0 };
  }
  const row = db
    .prepare(
      `
      SELECT
        (SELECT COUNT(*) FROM accounts) AS authorCount,
        (SELECT COUNT(*) FROM security_entities) AS stockCount,
        (SELECT COUNT(*) FROM theme_entities) AS themeCount,
        (SELECT COUNT(*) FROM content_items) AS contentCount
      `,
    )
    .get() as
    | {
        authorCount: number;
        stockCount: number;
        themeCount: number;
        contentCount: number;
      }
    | undefined;
  return (
    row ?? {
      authorCount: 0,
      stockCount: 0,
      themeCount: 0,
      contentCount: 0,
    }
  );
}

function getLastAnalysisRunAt(db: Database.Database | null) {
  if (!db) {
    return null;
  }
  const row = db
    .prepare("SELECT run_at AS runAt FROM analysis_runs ORDER BY run_at DESC, id DESC LIMIT 1")
    .get() as { runAt: string | null } | undefined;
  return row?.runAt ?? null;
}

function getLatestErrorText(
  platforms: Array<{
    platform: PlatformKey;
    enabled: boolean;
    statuses: ControlAccountStatus[];
  }>,
) {
  return getLatestVisibleError(platforms);
}

function getLatestCrawlRun(
  db: Database.Database | null,
  platform: PlatformKey,
  accountName: string,
): LatestCrawlRun | null {
  if (!db) {
    return null;
  }
  const row = db
    .prepare(
      `
      SELECT
        status,
        run_at AS runAt,
        candidate_count AS candidateCount,
        new_note_count AS newNoteCount,
        error_text AS errorText
      FROM crawl_account_runs
      WHERE platform = ? AND account_name = ?
      ORDER BY run_at DESC, id DESC
      LIMIT 1
      `,
    )
    .get(platform, accountName) as LatestCrawlRun | undefined;
  return row ?? null;
}

function countSeenNotes(bucket: MonitorBucket | undefined) {
  return Array.isArray(bucket?.seen_note_ids) ? bucket.seen_note_ids.length : 0;
}

function buildAccountStatuses(
  db: Database.Database | null,
  platform: PlatformKey,
  accounts: ControlAccountConfig[],
  monitorState: MonitorState,
): ControlAccountStatus[] {
  return accounts.map((account) => {
    const bucket = monitorState.accounts?.[account.name];
    const lastRun = getLatestCrawlRun(db, platform, account.name);
    const fallbackLastRunAt =
      typeof bucket?.last_run_at === "string" && bucket.last_run_at.trim()
        ? bucket.last_run_at
        : null;
    const fallbackLastError =
      typeof bucket?.last_error === "string" && bucket.last_error.trim()
        ? bucket.last_error
        : null;
    const rawLastError = lastRun ? (lastRun.errorText ?? null) : fallbackLastError;
    const newNoteCount = lastRun?.newNoteCount ?? null;
    const hasBlockingError = Boolean(rawLastError) && (newNoteCount ?? 0) === 0;
    const lastError = hasBlockingError ? humanizeCrawlError(rawLastError, platform) : null;

    return {
      name: account.name,
      lastStatus: hasBlockingError
        ? "failed"
        : lastRun?.status ??
          (fallbackLastRunAt ? (fallbackLastError ? "failed" : "success") : "idle"),
      lastRunAt: lastRun?.runAt ?? fallbackLastRunAt,
      lastError,
      seenCount: countSeenNotes(bucket),
      candidateCount: lastRun?.candidateCount ?? null,
      newNoteCount,
    };
  });
}

function getLatestVisibleError(
  platforms: Array<{
    platform: PlatformKey;
    enabled: boolean;
    statuses: ControlAccountStatus[];
  }>,
) {
  const latest = platforms
    .flatMap(({ platform, enabled, statuses }) =>
      enabled
        ? statuses
            .filter((item) => item.lastStatus === "failed" && item.lastError)
            .map((item) => ({
              platform,
              accountName: item.name,
              lastRunAt: item.lastRunAt ?? "",
              message: item.lastError as string,
            }))
        : [],
    )
    .sort((left, right) => right.lastRunAt.localeCompare(left.lastRunAt))[0];

  if (!latest) {
    return null;
  }
  return formatLatestError(latest.platform, latest.accountName, latest.message);
}

function truncateOutput(value: string) {
  const trimmed = value.trim();
  if (trimmed.length <= 24000) {
    return trimmed;
  }
  return `${trimmed.slice(-24000)}\n[truncated]`;
}

function extractProgressText(command: ManualRunCommandState) {
  const lines = `${command.stdout}\n${command.stderr}`
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  for (const line of lines.slice().reverse()) {
    const progressMatch = /^(stage|result):\s*(.+)$/i.exec(line);
    if (progressMatch) {
      return progressMatch[2];
    }
  }

  return null;
}

function cloneManualRunState(): ManualRunState {
  return {
    ...manualRunState,
    commands: manualRunState.commands.map((item) => ({ ...item })),
  };
}

function runCommand({
  cwd,
  pythonExecutable,
  label,
  args,
  onUpdate,
}: {
  cwd: string;
  pythonExecutable: string;
  label: string;
  args: string[];
  onUpdate?: (command: ManualRunCommandState) => void;
}): Promise<ManualRunCommandState> {
  const startedAt = Date.now();
  return new Promise((resolve) => {
    const child = spawn(pythonExecutable, args, {
      cwd,
      env: {
        ...process.env,
        PYTHONIOENCODING: process.env.PYTHONIOENCODING || "utf-8",
        PYTHONUNBUFFERED: process.env.PYTHONUNBUFFERED || "1",
      },
      shell: false,
      windowsHide: true,
    });

    let stdout = "";
    let stderr = "";
    const buildState = (exitCode: number | null): ManualRunCommandState => ({
      label,
      command: [pythonExecutable, ...args].join(" "),
      exitCode,
      durationMs: Date.now() - startedAt,
      stdout: truncateOutput(stdout),
      stderr: truncateOutput(stderr),
    });

    onUpdate?.(buildState(null));

    child.stdout?.on("data", (chunk) => {
      stdout += chunk.toString();
      onUpdate?.(buildState(null));
    });
    child.stderr?.on("data", (chunk) => {
      stderr += chunk.toString();
      onUpdate?.(buildState(null));
    });
    child.on("error", (error) => {
      stderr += `${error.message}\n`;
      onUpdate?.(buildState(1));
    });
    child.on("close", (code) => {
      const finalState = buildState(typeof code === "number" ? code : 1);
      onUpdate?.(finalState);
      resolve(finalState);
    });
  });
}

function commandPlanForTarget(target: ManualRunTarget) {
  if (target === "xiaohongshu") {
    return [{ label: "小红书抓取与分析", args: ["backend/src/main.py", "run-once"] }];
  }
  if (target === "x") {
    return [{ label: "X 抓取与分析", args: ["backend/src/main.py", "run-once-x"] }];
  }
  return [
    { label: "小红书抓取与分析", args: ["backend/src/main.py", "run-once"] },
    { label: "X 抓取与分析", args: ["backend/src/main.py", "run-once-x"] },
  ];
}

export function getManualRunState() {
  return cloneManualRunState();
}

export function startManualRun(target: ManualRunTarget) {
  if (activeManualRun) {
    return {
      accepted: false,
      state: cloneManualRunState(),
    };
  }

  const paths = getLocalProjectPaths();
  const pythonExecutable = process.env.PYTHON_EXECUTABLE || "python";
  const commandPlan = commandPlanForTarget(target);

  manualRunState = {
    status: "running",
    target,
    startedAt: new Date().toISOString(),
    finishedAt: null,
    currentStage: "Preparing",
    summary: "Running",
    commands: [],
  };

  activeManualRun = (async () => {
    const results: ManualRunCommandState[] = [];

    for (const item of commandPlan) {
      const commandIndex = results.length;
      const result = await runCommand({
        cwd: paths.rootDir,
        pythonExecutable,
        label: item.label,
        args: item.args,
        onUpdate: (command) => {
          results[commandIndex] = command;
          const progressText = extractProgressText(command);
          manualRunState = {
            ...manualRunState,
            currentStage: progressText ?? `${item.label} running`,
            summary: progressText ?? `${item.label} running`,
            commands: results.filter(Boolean).map((entry) => ({ ...entry })),
          };
        },
      });
      results[commandIndex] = result;
      const progressText = extractProgressText(result);
      manualRunState = {
        ...manualRunState,
        currentStage: progressText ?? item.label,
        summary: progressText ?? `${item.label} completed`,
        commands: results.map((entry) => ({ ...entry })),
      };
      if ((result.exitCode ?? 1) !== 0) {
        break;
      }
    }

    const failed = results.some((item) => (item.exitCode ?? 1) !== 0);
    manualRunState = {
      status: failed ? "failed" : "succeeded",
      target,
      startedAt: manualRunState.startedAt,
      finishedAt: new Date().toISOString(),
      currentStage: failed ? "Failed" : "Completed",
      summary: failed ? "Manual run failed" : "Manual run completed",
      commands: results,
    };
  })().finally(() => {
    activeManualRun = null;
  });

  return {
    accepted: true,
    state: cloneManualRunState(),
  };
}
export function getControlPanelData(): ControlPanelData {
  const paths = getLocalProjectPaths();
  const db = getDb();
  const aiConfig = readAiSettings(paths.aiSettingsPath);
  const xhsConfig = readXhsSettings(paths.watchlistPath);
  const xConfig = readXSettings(paths.xWatchlistPath);
  const scheduleTimes = readRuntimeScheduleTimes(paths.runtimeSettingsPath);
  const xhsState = readMonitorState(paths.xhsStatePath);
  const xState = readMonitorState(paths.xStatePath);
  const xhsAccountStatuses = buildAccountStatuses(
    db,
    "xiaohongshu",
    xhsConfig.accounts,
    xhsState,
  );
  const xAccountStatuses = buildAccountStatuses(db, "x", xConfig.accounts, xState);

  return {
    runtime: {
      xiaohongshuScheduleTimes: scheduleTimes.xiaohongshuScheduleTimes,
      xScheduleTimes: scheduleTimes.xScheduleTimes,
      lastRunAt: getLastAnalysisRunAt(db),
      latestError: getLatestErrorText([
        {
          platform: "xiaohongshu",
          enabled: xhsConfig.enabled,
          statuses: xhsAccountStatuses,
        },
        {
          platform: "x",
          enabled: xConfig.enabled,
          statuses: xAccountStatuses,
        },
      ]),
      dbPresent: existsSync(paths.insightDbPath),
      dbPath: toRelativeProjectPath(paths.rootDir, paths.insightDbPath),
      manualRun: getManualRunState(),
    },
    stats: getStatsFromDb(db),
    ai: {
      config: aiConfig,
    },
    xiaohongshu: {
      config: xhsConfig,
      status: {
        loginStatus: hasPersistentLogin(paths.xhsUserDataDir) ? "ready" : "missing",
        loginPath: toRelativeProjectPath(paths.rootDir, paths.xhsUserDataDir),
        accounts: xhsAccountStatuses,
      },
    },
    x: {
      config: xConfig,
      status: {
        accounts: xAccountStatuses,
      },
    },
  };
}

export function saveControlSettings(payload: unknown): ControlPanelData {
  const parsed = controlSaveSchema.parse(payload);
  const paths = getLocalProjectPaths();
  const xiaohongshuScheduleTimes = normalizeScheduleTimes(parsed.xiaohongshuScheduleTimes);
  const xScheduleTimes = normalizeScheduleTimes(parsed.xScheduleTimes);
  const xhsSettings = {
    ...parsed.xiaohongshu,
    accounts: normalizeAccounts(parsed.xiaohongshu.accounts),
  };
  const xSettings = {
    ...parsed.x,
    nitterInstances: normalizeStringList(parsed.x.nitterInstances),
    accounts: normalizeAccounts(parsed.x.accounts),
  };

  writeJsonFile(paths.runtimeSettingsPath, {
    xiaohongshu_schedule_times: xiaohongshuScheduleTimes,
    x_schedule_times: xScheduleTimes,
  });
  writeAiSettings(paths.aiSettingsPath, parsed.ai);
  writeJsonFile(paths.watchlistPath, {
    enabled: xhsSettings.enabled,
    browser_channel: xhsSettings.browserChannel,
    headless: xhsSettings.headless,
    inter_account_delay_sec: xhsSettings.interAccountDelaySec,
    inter_account_delay_jitter_sec: xhsSettings.interAccountDelayJitterSec,
    detail_delay_sec: xhsSettings.detailDelaySec,
    detail_fallback_enabled: xhsSettings.detailFallbackEnabled,
    detail_fallback_limit_per_account: xhsSettings.detailFallbackLimitPerAccount,
    exclude_old_posts: xhsSettings.excludeOldPosts,
    max_post_age_days: xhsSettings.maxPostAgeDays,
    accounts: xhsSettings.accounts.map((account) => ({
      name: account.name,
      profile_url: account.profileUrl,
      limit: account.limit,
    })),
  });
  writeJsonFile(paths.xWatchlistPath, {
    enabled: xSettings.enabled,
    headless: xSettings.headless,
    page_wait_sec: xSettings.pageWaitSec,
    inter_account_delay_sec: xSettings.interAccountDelaySec,
    inter_account_delay_jitter_sec: xSettings.interAccountDelayJitterSec,
    exclude_old_posts: xSettings.excludeOldPosts,
    max_post_age_days: xSettings.maxPostAgeDays,
    nitter_instances: xSettings.nitterInstances,
    accounts: xSettings.accounts.map((account) => ({
      name: account.name,
      profile_url: account.profileUrl,
      limit: account.limit,
    })),
  });

  return getControlPanelData();
}
