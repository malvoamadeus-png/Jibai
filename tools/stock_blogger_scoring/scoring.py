from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from typing import Any

from .market import event_trading_day
from .models import AuthorScore, ScoringConfig, SignalEvent, StockAuthorScore, StockSignalMention


VALID_DIRECTIONS = {"positive", "negative"}
VALID_SIGNAL_TYPES = {"explicit_stance", "logic_based"}
VALID_JUDGMENT_TYPES = {"direct", "implied"}
INVALID_CONVICTIONS = {"none"}
CONVICTION_RANK = {"strong": 4, "medium": 3, "unknown": 2, "weak": 1, "none": 0}


def _stable_event_id(author: str, security_key: str, day: str, direction: str, tweet_ids: list[str]) -> str:
    digest = hashlib.sha1("|".join([author, security_key, day, direction, *sorted(tweet_ids)]).encode("utf-8")).hexdigest()
    return digest[:16]


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = value.strip()
        if text and text not in result:
            result.append(text)
    return result


def _best_conviction(values: list[str]) -> str:
    return max(values or ["unknown"], key=lambda value: CONVICTION_RANK.get(value, 0))


def _best_signal_type(values: list[str]) -> str:
    return "logic_based" if "logic_based" in values else "explicit_stance"


def _best_judgment_type(values: list[str]) -> str:
    return "direct" if "direct" in values else "implied"


def _first_known(values: list[str], default: str = "unknown") -> str:
    for value in values:
        if value and value != "unknown":
            return value
    return default


def _merge_text(values: list[str], *, limit: int = 3) -> str:
    return " / ".join(_unique(values)[:limit])


def _scoreable(mention: StockSignalMention) -> tuple[bool, str | None]:
    if not mention.security_key:
        return False, "missing_security_key"
    if mention.direction not in VALID_DIRECTIONS:
        return False, "non_directional"
    if mention.signal_type not in VALID_SIGNAL_TYPES:
        return False, "non_signal"
    if mention.judgment_type not in VALID_JUDGMENT_TYPES:
        return False, "invalid_judgment_type"
    if mention.conviction in INVALID_CONVICTIONS:
        return False, "no_conviction"
    return True, None


def _event_from_mentions(items: list[StockSignalMention], *, status: str = "scoreable", status_reason: str | None = None, direction: str | None = None) -> SignalEvent:
    ordered = sorted(items, key=lambda item: item.published_at)
    first = ordered[0]
    day = event_trading_day(first.published_at, first.market)
    event_direction = direction or first.direction
    tweet_ids = [item.tweet_id for item in ordered]
    return SignalEvent(
        event_id=_stable_event_id(first.author, first.security_key, day, event_direction, tweet_ids),
        author=first.author,
        author_name=first.author_name,
        security_key=first.security_key,
        display_name=first.display_name or first.stock_name,
        ticker=first.ticker or first.ticker_or_code,
        market=first.market or first.market_hint,
        event_trading_day=day,
        published_at=first.published_at,
        direction=event_direction,
        signal_type=_best_signal_type([item.signal_type for item in ordered if item.signal_type in VALID_SIGNAL_TYPES]),
        judgment_type=_best_judgment_type([item.judgment_type for item in ordered if item.judgment_type in VALID_JUDGMENT_TYPES]),
        conviction=_best_conviction([item.conviction for item in ordered]),
        evidence_type=_first_known([item.evidence_type for item in ordered]),
        time_horizons=_unique([item.time_horizon for item in ordered]),
        tweet_ids=tweet_ids,
        source_urls=_unique([item.tweet_url for item in ordered]),
        logic=_merge_text([item.logic for item in ordered]),
        evidence=_unique([item.evidence for item in ordered])[:5],
        raw_texts=_unique([item.raw_text for item in ordered])[:5],
        status=status,
        status_reason=status_reason,
        metadata={"merged_mention_count": len(ordered)},
    )


def build_signal_events(mentions: list[StockSignalMention]) -> list[SignalEvent]:
    valid_by_day: dict[tuple[str, str, str], list[StockSignalMention]] = defaultdict(list)
    events: list[SignalEvent] = []

    for mention in mentions:
        scoreable, reason = _scoreable(mention)
        if not scoreable:
            if mention.security_key:
                events.append(_event_from_mentions([mention], status="unscored", status_reason=reason))
            continue
        day = event_trading_day(mention.published_at, mention.market)
        valid_by_day[(mention.author, mention.security_key, day)].append(mention)

    for (_author, _security_key, _day), items in sorted(valid_by_day.items(), key=lambda pair: pair[0]):
        directions = {item.direction for item in items}
        if len(directions) > 1:
            events.append(_event_from_mentions(items, status="unscored", status_reason="mixed_same_day", direction="mixed"))
            continue
        direction = next(iter(directions))
        same_direction_items = [item for item in items if item.direction == direction]
        events.append(_event_from_mentions(same_direction_items, direction=direction))

    events.sort(key=lambda event: (event.author.casefold(), event.event_trading_day, event.security_key, event.published_at))
    return events


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _weighted_mean(values: list[tuple[float, float]]) -> float | None:
    total_weight = sum(weight for _value, weight in values)
    if total_weight <= 0:
        return None
    return sum(value * weight for value, weight in values) / total_weight


def _horizon_labels(config: ScoringConfig) -> list[str]:
    return [f"{horizon}d" for horizon in config.horizons]


def _contributor_value(event: SignalEvent, config: ScoringConfig) -> float:
    value = 0.0
    conviction_weight = config.conviction_weights.get(event.conviction, 1.0)
    for label, horizon_score in event.horizon_scores.items():
        if horizon_score.status != "scored" or horizon_score.score is None:
            continue
        value += horizon_score.score * config.horizon_weights.get(label, 0.0) * conviction_weight
    return value


def aggregate_author_scores(events: list[SignalEvent], config: ScoringConfig) -> list[AuthorScore]:
    by_author: dict[str, list[SignalEvent]] = defaultdict(list)
    for event in events:
        by_author[event.author].append(event)

    rows: list[AuthorScore] = []
    labels = _horizon_labels(config)
    for author, items in sorted(by_author.items(), key=lambda pair: pair[0].casefold()):
        author_name = items[0].author_name
        score_by_horizon: dict[str, float | None] = {}
        avg_directional_excess_by_horizon: dict[str, float | None] = {}
        matured_count_by_horizon: dict[str, int] = {}
        scored_day_count_by_horizon: dict[str, int] = {}
        pending_count_by_horizon: dict[str, int] = {}

        for label in labels:
            scored_by_day: dict[str, list[tuple[float, float]]] = defaultdict(list)
            excess_values: list[float] = []
            pending_count = 0
            for event in items:
                horizon_score = event.horizon_scores.get(label)
                if horizon_score is None:
                    continue
                if horizon_score.status == "pending":
                    pending_count += 1
                if horizon_score.status != "scored":
                    continue
                if horizon_score.score is not None:
                    scored_by_day[event.event_trading_day].append((horizon_score.score, config.conviction_weights.get(event.conviction, 1.0)))
                if horizon_score.directional_excess is not None:
                    excess_values.append(horizon_score.directional_excess)

            day_scores = [
                day_score
                for values in scored_by_day.values()
                if (day_score := _weighted_mean(values)) is not None
            ]
            score_by_horizon[label] = _mean(day_scores)
            avg_directional_excess_by_horizon[label] = _mean(excess_values)
            matured_count_by_horizon[label] = sum(len(values) for values in scored_by_day.values())
            scored_day_count_by_horizon[label] = len(day_scores)
            pending_count_by_horizon[label] = pending_count

        weighted_horizon_scores = [
            (score, config.horizon_weights.get(label, 0.0))
            for label, score in score_by_horizon.items()
            if score is not None
        ]
        overall = _weighted_mean(weighted_horizon_scores)
        scored_event_count = len(
            [
                event
                for event in items
                if any(score.status == "scored" for score in event.horizon_scores.values())
            ]
        )
        scored_day_count = len(
            {
                event.event_trading_day
                for event in items
                if any(score.status == "scored" for score in event.horizon_scores.values())
            }
        )

        non_null_scores = {label: score for label, score in score_by_horizon.items() if score is not None}
        best_horizon = max(non_null_scores, key=lambda label: non_null_scores[label]) if non_null_scores else None
        worst_horizon = min(non_null_scores, key=lambda label: non_null_scores[label]) if non_null_scores else None

        contributors = sorted(
            [
                {
                    "event_id": event.event_id,
                    "security_key": event.security_key,
                    "display_name": event.display_name,
                    "event_trading_day": event.event_trading_day,
                    "direction": event.direction,
                    "conviction": event.conviction,
                    "contribution": _contributor_value(event, config),
                    "source_urls": event.source_urls,
                    "logic": event.logic,
                }
                for event in items
                if any(score.status == "scored" for score in event.horizon_scores.values())
            ],
            key=lambda item: item["contribution"],
        )
        top_contributors = contributors[:3] + contributors[-3:] if len(contributors) > 6 else contributors
        top_contributors.sort(key=lambda item: item["contribution"], reverse=True)

        conviction_counts = Counter(event.conviction for event in items)
        rows.append(
            AuthorScore(
                author=author,
                author_name=author_name,
                event_count=len([event for event in items if event.status == "scoreable"]),
                scored_event_count=scored_event_count,
                scored_day_count=scored_day_count,
                overall_score=overall,
                score_by_horizon=score_by_horizon,
                avg_directional_excess_by_horizon=avg_directional_excess_by_horizon,
                matured_count_by_horizon=matured_count_by_horizon,
                scored_day_count_by_horizon=scored_day_count_by_horizon,
                pending_count_by_horizon=pending_count_by_horizon,
                positive_count=sum(1 for event in items if event.direction == "positive"),
                negative_count=sum(1 for event in items if event.direction == "negative"),
                conviction_counts=dict(conviction_counts),
                best_horizon=best_horizon,
                worst_horizon=worst_horizon,
                top_contributors=top_contributors,
            )
        )

    rows.sort(key=lambda row: (row.overall_score is None, -(row.overall_score or -999), row.author.casefold()))
    return rows


def aggregate_stock_author_scores(events: list[SignalEvent], config: ScoringConfig) -> list[StockAuthorScore]:
    by_pair: dict[tuple[str, str], list[SignalEvent]] = defaultdict(list)
    for event in events:
        by_pair[(event.author, event.security_key)].append(event)

    labels = _horizon_labels(config)
    rows: list[StockAuthorScore] = []
    for (author, security_key), items in sorted(by_pair.items(), key=lambda pair: pair[0]):
        score_by_horizon: dict[str, float | None] = {}
        avg_directional_excess_by_horizon: dict[str, float | None] = {}
        for label in labels:
            scores: list[tuple[float, float]] = []
            excess_values: list[float] = []
            for event in items:
                horizon_score = event.horizon_scores.get(label)
                if horizon_score is None or horizon_score.status != "scored":
                    continue
                if horizon_score.score is not None:
                    scores.append((horizon_score.score, config.conviction_weights.get(event.conviction, 1.0)))
                if horizon_score.directional_excess is not None:
                    excess_values.append(horizon_score.directional_excess)
            score_by_horizon[label] = _weighted_mean(scores)
            avg_directional_excess_by_horizon[label] = _mean(excess_values)
        rows.append(
            StockAuthorScore(
                author=author,
                security_key=security_key,
                display_name=items[0].display_name,
                event_count=len(items),
                score_by_horizon=score_by_horizon,
                avg_directional_excess_by_horizon=avg_directional_excess_by_horizon,
            )
        )
    return rows
