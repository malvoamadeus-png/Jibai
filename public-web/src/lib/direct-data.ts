import type { SupabaseClient } from "@supabase/supabase-js";

import type {
  AccountListItem,
  AdminAccountItem,
  AdminJobItem,
  AdminRequestItem,
  AuthorDayViewpoint,
  AuthorDetailData,
  AuthorListItem,
  AuthorTimelineDay,
  CryptoAdminControls,
  CryptoMatrixAsset,
  CryptoMatrixCell,
  CryptoMatrixData,
  CryptoMatrixGranularity,
  EntityAuthorView,
  EntityDetailData,
  EntityListItem,
  EntitySortKey,
  FeedDay,
  HomeStats,
  MarketTopRiskData,
  MarketTopRiskHistoryPoint,
  MarketTopRiskSignal,
  MarketTopRiskSnapshot,
  PagedResult,
  RequestListItem,
  StockKlineCandle,
  StockKlineData,
  StockNewsItem,
  StockNewsLinkedEntity,
  StockNewsTrackingItem,
  StockNewsTrackingResponse,
  StockNewsTrackingStock,
  StockNewsTimelineDay,
  StockNewsTimelineResponse,
  StockKlineMarker,
  StockKlineMarkerView,
  StockBloggerAuthorScore,
  StockBloggerGoldData,
  StockBloggerGoldRun,
  StockBloggerHorizonScore,
  StockBloggerScoreEvent,
  StockMatrixAuthor,
  StockMatrixCell,
  StockMatrixData,
  StockMatrixGranularity,
  StockMatrixStock,
  StockMatrixView,
  StockNarrativeBrief,
  StockNarrativeSections,
  TimelineNote,
  UserProfile,
  ViewConviction,
  ViewDirection,
  ViewEntityType,
  ViewEvidenceType,
  ViewJudgmentType,
  ViewSignalType,
  ViewStance,
} from "@/lib/types";
import { makeAccountKey } from "@/lib/utils";
import { normalizeXUsername } from "@/lib/x";

type JsonRecord = Record<string, unknown>;
type Domain = "stock" | "crypto";
const STOCK_KLINE_WINDOW_DAYS = 180;

function assertNoError(error: unknown) {
  if (error && typeof error === "object" && "message" in error) {
    throw new Error(String((error as { message: unknown }).message));
  }
}

function asArray<T = unknown>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

function asRecord(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as JsonRecord) : {};
}

function asString(value: unknown, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function asNullableString(value: unknown) {
  return typeof value === "string" && value ? value : null;
}

function asNumber(value: unknown, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function asNullableNumber(value: unknown) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function dateKeyDaysAgo(days: number) {
  const now = new Date();
  const cutoff = new Date(now.getFullYear(), now.getMonth(), now.getDate() - days);
  const year = cutoff.getFullYear();
  const month = String(cutoff.getMonth() + 1).padStart(2, "0");
  const day = String(cutoff.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function normalizeStringArray(value: unknown) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item)).filter(Boolean);
  }
  if (typeof value === "string" && value.trim()) {
    return [value.trim()];
  }
  return [];
}

function normalizeViewpoint(rawValue: unknown): AuthorDayViewpoint | null {
  const raw = asRecord(rawValue);
  const stance = asString(raw.stance, "unknown") as ViewStance;

  return {
    entityType: asString(raw.entity_type ?? raw.entityType, "other") as ViewEntityType,
    entityKey: asString(raw.entity_key ?? raw.entityKey),
    entityName: asString(raw.entity_name ?? raw.entityName),
    entityIdentifierType: asString(raw.entity_identifier_type ?? raw.entityIdentifierType),
    rawIdentifiers: normalizeStringArray(raw.raw_identifiers ?? raw.rawIdentifiers),
    normalizedStatus: asString(raw.normalized_status ?? raw.normalizedStatus),
    sourceSignalLevel: asString(raw.source_signal_level ?? raw.sourceSignalLevel),
    stance,
    direction: asString(raw.direction, "unknown") as ViewDirection,
    signalType: asString(raw.signal_type ?? raw.signalType, "unknown") as ViewSignalType,
    judgmentType: asString(raw.judgment_type ?? raw.judgmentType, "unknown") as ViewJudgmentType,
    conviction: asString(raw.conviction, "unknown") as ViewConviction,
    evidenceType: asString(raw.evidence_type ?? raw.evidenceType, "unknown") as ViewEvidenceType,
    logic: asString(raw.logic),
    evidence: normalizeStringArray(raw.evidence),
    noteIds: normalizeStringArray(raw.note_ids ?? raw.noteIds),
    noteUrls: normalizeStringArray(raw.note_urls ?? raw.noteUrls),
    timeHorizons: normalizeStringArray(raw.time_horizons ?? raw.timeHorizons),
    metadata: asRecord(raw.metadata),
  };
}

function normalizeEntityAuthorView(rawValue: unknown): EntityAuthorView {
  const raw = asRecord(rawValue);
  const accountName = asString(raw.account_name ?? raw.author_name ?? raw.username).trim().replace(/^@/, "").toLowerCase();

  return {
    platform: asString(raw.platform, "x"),
    account_name: accountName,
    author_nickname: asString(raw.author_nickname ?? raw.display_name),
    entity_identifier_type: asString(raw.entity_identifier_type),
    raw_identifiers: normalizeStringArray(raw.raw_identifiers),
    normalized_status: asString(raw.normalized_status),
    source_signal_level: asString(raw.source_signal_level),
    stance: asString(raw.stance, "unknown") as ViewStance,
    direction: asString(raw.direction, "unknown") as ViewDirection,
    signal_type: asString(raw.signal_type, "unknown") as ViewSignalType,
    judgment_type: asString(raw.judgment_type, "unknown") as ViewJudgmentType,
    conviction: asString(raw.conviction, "unknown") as ViewConviction,
    evidence_type: asString(raw.evidence_type, "unknown") as ViewEvidenceType,
    logic: asString(raw.logic),
    note_ids: normalizeStringArray(raw.note_ids),
    note_urls: normalizeStringArray(raw.note_urls),
    evidence: normalizeStringArray(raw.evidence),
    time_horizons: normalizeStringArray(raw.time_horizons),
    metadata: asRecord(raw.metadata),
  };
}

function normalizeStockMatrixView(rawValue: unknown): StockMatrixView {
  const raw = asRecord(rawValue);
  return {
    ...normalizeEntityAuthorView(rawValue),
    date: asString(raw.date),
  };
}

function normalizeStockMatrixAuthor(rawValue: unknown): StockMatrixAuthor {
  const raw = asRecord(rawValue);
  const accountName = asString(raw.account_name ?? raw.accountName).trim().replace(/^@/, "").toLowerCase();
  return {
    accountName,
    authorNickname: asString(raw.author_nickname ?? raw.authorNickname, accountName),
    mentionCount: asNumber(raw.mention_count ?? raw.mentionCount),
    latestDate: raw.latest_date || raw.latestDate ? String(raw.latest_date || raw.latestDate) : null,
  };
}

function normalizeStockMatrixStock(rawValue: unknown): StockMatrixStock {
  const raw = asRecord(rawValue);
  return {
    securityKey: asString(raw.security_key ?? raw.securityKey),
    displayName: asString(raw.display_name ?? raw.displayName ?? raw.security_key ?? raw.securityKey),
    ticker: asNullableString(raw.ticker),
    market: asNullableString(raw.market),
    mentionCount: asNumber(raw.mention_count ?? raw.mentionCount),
    latestDate: raw.latest_date || raw.latestDate ? String(raw.latest_date || raw.latestDate) : null,
  };
}

function normalizeStockMatrixCell(rawValue: unknown): StockMatrixCell {
  const raw = asRecord(rawValue);
  const accountName = asString(raw.account_name ?? raw.accountName).trim().replace(/^@/, "").toLowerCase();
  return {
    securityKey: asString(raw.security_key ?? raw.securityKey),
    accountName,
    authorNickname: asString(raw.author_nickname ?? raw.authorNickname, accountName),
    views: asArray(raw.views).map(normalizeStockMatrixView),
  };
}

function normalizeStockNewsLinkedEntity(rawValue: unknown): StockNewsLinkedEntity {
  const raw = asRecord(rawValue);
  return {
    entityType: asString(raw.entity_type ?? raw.entityType, "theme") as StockNewsLinkedEntity["entityType"],
    entityKey: asString(raw.entity_key ?? raw.entityKey),
    entityName: asString(raw.entity_name ?? raw.entityName),
    entityCodeOrName: asNullableString(raw.entity_code_or_name ?? raw.entityCodeOrName),
    metadata: asRecord(raw.metadata),
  };
}

function normalizeStockNewsItem(rawValue: unknown): StockNewsItem {
  const raw = asRecord(rawValue);
  return {
    eventKey: asString(raw.event_key ?? raw.eventKey),
    eventSortOrder: asNumber(raw.event_sort_order ?? raw.eventSortOrder),
    noteId: asString(raw.note_id ?? raw.noteId),
    noteUrl: asString(raw.note_url ?? raw.noteUrl),
    accountName: asString(raw.account_name ?? raw.accountName),
    authorNickname: asString(raw.author_nickname ?? raw.authorNickname),
    publishTime: asNullableString(raw.publish_time ?? raw.publishTime),
    headline: asString(raw.headline),
    eventSummary: asString(raw.event_summary ?? raw.eventSummary),
    eventType: asString(raw.event_type ?? raw.eventType, "other"),
    eventNature: asString(raw.event_nature ?? raw.eventNature, "reported"),
    linkedEntities: asArray(raw.linked_entities ?? raw.linkedEntities).map(normalizeStockNewsLinkedEntity),
    metadata: asRecord(raw.metadata),
    isTracked: Boolean(raw.is_tracked ?? raw.isTracked),
  };
}

function normalizeStockNewsDay(rawValue: unknown): StockNewsTimelineDay {
  const raw = asRecord(rawValue);
  return {
    date: asString(raw.date),
    eventCount: asNumber(raw.event_count ?? raw.eventCount),
    events: asArray(raw.events).map(normalizeStockNewsItem),
    updatedAt: asNullableString(raw.updated_at ?? raw.updatedAt) ?? "",
  };
}

function normalizeStockNewsTrackingStock(rawValue: unknown): StockNewsTrackingStock {
  const raw = asRecord(rawValue);
  return {
    id: asString(raw.id),
    sortOrder: asNumber(raw.sort_order ?? raw.sortOrder),
    securityKey: asString(raw.security_key ?? raw.securityKey),
    displayName: asString(raw.display_name ?? raw.displayName ?? raw.security_key ?? raw.securityKey),
    ticker: asNullableString(raw.ticker),
    market: asNullableString(raw.market),
    countryOrRegion: asString(raw.country_or_region ?? raw.countryOrRegion),
    benefitLayer: asString(raw.benefit_layer ?? raw.benefitLayer),
    coreLink: asString(raw.core_link ?? raw.coreLink),
    benefitLogic: asString(raw.benefit_logic ?? raw.benefitLogic),
    confidence: asString(raw.confidence, "unknown"),
    selectedDate: asString(raw.selected_date ?? raw.selectedDate),
    anchorStatus: asString(raw.anchor_status ?? raw.anchorStatus, "pending"),
    anchorDate: asNullableString(raw.anchor_date ?? raw.anchorDate),
    anchorPrice: asNullableNumber(raw.anchor_price ?? raw.anchorPrice),
    latestDate: asNullableString(raw.latest_date ?? raw.latestDate),
    latestPrice: asNullableNumber(raw.latest_price ?? raw.latestPrice),
    horizon3Status: asString(raw.horizon_3_status ?? raw.horizon3Status, "pending"),
    return3d: asNullableNumber(raw.return_3d ?? raw.return3d),
    target3dDate: asNullableString(raw.target_3d_date ?? raw.target3dDate),
    horizon7Status: asString(raw.horizon_7_status ?? raw.horizon7Status, "pending"),
    return7d: asNullableNumber(raw.return_7d ?? raw.return7d),
    target7dDate: asNullableString(raw.target_7d_date ?? raw.target7dDate),
    returnSinceSelected: asNullableNumber(raw.return_since_selected ?? raw.returnSinceSelected),
    priceStatus: asString(raw.price_status ?? raw.priceStatus, "pending"),
    priceError: asString(raw.price_error ?? raw.priceError),
    lastPriceCheckedAt: asNullableString(raw.last_price_checked_at ?? raw.lastPriceCheckedAt),
  };
}

function normalizeStockNewsTrackingItem(rawValue: unknown): StockNewsTrackingItem {
  const raw = asRecord(rawValue);
  return {
    id: asString(raw.id),
    eventKey: asString(raw.event_key ?? raw.eventKey),
    eventDate: asNullableString(raw.event_date ?? raw.eventDate),
    eventSnapshot: asRecord(raw.event_snapshot ?? raw.eventSnapshot),
    status: asString(raw.status, "pending"),
    modelName: asNullableString(raw.model_name ?? raw.modelName),
    errorText: asString(raw.error_text ?? raw.errorText),
    createdAt: asString(raw.created_at ?? raw.createdAt),
    analyzedAt: asNullableString(raw.analyzed_at ?? raw.analyzedAt),
    stocks: asArray(raw.stocks).map(normalizeStockNewsTrackingStock),
  };
}

function normalizeStockBloggerHorizonScore(rawValue: unknown): StockBloggerHorizonScore {
  const raw = asRecord(rawValue);
  return {
    status: asString(raw.status),
    score: asNullableNumber(raw.score),
    directionalExcess: asNullableNumber(raw.directional_excess ?? raw.directionalExcess),
    stockReturn: asNullableNumber(raw.stock_return ?? raw.stockReturn),
    benchmarkReturn: asNullableNumber(raw.benchmark_return ?? raw.benchmarkReturn),
    excessReturn: asNullableNumber(raw.excess_return ?? raw.excessReturn),
    targetDate: asNullableString(raw.target_date ?? raw.targetDate),
    message: asString(raw.message),
  };
}

function normalizeStockBloggerHorizonMap(rawValue: unknown): Record<string, StockBloggerHorizonScore> {
  const raw = asRecord(rawValue);
  const result: Record<string, StockBloggerHorizonScore> = {};
  for (const label of ["1d", "5d", "20d"]) {
    result[label] = normalizeStockBloggerHorizonScore(raw[label]);
  }
  return result;
}

function normalizeStockBloggerEvent(rawValue: unknown): StockBloggerScoreEvent {
  const raw = asRecord(rawValue);
  return {
    id: asString(raw.id),
    securityKey: asString(raw.security_key ?? raw.securityKey),
    displayName: asString(raw.display_name ?? raw.displayName),
    ticker: asNullableString(raw.ticker),
    market: asNullableString(raw.market),
    eventTradingDay: asString(raw.event_trading_day ?? raw.eventTradingDay),
    publishedAt: asNullableString(raw.published_at ?? raw.publishedAt),
    direction: asString(raw.direction, "unknown") as StockBloggerScoreEvent["direction"],
    conviction: asString(raw.conviction, "unknown") as StockBloggerScoreEvent["conviction"],
    evidenceType: asString(raw.evidence_type ?? raw.evidenceType),
    anchorTradingDay: asNullableString(raw.anchor_trading_day ?? raw.anchorTradingDay),
    anchorPriceKind: asNullableString(raw.anchor_price_kind ?? raw.anchorPriceKind),
    benchmarkSymbol: asNullableString(raw.benchmark_symbol ?? raw.benchmarkSymbol),
    horizonScores: normalizeStockBloggerHorizonMap(raw.horizon_scores ?? raw.horizonScores),
  };
}

function normalizeStockBloggerAuthor(rawValue: unknown): StockBloggerAuthorScore {
  const raw = asRecord(rawValue);
  return {
    accountId: asString(raw.account_id ?? raw.accountId),
    accountName: asString(raw.account_name ?? raw.accountName),
    authorNickname: asString(raw.author_nickname ?? raw.authorNickname),
    overallScore: asNullableNumber(raw.overall_score ?? raw.overallScore),
    score1d: asNullableNumber(raw.score_1d ?? raw.score1d),
    score5d: asNullableNumber(raw.score_5d ?? raw.score5d),
    score20d: asNullableNumber(raw.score_20d ?? raw.score20d),
    scoredDayCount: asNumber(raw.scored_day_count ?? raw.scoredDayCount),
    eventCount: asNumber(raw.event_count ?? raw.eventCount),
    scoredEventCount: asNumber(raw.scored_event_count ?? raw.scoredEventCount),
    pendingCount: asNumber(raw.pending_count ?? raw.pendingCount),
    positiveCount: asNumber(raw.positive_count ?? raw.positiveCount),
    negativeCount: asNumber(raw.negative_count ?? raw.negativeCount),
    directionCounts: asRecord(raw.direction_counts ?? raw.directionCounts) as Record<string, number>,
    convictionCounts: asRecord(raw.conviction_counts ?? raw.convictionCounts) as Record<string, number>,
    bestHorizon: asNullableString(raw.best_horizon ?? raw.bestHorizon),
    worstHorizon: asNullableString(raw.worst_horizon ?? raw.worstHorizon),
    events: asArray(raw.events).map(normalizeStockBloggerEvent),
  };
}

function normalizeStockBloggerRun(rawValue: unknown): StockBloggerGoldRun | null {
  const raw = asRecord(rawValue);
  const id = asString(raw.id);
  if (!id) return null;
  return {
    id,
    runDate: asString(raw.run_date ?? raw.runDate),
    windowStart: asNullableString(raw.window_start ?? raw.windowStart),
    windowEnd: asNullableString(raw.window_end ?? raw.windowEnd),
    config: asRecord(raw.config),
    eventCount: asNumber(raw.event_count ?? raw.eventCount),
    authorCount: asNumber(raw.author_count ?? raw.authorCount),
    errorText: asString(raw.error_text ?? raw.errorText),
    updatedAt: asNullableString(raw.updated_at ?? raw.updatedAt),
  };
}

function normalizeNarrativeSections(rawValue: unknown): StockNarrativeSections {
  const raw = asRecord(rawValue);
  return {
    mainstreamNarrative: normalizeStringArray(raw.mainstream_narrative ?? raw.mainstreamNarrative),
    newDirections: normalizeStringArray(raw.new_directions ?? raw.newDirections),
    rareNegativeSignals: normalizeStringArray(raw.rare_negative_signals ?? raw.rareNegativeSignals),
  };
}

function normalizeCryptoMatrixAsset(rawValue: unknown): CryptoMatrixAsset {
  const raw = asRecord(rawValue);
  const identityStatusRaw = asString(raw.identity_status ?? raw.identityStatus);
  return {
    assetKey: asString(raw.asset_key ?? raw.assetKey),
    displayName: asString(raw.display_name ?? raw.displayName ?? raw.asset_key ?? raw.assetKey),
    ticker: asNullableString(raw.ticker),
    market: asNullableString(raw.market),
    mentionCount: asNumber(raw.mention_count ?? raw.mentionCount),
    latestDate: raw.latest_date || raw.latestDate ? String(raw.latest_date || raw.latestDate) : null,
    summary: asString(raw.summary),
    summaryStatus: asNullableString(raw.summary_status ?? raw.summaryStatus),
    identityStatus:
      identityStatusRaw === "anchored" || identityStatusRaw === "fuzzy" || identityStatusRaw === "ambiguous"
        ? identityStatusRaw
        : null,
    summaryUpdatedAt: asNullableString(raw.summary_updated_at ?? raw.summaryUpdatedAt),
  };
}

function normalizeCryptoMatrixCell(rawValue: unknown): CryptoMatrixCell {
  const raw = asRecord(rawValue);
  const accountName = asString(raw.account_name ?? raw.accountName).trim().replace(/^@/, "").toLowerCase();
  return {
    assetKey: asString(raw.asset_key ?? raw.assetKey),
    accountName,
    authorNickname: asString(raw.author_nickname ?? raw.authorNickname, accountName),
    views: asArray(raw.views).map(normalizeStockMatrixView),
  };
}

function normalizeAuthorDay(rawValue: unknown): AuthorTimelineDay {
  const raw = asRecord(rawValue);
  const viewpoints = asArray(raw.viewpoints)
    .map(normalizeViewpoint)
    .filter((item): item is AuthorDayViewpoint => item !== null);

  return {
    date: asString(raw.date),
    status: asString(raw.status, "has_update_today") as AuthorTimelineDay["status"],
    noteCountToday: asNumber(raw.noteCountToday ?? raw.note_count_today),
    summaryText: asString(raw.summaryText ?? raw.summary_text),
    noteIds: normalizeStringArray(raw.noteIds ?? raw.note_ids),
    notes: asArray(raw.notes).map((item): TimelineNote => {
      const note = asRecord(item);
      return {
        note_id: asString(note.note_id),
        url: asString(note.url),
        title: asString(note.title),
        publish_time: asNullableString(note.publish_time),
      };
    }),
    viewpoints,
    mentionedStocks: normalizeStringArray(raw.mentionedStocks ?? raw.mentioned_stocks),
    mentionedThemes: normalizeStringArray(raw.mentionedThemes ?? raw.mentioned_themes),
    mentionedCrypto: normalizeStringArray(raw.mentionedCrypto ?? raw.mentioned_crypto),
    updatedAt: asString(raw.updatedAt ?? raw.updated_at),
  };
}

function normalizeFeedDay(rawValue: unknown): FeedDay {
  const raw = asRecord(rawValue);
  return {
    id: asString(raw.id),
    username: asString(raw.username),
    displayName: asString(raw.display_name ?? raw.displayName ?? raw.username),
    profileUrl: asString(raw.profile_url ?? raw.profileUrl),
    date: asString(raw.date),
    status: asString(raw.status),
    noteCount: asNumber(raw.note_count ?? raw.noteCount),
    summary: asString(raw.summary),
    viewpointCount: asNumber(raw.viewpoint_count ?? raw.viewpointCount),
    notes: asArray(raw.notes).map((item): TimelineNote => {
      const note = asRecord(item);
      return {
        note_id: asString(note.note_id),
        url: asString(note.url),
        title: asString(note.title),
        publish_time: asNullableString(note.publish_time),
      };
    }),
    viewpoints: asArray(raw.viewpoints).map((item) => asRecord(item)),
    updatedAt: asString(raw.updated_at ?? raw.updatedAt),
  };
}

function normalizeEntityDay(rawValue: unknown) {
  const raw = asRecord(rawValue);
  const authorViews = asArray(raw.authorViews ?? raw.author_views).map(normalizeEntityAuthorView);

  return {
    date: asString(raw.date),
    mentionCount: asNumber(raw.mentionCount ?? raw.mention_count, authorViews.length),
    authorViews,
    updatedAt: asString(raw.updatedAt ?? raw.updated_at),
  };
}

function normalizeStockCandle(rawValue: unknown): StockKlineCandle | null {
  const raw = asRecord(rawValue);
  const open = asNullableNumber(raw.open ?? raw.open_price);
  const high = asNullableNumber(raw.high ?? raw.high_price);
  const low = asNullableNumber(raw.low ?? raw.low_price);
  const close = asNullableNumber(raw.close ?? raw.close_price);
  const date = asString(raw.date ?? raw.date_key);
  if (!date || open === null || high === null || low === null || close === null) {
    return null;
  }
  return {
    date,
    open,
    high,
    low,
    close,
    volume: asNullableNumber(raw.volume),
  };
}

function normalizeStockMarker(rawValue: unknown): StockKlineMarker | null {
  const raw = asRecord(rawValue);
  const date = asString(raw.date ?? raw.date_key);
  if (!date) return null;
  const authorViews = asArray(raw.authorViews ?? raw.author_views).map((item): StockKlineMarkerView => {
    const view = asRecord(item);
    return {
      platform: asString(view.platform, "x"),
      account_name: asString(view.account_name ?? view.author_name ?? view.username).trim().replace(/^@/, "").toLowerCase(),
      author_nickname: asString(view.author_nickname ?? view.display_name),
      stance: asString(view.stance, "unknown") as ViewStance,
      direction: asString(view.direction, "unknown") as ViewDirection,
      signal_type: asString(view.signal_type, "unknown") as ViewSignalType,
      judgment_type: asString(view.judgment_type, "unknown") as ViewJudgmentType,
      logic: asString(view.logic),
    };
  });
  return {
    date,
    mentionCount: asNumber(raw.mentionCount ?? raw.mention_count, authorViews.length),
    authorViews,
  };
}

function normalizeStockChart(rawValue: unknown): StockKlineData | null {
  const raw = asRecord(rawValue);
  if (Object.keys(raw).length === 0) return null;
  const cutoffDate = dateKeyDaysAgo(STOCK_KLINE_WINDOW_DAYS);
  const candles = asArray(raw.candles)
    .map(normalizeStockCandle)
    .filter((item): item is StockKlineCandle => item !== null && item.date >= cutoffDate)
    .sort((left, right) => left.date.localeCompare(right.date));
  const markers = asArray(raw.markers)
    .map(normalizeStockMarker)
    .filter((item): item is StockKlineMarker => item !== null && item.date >= cutoffDate)
    .sort((left, right) => left.date.localeCompare(right.date));
  return {
    sourceLabel: asNullableString(raw.sourceLabel ?? raw.source_label),
    message: asNullableString(raw.message),
    candles,
    markers,
  };
}

function normalizeRiskSignal(rawValue: unknown): MarketTopRiskSignal {
  const raw = asRecord(rawValue);
  return {
    value: asNullableNumber(raw.value),
    active: Boolean(raw.active ?? raw.signal),
    module: asString(raw.module),
  };
}

function normalizeRiskSignals(rawValue: unknown): Record<string, MarketTopRiskSignal> {
  const raw = asRecord(rawValue);
  return Object.fromEntries(Object.entries(raw).map(([key, value]) => [key, normalizeRiskSignal(value)]));
}

function normalizeRiskLevel(value: unknown): MarketTopRiskSnapshot["riskLevel"] {
  const text = asString(value, "low");
  if (text === "watch" || text === "elevated" || text === "high") return text;
  return "low";
}

function normalizeMarketTopRiskSnapshot(rawValue: unknown): MarketTopRiskSnapshot | null {
  const raw = asRecord(rawValue);
  const week = asString(raw.week);
  if (!week) return null;
  return {
    week,
    nasdaq100: asNullableNumber(raw.nasdaq100),
    ndxDdFrom52wHigh: asNullableNumber(raw.ndx_dd_from_52w_high ?? raw.ndxDdFrom52wHigh),
    breadthWeaknessScore: asNullableNumber(raw.breadth_weakness_score ?? raw.breadthWeaknessScore),
    breakageScore: asNullableNumber(raw.breakage_score ?? raw.breakageScore),
    riskScore: asNumber(raw.risk_score ?? raw.riskScore),
    riskLevel: normalizeRiskLevel(raw.risk_level ?? raw.riskLevel),
    warningActive: Boolean(raw.warning_active ?? raw.warningActive),
    confirmationActive: Boolean(raw.confirmation_active ?? raw.confirmationActive),
    signals: normalizeRiskSignals(raw.signals),
    metrics: asRecord(raw.metrics),
    sources: asRecord(raw.sources),
    updatedAt: asString(raw.updated_at ?? raw.updatedAt),
  };
}

function normalizeMarketTopRiskHistoryPoint(rawValue: unknown): MarketTopRiskHistoryPoint | null {
  const raw = asRecord(rawValue);
  const week = asString(raw.week);
  if (!week) return null;
  return {
    week,
    nasdaq100: asNullableNumber(raw.nasdaq100),
    breadthWeaknessScore: asNullableNumber(raw.breadth_weakness_score ?? raw.breadthWeaknessScore),
    breakageScore: asNullableNumber(raw.breakage_score ?? raw.breakageScore),
    riskScore: asNumber(raw.risk_score ?? raw.riskScore),
    riskLevel: normalizeRiskLevel(raw.risk_level ?? raw.riskLevel),
    warningActive: Boolean(raw.warning_active ?? raw.warningActive),
    confirmationActive: Boolean(raw.confirmation_active ?? raw.confirmationActive),
    signals: normalizeRiskSignals(raw.signals),
    metrics: asRecord(raw.metrics),
  };
}

function normalizePaged<T>(
  rawValue: unknown,
  normalizeRow: (value: unknown) => T,
): PagedResult<T> {
  const raw = asRecord(rawValue);
  const rows = asArray(raw.rows).map(normalizeRow);
  const page = asNumber(raw.page, 1);
  const pageSize = asNumber(raw.pageSize ?? raw.page_size, rows.length || 1);
  const total = asNumber(raw.total, rows.length);

  return {
    rows,
    total,
    page,
    pageSize,
    totalPages: Math.max(1, asNumber(raw.totalPages ?? raw.total_pages, Math.ceil(total / pageSize))),
  };
}

function mapAccountRow(item: any): AccountListItem {
  return {
    id: String(item.id),
    username: String(item.username),
    displayName: String(item.display_name || item.displayName || item.username),
    profileUrl: String(item.profile_url || item.profileUrl || ""),
    subscribed: Boolean(item.subscribed),
    backfillCompletedAt: item.backfill_completed_at || item.backfillCompletedAt ? String(item.backfill_completed_at || item.backfillCompletedAt) : null,
  };
}

function mapAuthorRow(item: any): AuthorListItem {
  const accountName = String(item.account_name || item.accountName || item.username || "");
  const platform = String(item.platform || "x");
  return {
    accountId: String(item.account_id || item.accountId || item.id || ""),
    platform,
    accountKey: String(item.account_key || item.accountKey || makeAccountKey(platform, accountName)),
    accountName,
    authorNickname: String(item.author_nickname || item.authorNickname || item.display_name || accountName),
    profileUrl: String(item.profile_url || item.profileUrl || ""),
    latestDate: item.latest_date || item.latestDate ? String(item.latest_date || item.latestDate) : null,
    latestStatus: item.latest_status || item.latestStatus ? String(item.latest_status || item.latestStatus) : null,
    totalDays: Number(item.total_days || item.totalDays || 0),
    totalNotes: Number(item.total_notes || item.totalNotes || 0),
    updatedAt: item.updated_at || item.updatedAt ? String(item.updated_at || item.updatedAt) : null,
  };
}

function mapEntityRow(item: any): EntityListItem {
  return {
    key: String(item.entity_key || item.key || item.security_key || item.theme_key || ""),
    displayName: String(item.display_name || item.displayName || item.entity_key || item.key || ""),
    ticker: item.ticker ? String(item.ticker) : null,
    market: item.market ? String(item.market) : null,
    latestDate: item.latest_date || item.latestDate ? String(item.latest_date || item.latestDate) : null,
    mentionDays: Number(item.mention_days || item.mentionDays || 0),
    totalMentions: Number(item.total_mentions || item.totalMentions || item.mention_count || 0),
    updatedAt: item.updated_at || item.updatedAt ? String(item.updated_at || item.updatedAt) : null,
  };
}

export async function listAccounts(
  supabase: SupabaseClient,
  profile: UserProfile | null,
  query = "",
  domain: Domain = "stock",
): Promise<AccountListItem[]> {
  const { data, error } = await supabase.rpc("list_public_accounts", {
    query_arg: query,
    limit_arg: 100,
    domain_arg: domain,
  });
  assertNoError(error);

  const rows = (data || []).map(mapAccountRow);
  if (!profile) return rows;
  return rows;
}

export async function listVisibleAuthors(
  supabase: SupabaseClient,
  profile: UserProfile | null,
  query = "",
  limit = 100,
  domain: Domain = "stock",
): Promise<AuthorListItem[]> {
  const { data, error } = await supabase.rpc("list_visible_authors", {
    query_arg: query,
    limit_arg: profile ? limit : 1,
    domain_arg: domain,
  });
  assertNoError(error);
  return (data || []).map(mapAuthorRow);
}

export async function getVisibleAuthorTimeline(
  supabase: SupabaseClient,
  profile: UserProfile | null,
  accountId: string,
  page = 1,
  domain: Domain = "stock",
): Promise<AuthorDetailData | null> {
  if (!accountId) return null;
  const { data, error } = await supabase.rpc("get_visible_author_timeline", {
    account_id_arg: accountId,
    page_arg: page,
    page_size_arg: profile ? 20 : 3,
    domain_arg: domain,
  });
  assertNoError(error);

  const payload = asRecord(data);
  if (!payload.meta) return null;
  const meta = asRecord(payload.meta);
  const platform = asString(meta.platform, "x");
  const accountName = asString(meta.accountName ?? meta.account_name);

  return {
    accountId,
    platform,
    accountKey: makeAccountKey(platform, accountName),
    accountName,
    authorNickname: asString(meta.authorNickname ?? meta.author_nickname, accountName),
    authorId: asString(meta.authorId ?? meta.author_id),
    profileUrl: asString(meta.profileUrl ?? meta.profile_url),
    timeline: normalizePaged(payload.timeline, normalizeAuthorDay),
  } satisfies AuthorDetailData;
}

export async function listEntities(
  supabase: SupabaseClient,
  type: "stock" | "crypto",
  profile: UserProfile | null,
  query = "",
  limit = 100,
  sort: EntitySortKey = "date_desc",
): Promise<EntityListItem[]> {
  if (type === "crypto") {
    const { data, error } = await supabase.rpc("list_visible_crypto_entities", {
      query_arg: query,
      limit_arg: profile ? limit : 1,
      sort_arg: sort,
    });
    assertNoError(error);
    return (data || []).map(mapEntityRow);
  }
  const { data, error } = await supabase.rpc("list_visible_entities", {
    entity_type_arg: type,
    query_arg: query,
    limit_arg: profile ? limit : 1,
    sort_arg: sort,
  });
  assertNoError(error);
  return (data || []).map(mapEntityRow);
}

export async function getVisibleEntityTimeline(
  supabase: SupabaseClient,
  profile: UserProfile | null,
  type: "stock" | "crypto",
  entityKey: string,
  page = 1,
): Promise<EntityDetailData | null> {
  if (!entityKey) return null;
  if (type === "crypto") {
    const { data, error } = await supabase.rpc("get_visible_crypto_entity_timeline", {
      entity_key_arg: entityKey,
      page_arg: page,
      page_size_arg: profile ? 20 : 3,
    });
    assertNoError(error);

    const payload = asRecord(data);
    if (!payload.meta) return null;
    const meta = asRecord(payload.meta);
    return {
      key: asString(meta.key ?? meta.entityKey ?? meta.entity_key, entityKey),
      displayName: asString(meta.displayName ?? meta.display_name, entityKey),
      ticker: asNullableString(meta.ticker),
      market: asNullableString(meta.market),
      identifierType: asNullableString(meta.identifier_type ?? meta.identifierType),
      rawIdentifiers: normalizeStringArray(meta.raw_identifiers ?? meta.rawIdentifiers),
      normalizedStatus: asNullableString(meta.normalized_status ?? meta.normalizedStatus),
      timeline: normalizePaged(payload.timeline, normalizeEntityDay),
      chart: null,
    } satisfies EntityDetailData;
  }
  const { data, error } = await supabase.rpc("get_visible_entity_timeline", {
    entity_type_arg: type,
    entity_key_arg: entityKey,
    page_arg: page,
    page_size_arg: profile ? 20 : 3,
  });
  assertNoError(error);

  const payload = asRecord(data);
  if (!payload.meta) return null;
  const meta = asRecord(payload.meta);

  return {
    key: asString(meta.key ?? meta.entityKey ?? meta.entity_key, entityKey),
    displayName: asString(meta.displayName ?? meta.display_name, entityKey),
    ticker: asNullableString(meta.ticker),
    market: asNullableString(meta.market),
    identifierType: asNullableString(meta.identifier_type ?? meta.identifierType),
    rawIdentifiers: normalizeStringArray(meta.raw_identifiers ?? meta.rawIdentifiers),
    normalizedStatus: asNullableString(meta.normalized_status ?? meta.normalizedStatus),
    timeline: normalizePaged(payload.timeline, normalizeEntityDay),
    chart: type === "stock" ? normalizeStockChart(payload.chart) : null,
  } satisfies EntityDetailData;
}

export async function getVisibleCryptoMatrix(
  supabase: SupabaseClient,
  endDate: string | null = null,
  granularity: CryptoMatrixGranularity = "week",
): Promise<CryptoMatrixData> {
  const { data, error } = await supabase.rpc("get_visible_crypto_matrix", {
    end_date_arg: endDate || null,
    granularity_arg: granularity,
  });
  assertNoError(error);
  const payload = asRecord(data);
  return {
    startDate: asNullableString(payload.start_date ?? payload.startDate),
    endDate: asNullableString(payload.end_date ?? payload.endDate),
    previousEndDate: asNullableString(payload.previous_end_date ?? payload.previousEndDate),
    nextEndDate: asNullableString(payload.next_end_date ?? payload.nextEndDate),
    authors: asArray(payload.authors).map(normalizeStockMatrixAuthor),
    assets: asArray(payload.assets).map(normalizeCryptoMatrixAsset),
    cells: asArray(payload.cells).map(normalizeCryptoMatrixCell),
  };
}

export async function getVisibleStockMatrix(
  supabase: SupabaseClient,
  endDate: string | null = null,
  granularity: StockMatrixGranularity = "week",
): Promise<StockMatrixData> {
  const { data, error } = await supabase.rpc("get_visible_stock_matrix", {
    end_date_arg: endDate || null,
    granularity_arg: granularity,
  });
  assertNoError(error);
  const payload = asRecord(data);
  return {
    startDate: asNullableString(payload.start_date ?? payload.startDate),
    endDate: asNullableString(payload.end_date ?? payload.endDate),
    previousEndDate: asNullableString(payload.previous_end_date ?? payload.previousEndDate),
    nextEndDate: asNullableString(payload.next_end_date ?? payload.nextEndDate),
    authors: asArray(payload.authors).map(normalizeStockMatrixAuthor),
    stocks: asArray(payload.stocks).map(normalizeStockMatrixStock),
    cells: asArray(payload.cells).map(normalizeStockMatrixCell),
  };
}

export async function getVisibleStockNewsTimeline(
  supabase: SupabaseClient,
  profile: UserProfile | null,
  page = 1,
): Promise<StockNewsTimelineResponse> {
  const { data, error } = await supabase.rpc("get_visible_stock_news_timeline", {
    page_arg: page,
    page_size_arg: profile ? 5 : 3,
  });
  assertNoError(error);
  const payload = asRecord(data);
  return {
    timeline: normalizePaged(payload.timeline, normalizeStockNewsDay),
  };
}

export async function trackStockNewsEvent(
  supabase: SupabaseClient,
  event: StockNewsItem,
  date: string,
): Promise<void> {
  if (!event.eventKey) {
    throw new Error("这条新闻缺少 event_key，等待下一次新闻物化后再追踪。");
  }
  const { error } = await supabase.rpc("track_stock_news_event", {
    event_key_arg: event.eventKey,
    event_snapshot_arg: {
      date,
      event_key: event.eventKey,
      event_sort_order: event.eventSortOrder,
      note_id: event.noteId,
      note_url: event.noteUrl,
      account_name: event.accountName,
      author_nickname: event.authorNickname,
      publish_time: event.publishTime,
      headline: event.headline,
      event_summary: event.eventSummary,
      event_type: event.eventType,
      event_nature: event.eventNature,
      linked_entities: event.linkedEntities.map((entity) => ({
        entity_type: entity.entityType,
        entity_key: entity.entityKey,
        entity_name: entity.entityName,
        entity_code_or_name: entity.entityCodeOrName,
        metadata: entity.metadata,
      })),
      metadata: event.metadata,
    },
  });
  assertNoError(error);
}

export async function getStockNewsTracking(
  supabase: SupabaseClient,
  page = 1,
): Promise<StockNewsTrackingResponse> {
  const { data, error } = await supabase.rpc("get_stock_news_tracking", {
    page_arg: page,
    page_size_arg: 20,
  });
  assertNoError(error);
  const payload = asRecord(data);
  return {
    viewerIsAdmin: Boolean(payload.viewer_is_admin ?? payload.viewerIsAdmin),
    tracking: normalizePaged(payload.tracking, normalizeStockNewsTrackingItem),
  };
}

export async function deleteStockNewsTrackingStock(
  supabase: SupabaseClient,
  stockRowId: string,
): Promise<void> {
  const { error } = await supabase.rpc("delete_stock_news_tracking_stock", {
    stock_row_id_arg: stockRowId,
  });
  assertNoError(error);
}

export async function deleteStockNewsTrackingItem(
  supabase: SupabaseClient,
  trackingId: string,
): Promise<void> {
  const { error } = await supabase.rpc("delete_stock_news_tracking_item", {
    tracking_id_arg: trackingId,
  });
  assertNoError(error);
}

export async function getLatestStockNarrativeBrief(
  supabase: SupabaseClient,
): Promise<StockNarrativeBrief | null> {
  const { data, error } = await supabase.rpc("get_latest_stock_narrative_brief");
  assertNoError(error);
  const payload = asRecord(data);
  const id = asString(payload.id);
  const briefText = asString(payload.brief_text ?? payload.briefText);
  if (!id || !briefText) return null;
  return {
    id,
    briefDate: asString(payload.brief_date ?? payload.briefDate),
    windowStart: asNullableString(payload.window_start ?? payload.windowStart),
    windowEnd: asNullableString(payload.window_end ?? payload.windowEnd),
    previousWindowStart: asNullableString(payload.previous_window_start ?? payload.previousWindowStart),
    previousWindowEnd: asNullableString(payload.previous_window_end ?? payload.previousWindowEnd),
    baselineStart: asNullableString(payload.baseline_start ?? payload.baselineStart),
    baselineEnd: asNullableString(payload.baseline_end ?? payload.baselineEnd),
    inputDigest: asRecord(payload.input_digest ?? payload.inputDigest),
    sections: normalizeNarrativeSections(payload.sections),
    briefText,
    modelName: asNullableString(payload.model_name ?? payload.modelName),
    promptVersion: asString(payload.prompt_version ?? payload.promptVersion),
    usage: asRecord(payload.usage),
    createdAt: asNullableString(payload.created_at ?? payload.createdAt),
    updatedAt: asNullableString(payload.updated_at ?? payload.updatedAt),
  };
}

export async function getStockBloggerGoldRankings(
  supabase: SupabaseClient,
): Promise<StockBloggerGoldData> {
  const { data, error } = await supabase.rpc("get_stock_blogger_gold_rankings");
  assertNoError(error);
  const payload = asRecord(data);
  return {
    requiresLogin: Boolean(payload.requires_login ?? payload.requiresLogin),
    run: normalizeStockBloggerRun(payload.run),
    authors: asArray(payload.authors).map(normalizeStockBloggerAuthor),
  };
}

export async function getMarketTopRisk(
  supabase: SupabaseClient,
  historyLimit = 80,
): Promise<MarketTopRiskData> {
  const { data, error } = await supabase.rpc("get_market_top_risk", {
    history_limit_arg: historyLimit,
  });
  assertNoError(error);
  const payload = asRecord(data);
  const baseline = asRecord(payload.baseline);
  return {
    latest: normalizeMarketTopRiskSnapshot(payload.latest),
    history: asArray(payload.history)
      .map(normalizeMarketTopRiskHistoryPoint)
      .filter((item): item is MarketTopRiskHistoryPoint => item !== null),
    baseline: {
      nearHighFwd26wAvgDrawdown: asNullableNumber(baseline.near_high_fwd_26w_avg_drawdown),
      nearHighFwd26wDd10Probability: asNullableNumber(baseline.near_high_fwd_26w_dd10_probability),
      method: asString(baseline.method),
    },
  };
}

export async function listMyRequests(
  supabase: SupabaseClient,
  profile: UserProfile | null,
  domain: Domain = "stock",
): Promise<RequestListItem[]> {
  if (!profile) return [];
  const { data, error } = await supabase
    .from("account_requests")
    .select("id, status, raw_input, normalized_username, created_at")
    .eq("requester_id", profile.id)
    .eq("domain", domain)
    .order("created_at", { ascending: false })
    .limit(20);
  assertNoError(error);
  return (data || []).map(
    (item: any): RequestListItem => ({
      id: String(item.id),
      status: String(item.status),
      rawInput: String(item.raw_input),
      normalizedUsername: String(item.normalized_username),
      createdAt: String(item.created_at),
    }),
  );
}

export async function submitAccount(supabase: SupabaseClient, rawInput: string, domain: Domain = "stock") {
  const username = normalizeXUsername(rawInput);
  const { error } = await supabase.rpc("submit_x_account", {
    raw_input_arg: rawInput,
    username_arg: username,
    domain_arg: domain,
  });
  assertNoError(error);
}

export async function setSubscription(
  supabase: SupabaseClient,
  profile: UserProfile,
  accountId: string,
  subscribed: boolean,
  domain: Domain = "stock",
) {
  if (!profile.id) throw new Error("Authentication required.");
  const { error } = await supabase.rpc("set_x_account_subscription", {
    account_id_arg: accountId,
    subscribed_arg: subscribed,
    domain_arg: domain,
  });
  assertNoError(error);
}

export async function listFeed(
  supabase: SupabaseClient,
  profile: UserProfile | null,
  limit = 40,
  domain: Domain = "stock",
): Promise<FeedDay[]> {
  const { data, error } = await supabase.rpc("get_home_feed_preview", {
    limit_arg: limit,
    domain_arg: domain,
  });
  assertNoError(error);
  const payload = asRecord(data);
  return asArray(payload.rows).map(normalizeFeedDay);
}

export async function getHomeStats(
  supabase: SupabaseClient,
  domain: Domain = "stock",
): Promise<HomeStats> {
  const { data, error } = await supabase.rpc("get_home_stats", {
    domain_arg: domain,
  });
  assertNoError(error);
  const payload = asRecord(data);
  return {
    approvedCount: asNumber(payload.approved_count ?? payload.approvedCount),
    subscribedCount: asNumber(payload.subscribed_count ?? payload.subscribedCount),
  };
}

export async function listAdminDashboard(supabase: SupabaseClient, domain: Domain = "stock") {
  const [requests, accountCount, approvedAccounts, jobs] = await Promise.all([
    supabase
      .from("account_requests")
      .select("id, raw_input, normalized_username, created_at, requester_id, x_accounts(id, username, display_name, profile_url, status)")
      .eq("status", "pending")
      .eq("domain", domain)
      .order("created_at", { ascending: true })
      .limit(50),
    supabase
      .from("account_domains")
      .select("account_id", { count: "exact" })
      .eq("domain", domain)
      .eq("status", "approved")
      .limit(1),
    supabase
      .from("account_domains")
      .select("backfill_completed_at, x_accounts(id, username, display_name, profile_url)")
      .eq("domain", domain)
      .eq("status", "approved")
      .order("approved_at", { ascending: false, nullsFirst: false })
      .limit(100),
    supabase
      .from("crawl_jobs")
      .select("id, kind, status, summary, error_text, created_at, finished_at")
      .eq("domain", domain)
      .order("created_at", { ascending: false })
      .limit(20),
  ]);
  assertNoError(requests.error);
  assertNoError(accountCount.error);
  assertNoError(approvedAccounts.error);
  assertNoError(jobs.error);

  const requesterIds = Array.from(new Set((requests.data || []).map((item: any) => String(item.requester_id))));
  const { data: profiles, error: profileError } = requesterIds.length
    ? await supabase.from("profiles").select("id, email").in("id", requesterIds)
    : { data: [], error: null };
  assertNoError(profileError);
  const profileMap = new Map((profiles || []).map((item: any) => [String(item.id), String(item.email)]));

  return {
    approvedCount: accountCount.count || 0,
    approvedAccounts: (approvedAccounts.data || []).map((item: any): AdminAccountItem => {
      const account = Array.isArray(item.x_accounts) ? item.x_accounts[0] : item.x_accounts;
      return {
        id: String(account?.id || item.account_id || ""),
        username: String(account?.username || ""),
        displayName: String(account?.display_name || account?.username || ""),
        profileUrl: String(account?.profile_url || ""),
        backfillCompletedAt: item.backfill_completed_at ? String(item.backfill_completed_at) : null,
      };
    }),
    jobs: (jobs.data || []).map(
      (item: any): AdminJobItem => ({
        id: String(item.id),
        kind: String(item.kind),
        status: String(item.status),
        summary: String(item.summary || ""),
        errorText: item.error_text ? String(item.error_text) : null,
        createdAt: String(item.created_at),
        finishedAt: item.finished_at ? String(item.finished_at) : null,
      }),
    ),
    requests: (requests.data || []).map((item: any): AdminRequestItem => {
      const account = Array.isArray(item.x_accounts) ? item.x_accounts[0] : item.x_accounts;
      return {
        id: String(item.id),
        rawInput: String(item.raw_input),
        normalizedUsername: String(item.normalized_username),
        requesterEmail: profileMap.get(String(item.requester_id)) || "unknown",
        createdAt: String(item.created_at),
        account: {
          id: String(account?.id || ""),
          username: String(account?.username || item.normalized_username),
          displayName: String(account?.display_name || item.normalized_username),
          profileUrl: String(account?.profile_url || ""),
          status: String(account?.status || "pending"),
        },
      };
    }),
  };
}

export async function approveRequest(supabase: SupabaseClient, requestId: string) {
  const { error } = await supabase.rpc("approve_account_request", { request_id_arg: requestId });
  assertNoError(error);
}

export async function rejectRequest(supabase: SupabaseClient, requestId: string) {
  const { error } = await supabase.rpc("reject_account_request", { request_id_arg: requestId });
  assertNoError(error);
}

export async function disableAccount(supabase: SupabaseClient, accountId: string, domain: Domain = "stock") {
  const { error } = await supabase.rpc("disable_x_account", { account_id_arg: accountId, domain_arg: domain });
  assertNoError(error);
}

export async function enqueueManualCrawl(supabase: SupabaseClient, domain: Domain = "stock") {
  const { error } = await supabase.rpc("enqueue_manual_crawl", { domain_arg: domain });
  assertNoError(error);
}

export async function listCryptoAdminControls(supabase: SupabaseClient): Promise<CryptoAdminControls> {
  const { data, error } = await supabase.rpc("list_crypto_admin_controls");
  assertNoError(error);
  const payload = asRecord(data);
  const runtimeControl = asRecord(payload.runtime_control ?? payload.runtimeControl);
  const runtimeEnabled = runtimeControl.pipeline_enabled ?? runtimeControl.pipelineEnabled;
  return {
    runtimeControl: {
      domain: asString(runtimeControl.domain, "crypto") as Domain,
      pipelineEnabled: runtimeEnabled === undefined ? true : Boolean(runtimeEnabled),
      updatedAt: asNullableString(runtimeControl.updated_at ?? runtimeControl.updatedAt),
    },
    blockedTerms: asArray(payload.blocked_terms ?? payload.blockedTerms).map((item) => {
      const raw = asRecord(item);
      return {
        term: asString(raw.term),
        createdAt: asNullableString(raw.created_at ?? raw.createdAt),
        updatedAt: asNullableString(raw.updated_at ?? raw.updatedAt),
      };
    }),
    deletedAssets: asArray(payload.deleted_assets ?? payload.deletedAssets).map((item) => {
      const raw = asRecord(item);
      return {
        assetKey: asString(raw.asset_key ?? raw.assetKey),
        displayName: asString(raw.display_name ?? raw.displayName ?? raw.asset_key ?? raw.assetKey),
        reason: asString(raw.reason),
        createdAt: asNullableString(raw.created_at ?? raw.createdAt),
        updatedAt: asNullableString(raw.updated_at ?? raw.updatedAt),
      };
    }),
  };
}

export async function setDomainPipelineEnabled(
  supabase: SupabaseClient,
  domain: Domain,
  enabled: boolean,
): Promise<CryptoAdminControls["runtimeControl"]> {
  const { data, error } = await supabase.rpc("set_domain_pipeline_enabled", {
    domain_arg: domain,
    enabled_arg: enabled,
  });
  assertNoError(error);
  const raw = asRecord(data);
  return {
    domain: asString(raw.domain, domain) as Domain,
    pipelineEnabled: Boolean(raw.pipeline_enabled ?? raw.pipelineEnabled),
    updatedAt: asNullableString(raw.updated_at ?? raw.updatedAt),
  };
}

export async function addCryptoBlockedTerm(supabase: SupabaseClient, term: string) {
  const { error } = await supabase.rpc("add_crypto_blocked_term", {
    term_arg: term,
  });
  assertNoError(error);
}

export async function removeCryptoBlockedTerm(supabase: SupabaseClient, term: string) {
  const { error } = await supabase.rpc("remove_crypto_blocked_term", {
    term_arg: term,
  });
  assertNoError(error);
}

export async function adminDeleteCryptoAsset(supabase: SupabaseClient, assetKey: string, reason = "deleted_by_admin") {
  const { error } = await supabase.rpc("admin_delete_crypto_asset", {
    asset_key_arg: assetKey,
    reason_arg: reason,
  });
  assertNoError(error);
}
