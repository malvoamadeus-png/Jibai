from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal


ReportStance = Literal["bull", "bear", "mention_only", "mixed"]


@dataclass(slots=True)
class AuditPost:
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
class StockMention:
    tweet_id: str
    published_at: str
    stock_name: str
    ticker_or_code: str | None
    market_hint: str | None
    stance: ReportStance
    direction: str
    judgment_type: str
    confidence: float
    viewpoint: str
    evidence: str
    tweet_url: str = ""
    raw_text: str = ""
    security_key: str = ""
    display_name: str = ""
    ticker: str | None = None
    market: str | None = None
    price_date: str | None = None
    price_close: float | None = None
    forward_returns: dict[str, float | None] = field(default_factory=dict)

    @property
    def date(self) -> str:
        return self.published_at[:10]


@dataclass(slots=True)
class Candle:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


@dataclass(slots=True)
class StockChart:
    security_key: str
    display_name: str
    ticker: str | None
    market: str | None
    source_label: str | None
    source_symbol: str | None
    message: str | None
    candles: list[Candle]
    mentions: list[StockMention]


@dataclass(slots=True)
class ScoreRow:
    security_key: str
    display_name: str
    ticker: str | None
    market: str | None
    signal_count: int
    mention_only_count: int
    hit_rate_1d: float | None
    hit_rate_5d: float | None
    hit_rate_20d: float | None
    avg_return_1d: float | None
    avg_return_5d: float | None
    avg_return_20d: float | None


@dataclass(slots=True)
class AuditResult:
    profile_url: str
    username: str
    run_dir: str
    started_at: datetime
    start_date: date
    end_date: date
    posts: list[AuditPost]
    mentions: list[StockMention]
    charts: list[StockChart]
    scores: list[ScoreRow]
    manifest: dict[str, Any]

