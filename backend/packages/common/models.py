from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


TimelineStatus = Literal["has_update_today", "no_update_today", "crawl_failed"]
AnalysisDomain = Literal["stock", "crypto"]
ViewEntityType = Literal["stock", "theme", "macro", "other", "crypto_entity"]
EventEntityType = Literal["stock", "theme"]
ViewStance = Literal[
    "strong_bullish",
    "bullish",
    "neutral",
    "bearish",
    "strong_bearish",
    "mixed",
    "mention_only",
    "unknown",
]
ViewDirection = Literal["positive", "negative", "neutral", "mixed", "unknown"]
ViewSignalType = Literal["explicit_stance", "logic_based", "informational", "mention_signal", "unknown"]
ViewJudgmentType = Literal[
    "direct",
    "implied",
    "factual_only",
    "quoted",
    "mention_only",
    "unknown",
]
ViewConviction = Literal["strong", "medium", "weak", "none", "unknown"]
ViewEvidenceType = Literal[
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
    "onchain",
    "tokenomics",
    "unlock",
    "ecosystem",
    "protocol_revenue",
    "catalyst",
    "listing",
    "liquidity",
    "funding_rate",
    "security_incident",
    "regulation",
    "other",
    "unknown",
]
ViewHorizon = Literal["short_term", "medium_term", "long_term", "unspecified"]


class RawNoteRecord(BaseModel):
    platform: str = "xiaohongshu"
    account_name: str
    profile_url: str
    note_id: str
    url: str
    title: str = ""
    desc: str = ""
    author_id: str = ""
    author_nickname: str = ""
    note_type: str = ""
    publish_time: str | None = None
    last_update_time: str | None = None
    like_count: int | None = None
    collect_count: int | None = None
    comment_count: int | None = None
    share_count: int | None = None
    fetched_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class CrawlAccountResult(BaseModel):
    platform: str = "xiaohongshu"
    account_name: str
    profile_url: str
    run_at: str
    status: Literal["success", "failed"]
    candidate_count: int = 0
    new_note_count: int = 0
    fetched_note_ids: list[str] = Field(default_factory=list)
    error: str | None = None


class ViewpointRecord(BaseModel):
    entity_type: ViewEntityType
    entity_key: str = ""
    entity_name: str
    entity_code_or_name: str | None = None
    entity_identifier_type: str = "unknown"
    raw_identifiers: list[str] = Field(default_factory=list)
    normalized_status: str = "canonical"
    source_signal_level: str = "strong"
    stance: ViewStance = "unknown"
    direction: ViewDirection = "unknown"
    signal_type: ViewSignalType = "unknown"
    judgment_type: ViewJudgmentType = "unknown"
    conviction: ViewConviction = "unknown"
    evidence_type: ViewEvidenceType = "unknown"
    logic: str = ""
    evidence: str = ""
    time_horizon: ViewHorizon = "unspecified"
    sort_order: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class EventLinkedEntity(BaseModel):
    entity_type: EventEntityType
    entity_key: str = ""
    entity_name: str
    entity_code_or_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EventRecord(BaseModel):
    headline: str
    event_summary: str = ""
    event_type: str = "other"
    event_nature: str = "reported"
    evidence: str = ""
    sort_order: int = 0
    linked_entities: list[EventLinkedEntity] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class NoteExtractRecord(BaseModel):
    platform: str = "xiaohongshu"
    note_id: str
    account_name: str
    profile_url: str
    note_url: str
    note_title: str = ""
    note_desc: str = ""
    author_id: str = ""
    author_nickname: str = ""
    publish_time: str | None = None
    date: str
    extracted_at: str
    analysis_version: str = "viewpoints_v2"
    analysis_domain: AnalysisDomain = "stock"
    summary_text: str = ""
    key_points: list[str] = Field(default_factory=list)
    viewpoints: list[ViewpointRecord] = Field(default_factory=list)
    events: list[EventRecord] = Field(default_factory=list)
    model_name: str | None = None
    request_id: str | None = None
    usage: dict[str, int] = Field(default_factory=dict)
    raw_response: dict[str, Any] = Field(default_factory=dict)


class AuthorTimelineNote(BaseModel):
    note_id: str
    url: str
    title: str = ""
    publish_time: str | None = None


class AuthorDayViewpoint(BaseModel):
    entity_type: ViewEntityType
    entity_key: str
    entity_name: str
    entity_identifier_type: str = "unknown"
    raw_identifiers: list[str] = Field(default_factory=list)
    normalized_status: str = "canonical"
    source_signal_level: str = "strong"
    stance: ViewStance = "unknown"
    direction: ViewDirection = "unknown"
    signal_type: ViewSignalType = "unknown"
    judgment_type: ViewJudgmentType = "unknown"
    conviction: ViewConviction = "unknown"
    evidence_type: ViewEvidenceType = "unknown"
    logic: str = ""
    evidence: list[str] = Field(default_factory=list)
    note_ids: list[str] = Field(default_factory=list)
    note_urls: list[str] = Field(default_factory=list)
    time_horizons: list[ViewHorizon] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuthorDayRecord(BaseModel):
    platform: str = "xiaohongshu"
    analysis_domain: AnalysisDomain = "stock"
    date: str
    account_name: str
    profile_url: str
    author_id: str = ""
    author_nickname: str = ""
    status: TimelineStatus
    note_count_today: int
    summary_text: str
    note_ids: list[str] = Field(default_factory=list)
    notes: list[AuthorTimelineNote] = Field(default_factory=list)
    viewpoints: list[AuthorDayViewpoint] = Field(default_factory=list)
    mentioned_stocks: list[str] = Field(default_factory=list)
    mentioned_themes: list[str] = Field(default_factory=list)
    mentioned_crypto: list[str] = Field(default_factory=list)
    content_hash: str = ""
    updated_at: str


class AuthorTimelineFile(BaseModel):
    account_name: str
    profile_url: str
    author_id: str = ""
    author_nickname: str = ""
    records: list[AuthorDayRecord] = Field(default_factory=list)


class EntityAuthorView(BaseModel):
    platform: str = ""
    account_name: str
    author_nickname: str = ""
    entity_identifier_type: str = "unknown"
    raw_identifiers: list[str] = Field(default_factory=list)
    normalized_status: str = "canonical"
    source_signal_level: str = "strong"
    stance: ViewStance = "unknown"
    direction: ViewDirection = "unknown"
    signal_type: ViewSignalType = "unknown"
    judgment_type: ViewJudgmentType = "unknown"
    conviction: ViewConviction = "unknown"
    evidence_type: ViewEvidenceType = "unknown"
    logic: str = ""
    note_ids: list[str] = Field(default_factory=list)
    note_urls: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    time_horizons: list[ViewHorizon] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class StockDayRecord(BaseModel):
    date: str
    stock_code_or_name: str
    stock_name: str | None = None
    mention_count: int
    author_views: list[EntityAuthorView] = Field(default_factory=list)
    content_hash: str = ""
    updated_at: str


class StockTimelineFile(BaseModel):
    stock_code_or_name: str
    stock_name: str | None = None
    records: list[StockDayRecord] = Field(default_factory=list)


class NewsTimelineItem(BaseModel):
    note_id: str
    note_url: str = ""
    note_title: str = ""
    account_name: str
    author_nickname: str = ""
    publish_time: str | None = None
    headline: str
    event_summary: str = ""
    event_type: str = "other"
    event_nature: str = "reported"
    evidence: str = ""
    linked_entities: list[EventLinkedEntity] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class NewsTimelineDay(BaseModel):
    date: str
    event_count: int
    events: list[NewsTimelineItem] = Field(default_factory=list)
    content_hash: str = ""
    updated_at: str


class CryptoEntityIdentity(BaseModel):
    asset_key: str
    display_name: str
    symbol: str | None = None
    identifier_type: str = "unknown"
    raw_identifiers: list[str] = Field(default_factory=list)
    contract_addresses: list[str] = Field(default_factory=list)
    x_accounts: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    chain: str | None = None
    normalized_status: str = "temporary"


class CryptoDayRecord(BaseModel):
    date: str
    asset_key: str
    display_name: str
    symbol: str | None = None
    mention_count: int
    author_views: list[EntityAuthorView] = Field(default_factory=list)
    content_hash: str = ""
    updated_at: str


class CryptoTimelineFile(BaseModel):
    asset_key: str
    display_name: str
    records: list[CryptoDayRecord] = Field(default_factory=list)


class StockPriceCandle(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


class MarketTopRiskSnapshot(BaseModel):
    week: str
    nasdaq100: float | None = None
    ndx_dd_from_52w_high: float | None = None
    breadth_weakness_score: float | None = None
    breakage_score: float | None = None
    risk_score: float
    risk_level: Literal["low", "watch", "elevated", "high"]
    warning_active: bool
    confirmation_active: bool
    signals: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    sources: dict[str, Any] = Field(default_factory=dict)


class ThemeDayRecord(BaseModel):
    date: str
    theme_key: str
    theme_name: str
    mention_count: int
    author_views: list[EntityAuthorView] = Field(default_factory=list)
    content_hash: str = ""
    updated_at: str


class ThemeTimelineFile(BaseModel):
    theme_key: str
    theme_name: str
    records: list[ThemeDayRecord] = Field(default_factory=list)


class AnalysisSnapshot(BaseModel):
    run_id: str
    run_at: str
    analysis_domain: AnalysisDomain = "stock"
    processed_note_ids: list[str] = Field(default_factory=list)
    crawl_results: list[CrawlAccountResult] = Field(default_factory=list)
    note_extracts: list[NoteExtractRecord] = Field(default_factory=list)
    author_summaries: list[AuthorDayRecord] = Field(default_factory=list)
    stock_views: list[StockDayRecord] = Field(default_factory=list)
    stock_news: list[NewsTimelineDay] = Field(default_factory=list)
    theme_views: list[ThemeDayRecord] = Field(default_factory=list)
    crypto_views: list[CryptoDayRecord] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
