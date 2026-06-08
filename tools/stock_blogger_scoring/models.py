from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal


Direction = Literal["positive", "negative"]
SignalType = Literal["explicit_stance", "logic_based"]
JudgmentType = Literal["direct", "implied", "factual_only", "quoted", "mention_only", "unknown"]
Conviction = Literal["strong", "medium", "weak", "none", "unknown"]
TimeHorizon = Literal["short_term", "medium_term", "long_term", "unspecified"]
HorizonStatus = Literal["scored", "pending", "missing_price", "unsupported_benchmark", "unscored"]


@dataclass(frozen=True, slots=True)
class ScoringConfig:
    accounts: list[str] = field(default_factory=lambda: ["labubu_trader", "hicagr", "xiaomustock"])
    history_days: int = 90
    price_days: int = 180
    horizons: tuple[int, ...] = (1, 5, 20)
    horizon_weights: dict[str, float] = field(
        default_factory=lambda: {"1d": 0.20, "5d": 0.35, "20d": 0.45}
    )
    score_scales: dict[str, float] = field(
        default_factory=lambda: {"1d": 0.05, "5d": 0.10, "20d": 0.20}
    )
    conviction_weights: dict[str, float] = field(
        default_factory=lambda: {"strong": 1.25, "medium": 1.0, "unknown": 0.85, "weak": 0.65}
    )
    benchmark_symbol: str = "^IXIC"
    benchmark_fallback_symbol: str = "QQQ"
    a_share_benchmark_symbol: str = "000688"
    a_share_benchmark_fallback_symbol: str = "588000"
    a_share_benchmark_extra_symbols: list[str] = field(default_factory=list)
    min_ranked_events: int = 10
    full_confidence_events: int = 30


@dataclass(slots=True)
class BloggerPost:
    tweet_id: str
    author: str
    author_name: str
    text: str
    published_at: str
    url: str
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    views: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def published_date(self) -> str:
        return self.published_at[:10]


@dataclass(slots=True)
class StockSignalMention:
    tweet_id: str
    author: str
    author_name: str
    published_at: str
    tweet_url: str
    raw_text: str
    stock_name: str
    ticker_or_code: str | None
    market_hint: str | None
    direction: str
    signal_type: str
    judgment_type: str
    conviction: str
    evidence_type: str
    time_horizon: str
    confidence: float
    logic: str
    evidence: str
    security_key: str = ""
    display_name: str = ""
    ticker: str | None = None
    market: str | None = None
    normalized_status: str = "unknown"


@dataclass(frozen=True, slots=True)
class Candle:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


@dataclass(slots=True)
class HorizonScore:
    horizon: str
    status: HorizonStatus
    target_date: str | None = None
    target_price: float | None = None
    benchmark_target_price: float | None = None
    stock_return: float | None = None
    benchmark_return: float | None = None
    excess_return: float | None = None
    directional_excess: float | None = None
    score: float | None = None
    message: str | None = None


@dataclass(slots=True)
class SignalEvent:
    event_id: str
    author: str
    author_name: str
    security_key: str
    display_name: str
    ticker: str | None
    market: str | None
    event_trading_day: str
    published_at: str
    direction: str
    signal_type: str
    judgment_type: str
    conviction: str
    evidence_type: str
    time_horizons: list[str] = field(default_factory=list)
    tweet_ids: list[str] = field(default_factory=list)
    source_urls: list[str] = field(default_factory=list)
    logic: str = ""
    evidence: list[str] = field(default_factory=list)
    raw_texts: list[str] = field(default_factory=list)
    status: str = "scoreable"
    status_reason: str | None = None
    anchor_trading_day: str | None = None
    anchor_price: float | None = None
    benchmark_anchor_price: float | None = None
    anchor_price_kind: str | None = None
    benchmark_symbol: str | None = None
    benchmark_status: str | None = None
    horizon_scores: dict[str, HorizonScore] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AuthorScore:
    author: str
    author_name: str
    event_count: int
    scored_event_count: int
    scored_day_count: int
    overall_score: float | None
    score_by_horizon: dict[str, float | None] = field(default_factory=dict)
    avg_directional_excess_by_horizon: dict[str, float | None] = field(default_factory=dict)
    matured_count_by_horizon: dict[str, int] = field(default_factory=dict)
    scored_day_count_by_horizon: dict[str, int] = field(default_factory=dict)
    pending_count_by_horizon: dict[str, int] = field(default_factory=dict)
    positive_count: int = 0
    negative_count: int = 0
    conviction_counts: dict[str, int] = field(default_factory=dict)
    best_horizon: str | None = None
    worst_horizon: str | None = None
    top_contributors: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class StockAuthorScore:
    author: str
    security_key: str
    display_name: str
    event_count: int
    score_by_horizon: dict[str, float | None] = field(default_factory=dict)
    avg_directional_excess_by_horizon: dict[str, float | None] = field(default_factory=dict)


@dataclass(slots=True)
class ScoringRunResult:
    run_dir: str
    started_at: datetime
    start_date: date
    end_date: date
    config: ScoringConfig
    posts: list[BloggerPost]
    mentions: list[StockSignalMention]
    events: list[SignalEvent]
    author_scores: list[AuthorScore]
    stock_author_scores: list[StockAuthorScore]
    manifest: dict[str, Any]
