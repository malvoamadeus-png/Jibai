from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


TimelineStatus = Literal["has_update_today", "no_update_today", "crawl_failed"]
ViewEntityType = Literal["stock", "theme", "macro", "other"]
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
    stance: ViewStance = "unknown"
    direction: ViewDirection = "unknown"
    judgment_type: ViewJudgmentType = "unknown"
    conviction: ViewConviction = "unknown"
    evidence_type: ViewEvidenceType = "unknown"
    logic: str = ""
    evidence: str = ""
    time_horizon: ViewHorizon = "unspecified"
    sort_order: int = 0


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
    summary_text: str = ""
    key_points: list[str] = Field(default_factory=list)
    viewpoints: list[ViewpointRecord] = Field(default_factory=list)
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
    stance: ViewStance = "unknown"
    direction: ViewDirection = "unknown"
    judgment_type: ViewJudgmentType = "unknown"
    conviction: ViewConviction = "unknown"
    evidence_type: ViewEvidenceType = "unknown"
    logic: str = ""
    evidence: list[str] = Field(default_factory=list)
    note_ids: list[str] = Field(default_factory=list)
    note_urls: list[str] = Field(default_factory=list)
    time_horizons: list[ViewHorizon] = Field(default_factory=list)


class AuthorDayRecord(BaseModel):
    platform: str = "xiaohongshu"
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
    stance: ViewStance = "unknown"
    direction: ViewDirection = "unknown"
    judgment_type: ViewJudgmentType = "unknown"
    conviction: ViewConviction = "unknown"
    evidence_type: ViewEvidenceType = "unknown"
    logic: str = ""
    note_ids: list[str] = Field(default_factory=list)
    note_urls: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    time_horizons: list[ViewHorizon] = Field(default_factory=list)


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


class StockPriceCandle(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


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
    processed_note_ids: list[str] = Field(default_factory=list)
    crawl_results: list[CrawlAccountResult] = Field(default_factory=list)
    note_extracts: list[NoteExtractRecord] = Field(default_factory=list)
    author_summaries: list[AuthorDayRecord] = Field(default_factory=list)
    stock_views: list[StockDayRecord] = Field(default_factory=list)
    theme_views: list[ThemeDayRecord] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
