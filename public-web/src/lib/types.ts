export type UserProfile = {
  id: string;
  email: string;
  displayName: string;
  avatarUrl: string;
  isAdmin: boolean;
};

export type Domain = "stock" | "crypto";
export type OnchainChainKey = "ethereum" | "base" | "bsc" | "solana";

export type OnchainChain = {
  key: OnchainChainKey;
  chainIndex: string;
  enabled?: boolean;
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
export type ViewSignalType = "explicit_stance" | "logic_based" | "informational" | "mention_signal" | "unknown";
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
  | "onchain"
  | "tokenomics"
  | "unlock"
  | "ecosystem"
  | "protocol_revenue"
  | "catalyst"
  | "listing"
  | "liquidity"
  | "funding_rate"
  | "security_incident"
  | "regulation"
  | "other"
  | "unknown";

export type ViewEntityType = "stock" | "theme" | "macro" | "other" | "crypto_entity";

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
  entityIdentifierType: string;
  rawIdentifiers: string[];
  normalizedStatus: string;
  sourceSignalLevel: string;
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
  metadata: Record<string, unknown>;
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
  mentionedCrypto: string[];
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

export type EntitySortKey = "date_desc" | "date_asc" | "count_desc" | "count_asc";

export type EntityAuthorView = {
  platform: string;
  account_name: string;
  author_nickname: string;
  entity_identifier_type?: string;
  raw_identifiers?: string[];
  normalized_status?: string;
  source_signal_level?: string;
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
  metadata?: Record<string, unknown>;
};

export type StockMatrixAuthor = {
  accountName: string;
  authorNickname: string;
  mentionCount: number;
  latestDate: string | null;
};

export type StockMatrixStock = {
  securityKey: string;
  displayName: string;
  ticker: string | null;
  market: string | null;
  mentionCount: number;
  latestDate: string | null;
};

export type StockMatrixView = EntityAuthorView & {
  date: string;
};

export type StockMatrixGranularity = "day" | "week";
export type CryptoMatrixGranularity = StockMatrixGranularity;
export type CryptoBriefIdentityStatus = "anchored" | "fuzzy" | "ambiguous";

export type StockMatrixCell = {
  securityKey: string;
  accountName: string;
  authorNickname: string;
  views: StockMatrixView[];
};

export type StockMatrixData = {
  startDate: string | null;
  endDate: string | null;
  previousEndDate: string | null;
  nextEndDate: string | null;
  authors: StockMatrixAuthor[];
  stocks: StockMatrixStock[];
  cells: StockMatrixCell[];
};

export type StockNarrativeSections = {
  mainstreamNarrative: string[];
  newDirections: string[];
  rareNegativeSignals: string[];
};

export type StockNarrativeBrief = {
  id: string;
  briefDate: string;
  windowStart: string | null;
  windowEnd: string | null;
  previousWindowStart: string | null;
  previousWindowEnd: string | null;
  baselineStart: string | null;
  baselineEnd: string | null;
  inputDigest: Record<string, unknown>;
  sections: StockNarrativeSections;
  briefText: string;
  modelName: string | null;
  promptVersion: string;
  usage: Record<string, unknown>;
  createdAt: string | null;
  updatedAt: string | null;
};

export type CryptoMatrixAsset = {
  assetKey: string;
  displayName: string;
  ticker: string | null;
  market: string | null;
  mentionCount: number;
  latestDate: string | null;
  summary: string;
  summaryStatus: string | null;
  identityStatus: CryptoBriefIdentityStatus | null;
  summaryUpdatedAt: string | null;
};

export type CryptoMatrixView = StockMatrixView;

export type CryptoMatrixCell = {
  assetKey: string;
  accountName: string;
  authorNickname: string;
  views: CryptoMatrixView[];
};

export type CryptoMatrixData = {
  startDate: string | null;
  endDate: string | null;
  previousEndDate: string | null;
  nextEndDate: string | null;
  authors: StockMatrixAuthor[];
  assets: CryptoMatrixAsset[];
  cells: CryptoMatrixCell[];
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
  identifierType?: string | null;
  rawIdentifiers?: string[];
  normalizedStatus?: string | null;
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

export type MarketTopRiskSignal = {
  value: number | null;
  active: boolean;
  module: string;
};

export type MarketTopRiskSnapshot = {
  week: string;
  nasdaq100: number | null;
  ndxDdFrom52wHigh: number | null;
  breadthWeaknessScore: number | null;
  breakageScore: number | null;
  riskScore: number;
  riskLevel: "low" | "watch" | "elevated" | "high";
  warningActive: boolean;
  confirmationActive: boolean;
  signals: Record<string, MarketTopRiskSignal>;
  metrics: Record<string, unknown>;
  sources: Record<string, unknown>;
  updatedAt: string;
};

export type MarketTopRiskHistoryPoint = {
  week: string;
  nasdaq100: number | null;
  breadthWeaknessScore: number | null;
  breakageScore: number | null;
  riskScore: number;
  riskLevel: MarketTopRiskSnapshot["riskLevel"];
  warningActive: boolean;
  confirmationActive: boolean;
};

export type MarketTopRiskData = {
  latest: MarketTopRiskSnapshot | null;
  history: MarketTopRiskHistoryPoint[];
  baseline: {
    nearHighFwd26wAvgDrawdown: number | null;
    nearHighFwd26wDd10Probability: number | null;
    method: string;
  };
};

export type OnchainWalletListItem = {
  id: string;
  address: string;
  addressShort: string;
  displayName: string;
  adminLabel: string;
  userNote: string;
  subscribed: boolean;
  enabledChains: OnchainChain[];
  lastSnapshotAt: string | null;
  status: string;
};

export type OnchainRequestItem = {
  id: string;
  status: string;
  rawInput: string;
  normalizedAddress: string;
  createdAt: string;
};

export type OnchainHolder = {
  walletId: string;
  address: string;
  addressShort: string;
  displayName: string;
  balance: number;
  valueUsd: number;
};

export type OnchainTokenMatrixToken = {
  tokenId: string;
  tokenKey: string;
  chainKey: OnchainChainKey;
  chainIndex: string;
  contractAddress: string;
  symbol: string;
  displayName: string;
  latestDate: string | null;
  latestHolderCount: number;
  latestValueUsd: number;
};

export type OnchainTokenMatrixCell = {
  date: string;
  tokenId: string;
  holderCount: number;
  balanceSum: number;
  valueUsdSum: number;
  holderCountDelta: number | null;
  balanceDelta: number | null;
  valueUsdDelta: number | null;
  holders: OnchainHolder[];
};

export type OnchainTokenMatrixData = {
  dates: string[];
  tokens: OnchainTokenMatrixToken[];
  cells: OnchainTokenMatrixCell[];
};

export type OnchainWalletMatrixToken = {
  tokenId: string;
  tokenKey: string;
  chainKey: OnchainChainKey;
  chainIndex: string;
  contractAddress: string;
  symbol: string;
  displayName: string;
};

export type OnchainWalletMatrixCell = {
  date: string;
  tokenId: string;
  balance: number;
  valueUsd: number;
  balanceDelta: number | null;
  valueUsdDelta: number | null;
  state: string;
};

export type OnchainWalletMatrixData = {
  meta: OnchainWalletListItem | null;
  dates: string[];
  tokens: OnchainWalletMatrixToken[];
  cells: OnchainWalletMatrixCell[];
};

export type OnchainRunItem = {
  id: string;
  kind: string;
  status: string;
  summary: string;
  errorText: string | null;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
};

export type OnchainOverviewData = {
  latestDate: string | null;
  walletCount: number;
  tokenCount: number;
  topTokens: Array<Record<string, unknown>>;
  newTokens: Array<Record<string, unknown>>;
  increasedTokens: Array<Record<string, unknown>>;
  activeWallets: Array<Record<string, unknown>>;
  recentRuns: OnchainRunItem[];
};

export type OnchainAdminWalletItem = {
  id: string;
  address: string;
  addressShort: string;
  adminLabel: string;
  status: string;
  lastSnapshotAt: string | null;
  enabledChains: OnchainChain[];
};

export type OnchainAdminRequestItem = {
  id: string;
  rawInput: string;
  normalizedAddress: string;
  status: string;
  requesterEmail: string;
  createdAt: string;
};

export type OnchainAdminDashboard = {
  approvedCount: number;
  pendingCount: number;
  wallets: OnchainAdminWalletItem[];
  requests: OnchainAdminRequestItem[];
  runs: OnchainRunItem[];
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

export type CryptoAdminBlockedTermItem = {
  term: string;
  createdAt: string | null;
  updatedAt: string | null;
};

export type CryptoAdminDeletedAssetItem = {
  assetKey: string;
  displayName: string;
  reason: string;
  createdAt: string | null;
  updatedAt: string | null;
};

export type CryptoAdminControls = {
  blockedTerms: CryptoAdminBlockedTermItem[];
  deletedAssets: CryptoAdminDeletedAssetItem[];
};
