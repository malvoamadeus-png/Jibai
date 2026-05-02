export type PagedResult<T> = {
  rows: T[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
};

export type ViewStance =
  | "strong_bullish"
  | "bullish"
  | "neutral"
  | "bearish"
  | "strong_bearish"
  | "mixed"
  | "mention_only"
  | "unknown";

export type ViewDirection = "positive" | "negative" | "neutral" | "mixed" | "unknown";
export type ViewJudgmentType =
  | "direct"
  | "implied"
  | "factual_only"
  | "quoted"
  | "mention_only"
  | "unknown";
export type ViewConviction = "strong" | "medium" | "weak" | "none" | "unknown";
export type ViewEvidenceType =
  | "price_action"
  | "earnings"
  | "guidance"
  | "management_commentary"
  | "valuation"
  | "policy"
  | "rumor"
  | "position"
  | "capital_flow"
  | "technical"
  | "macro"
  | "other"
  | "unknown";

export type ViewEntityType = "stock" | "theme" | "macro" | "other";

export type OverviewData = {
  lastRunAt: string | null;
  authorCount: number;
  stockCount: number;
  themeCount: number;
  contentCount: number;
  latestAuthors: AuthorListItem[];
  latestStocks: StockListItem[];
  latestThemes: ThemeListItem[];
};

export type AuthorListItem = {
  platform: string;
  accountKey: string;
  accountName: string;
  authorNickname: string;
  profileUrl: string;
  latestDate: string | null;
  latestStatus: string | null;
  totalDays: number;
  totalNotes: number;
  updatedAt: string | null;
};

export type TimelineNote = {
  note_id: string;
  url: string;
  title: string;
  publish_time: string | null;
};

export type AuthorDayViewpoint = {
  entityType: ViewEntityType;
  entityKey: string;
  entityName: string;
  stance: ViewStance;
  direction: ViewDirection;
  judgmentType: ViewJudgmentType;
  conviction: ViewConviction;
  evidenceType: ViewEvidenceType;
  logic: string;
  evidence: string[];
  noteIds: string[];
  noteUrls: string[];
  timeHorizons: string[];
};

export type AuthorTimelineDay = {
  date: string;
  status: "has_update_today" | "no_update_today" | "crawl_failed";
  noteCountToday: number;
  summaryText: string;
  noteIds: string[];
  notes: TimelineNote[];
  viewpoints: AuthorDayViewpoint[];
  mentionedStocks: string[];
  mentionedThemes: string[];
  updatedAt: string;
};

export type AuthorDetailData = {
  platform: string;
  accountKey: string;
  accountName: string;
  authorNickname: string;
  authorId: string;
  profileUrl: string;
  timeline: PagedResult<AuthorTimelineDay>;
};

export type StockListItem = {
  securityKey: string;
  displayName: string;
  ticker: string | null;
  market: string | null;
  latestDate: string | null;
  mentionDays: number;
  totalMentions: number;
  updatedAt: string | null;
};

export type EntityAuthorView = {
  platform: string;
  account_name: string;
  author_nickname: string;
  stance: ViewStance;
  direction: ViewDirection;
  judgment_type: ViewJudgmentType;
  conviction: ViewConviction;
  evidence_type: ViewEvidenceType;
  logic: string;
  note_ids: string[];
  note_urls: string[];
  evidence: string[];
  time_horizons: string[];
};

export type StockTimelineDay = {
  date: string;
  mentionCount: number;
  authorViews: EntityAuthorView[];
  updatedAt: string;
};

export type StockKlineCandle = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
};

export type StockKlineMarker = {
  date: string;
  mentionCount: number;
  authorViews: EntityAuthorView[];
};

export type StockKlineData = {
  sourceLabel: string | null;
  message: string | null;
  candles: StockKlineCandle[];
  markers: StockKlineMarker[];
};

export type StockDetailData = {
  securityKey: string;
  displayName: string;
  ticker: string | null;
  market: string | null;
  timeline: PagedResult<StockTimelineDay>;
};

export type ThemeListItem = {
  themeKey: string;
  displayName: string;
  latestDate: string | null;
  mentionDays: number;
  totalMentions: number;
  updatedAt: string | null;
};

export type ThemeTimelineDay = {
  date: string;
  mentionCount: number;
  authorViews: EntityAuthorView[];
  updatedAt: string;
};

export type ThemeDetailData = {
  themeKey: string;
  displayName: string;
  timeline: PagedResult<ThemeTimelineDay>;
};

export type PlatformKey = "xiaohongshu" | "x";

export type ControlAccountConfig = {
  name: string;
  profileUrl: string;
  limit: number;
};

export type ControlAccountStatus = {
  name: string;
  lastStatus: "success" | "failed" | "idle";
  lastRunAt: string | null;
  lastError: string | null;
  seenCount: number;
  candidateCount: number | null;
  newNoteCount: number | null;
};

export type XiaohongshuSettings = {
  enabled: boolean;
  browserChannel: string;
  headless: boolean;
  interAccountDelaySec: number;
  interAccountDelayJitterSec: number;
  detailDelaySec: number;
  detailFallbackEnabled: boolean;
  detailFallbackLimitPerAccount: number;
  excludeOldPosts: boolean;
  maxPostAgeDays: number;
  accounts: ControlAccountConfig[];
};

export type XSettings = {
  enabled: boolean;
  headless: boolean;
  pageWaitSec: number;
  interAccountDelaySec: number;
  interAccountDelayJitterSec: number;
  excludeOldPosts: boolean;
  maxPostAgeDays: number;
  nitterInstances: string[];
  accounts: ControlAccountConfig[];
};

export type XiaohongshuRuntimeStatus = {
  loginStatus: "ready" | "missing";
  loginPath: string;
  accounts: ControlAccountStatus[];
};

export type XRuntimeStatus = {
  accounts: ControlAccountStatus[];
};

export type AiProvider = "openai-compatible" | "anthropic";

export type AiSettings = {
  provider: AiProvider;
  model: string;
  fallbackModels: string[];
  reasoningEffort: string | null;
  baseUrl: string | null;
  hasApiKey: boolean;
};

export type AiSavePayload = {
  provider: AiProvider;
  model: string;
  fallbackModels: string[];
  reasoningEffort: string | null;
  baseUrl: string | null;
  apiKey: string;
};

export type ManualRunTarget = "enabled" | "xiaohongshu" | "x";

export type ManualRunCommandState = {
  label: string;
  command: string;
  exitCode: number | null;
  durationMs: number;
  stdout: string;
  stderr: string;
};

export type ManualRunState = {
  status: "idle" | "running" | "succeeded" | "failed";
  target: ManualRunTarget | null;
  startedAt: string | null;
  finishedAt: string | null;
  currentStage: string | null;
  summary: string;
  commands: ManualRunCommandState[];
};

export type RuntimeControlStatus = {
  xiaohongshuScheduleTimes: string[];
  xScheduleTimes: string[];
  lastRunAt: string | null;
  latestError: string | null;
  dbPresent: boolean;
  dbPath: string;
  manualRun: ManualRunState;
};

export type ControlStats = {
  authorCount: number;
  stockCount: number;
  themeCount: number;
  contentCount: number;
};

export type ControlSavePayload = {
  xiaohongshuScheduleTimes: string[];
  xScheduleTimes: string[];
  xiaohongshu: XiaohongshuSettings;
  x: XSettings;
  ai: AiSavePayload;
};

export type ControlPanelData = {
  runtime: RuntimeControlStatus;
  stats: ControlStats;
  ai: {
    config: AiSettings;
  };
  xiaohongshu: {
    config: XiaohongshuSettings;
    status: XiaohongshuRuntimeStatus;
  };
  x: {
    config: XSettings;
    status: XRuntimeStatus;
  };
};
