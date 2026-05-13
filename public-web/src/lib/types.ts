export type UserProfile = {
  id: string;
  email: string;
  displayName: string;
  avatarUrl: string;
  isAdmin: boolean;
};

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
export type ViewSignalType = "explicit_stance" | "logic_based" | "unknown";
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

export type AccountListItem = {
  id: string;
  username: string;
  displayName: string;
  profileUrl: string;
  subscribed: boolean;
  backfillCompletedAt: string | null;
};

export type RequestListItem = {
  id: string;
  status: string;
  rawInput: string;
  normalizedUsername: string;
  createdAt: string;
};

export type FeedDay = {
  id: string;
  username: string;
  displayName: string;
  profileUrl: string;
  date: string;
  status: string;
  noteCount: number;
  summary: string;
  notes: Array<{ note_id: string; url: string; title: string; publish_time: string | null }>;
  viewpoints: Array<Record<string, unknown>>;
  updatedAt: string;
};

export type AuthorListItem = {
  accountId: string;
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
  signalType: ViewSignalType;
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
  accountId: string;
  platform: string;
  accountKey: string;
  accountName: string;
  authorNickname: string;
  authorId: string;
  profileUrl: string;
  timeline: PagedResult<AuthorTimelineDay>;
};

export type EntityListItem = {
  key: string;
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
  signal_type: ViewSignalType;
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

export type EntityDetailData = {
  key: string;
  displayName: string;
  ticker: string | null;
  market: string | null;
  timeline: PagedResult<StockTimelineDay>;
  chart?: StockKlineData | null;
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

export type AdminRequestItem = {
  id: string;
  rawInput: string;
  normalizedUsername: string;
  requesterEmail: string;
  createdAt: string;
  account: {
    id: string;
    username: string;
    displayName: string;
    profileUrl: string;
    status: string;
  };
};

export type AdminAccountItem = {
  id: string;
  username: string;
  displayName: string;
  profileUrl: string;
  backfillCompletedAt: string | null;
};

export type AdminJobItem = {
  id: string;
  kind: string;
  status: string;
  summary: string;
  errorText: string | null;
  createdAt: string;
  finishedAt: string | null;
};
