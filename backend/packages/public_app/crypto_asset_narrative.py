from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable, Sequence

from psycopg.types.json import Jsonb

from packages.ai.prompts import (
    CRYPTO_ASSET_BRIEF_REQUIRED_KEYS,
    CRYPTO_CA_MATCH_REQUIRED_KEYS,
    CRYPTO_KEYWORD_EXPANSION_REQUIRED_KEYS,
    build_crypto_asset_brief_messages,
    build_crypto_asset_keyword_messages,
    build_crypto_ca_match_messages,
)
from packages.common.postgres_database import postgres_connection
from packages.common.settings import load_settings
from packages.common.time_utils import SHANGHAI_TZ
from packages.onchain.gmgn_labels import OKXTokenSearchCandidate, search_token_candidates
from packages.onchain.okx_client import OKXWeb3Client

from .x_search import XSearchResult, XSearchTweet, search_x_posts


PROMPT_VERSION = "crypto_asset_narrative_v2"
MAX_NAME_GROUP_TWEETS = 20
MAX_CANDIDATE_GROUP_TWEETS = 20
MAX_SUMMARY_TWEETS = 50
MAX_CANDIDATES = 5
MIN_MATCH_SAMPLE_COUNT = 3
LOW_SAMPLE_CAP = 0.74
MATCH_CONFIDENCE_THRESHOLD = 0.75
SUMMARY_MIN_TWEETS = 3
IDENTITY_STATUS_ANCHORED = "anchored"
IDENTITY_STATUS_FUZZY = "fuzzy"
IDENTITY_STATUS_AMBIGUOUS = "ambiguous"
_COMMON_WORD_HINTS = {
    "aeon",
    "base",
    "beam",
    "fuel",
    "mode",
    "mint",
    "pitch",
    "spark",
    "surplus",
}

_EVM_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
_SOLANA_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_/\-]{2,24}|[\u4e00-\u9fff]{2,12}")
_STOPWORDS = {
    "https",
    "http",
    "www",
    "com",
    "status",
    "token",
    "coin",
    "project",
    "crypto",
    "official",
    "today",
    "this",
    "that",
    "from",
    "with",
    "about",
    "have",
    "your",
    "they",
    "their",
    "what",
    "when",
    "where",
    "which",
    "just",
    "more",
    "some",
    "into",
    "like",
    "than",
    "已经",
    "这个",
    "那个",
    "一个",
    "我们",
    "他们",
    "项目",
    "代币",
    "叙事",
    "社区",
    "讨论",
    "用户",
    "现在",
    "今天",
}


@dataclass(frozen=True, slots=True)
class CryptoAssetBriefTarget:
    asset_key: str
    display_name: str
    symbol: str
    chain: str
    identifier_type: str
    aliases: list[str]
    raw_identifiers: list[str]
    contract_addresses: list[str]
    x_accounts: list[str]
    first_seen_date: str
    latest_seen_date: str
    mention_count: int


@dataclass(frozen=True, slots=True)
class SearchGroup:
    label: str
    queries: list[str]
    tweets: list[XSearchTweet]
    warning_messages: list[str]
    error_messages: list[str]


@dataclass(frozen=True, slots=True)
class ExistingCAResolution:
    contract_address: str
    chain_index: str
    status: str
    resolved_by: str


@dataclass(frozen=True, slots=True)
class CandidateDecision:
    candidate: OKXTokenSearchCandidate
    overlap: dict[str, Any]
    same_project: bool
    confidence: float
    shared_signals: list[str]
    reason: str
    passes: bool
    name_sample_count: int
    candidate_sample_count: int


@dataclass(frozen=True, slots=True)
class BlockedAssetMatch:
    term: str
    source_field: str


@dataclass(frozen=True, slots=True)
class IdentityAssessment:
    status: str
    reasons: list[str]
    official_account_match: bool
    dominant_cluster_ratio: float
    cluster_count: int
    overlapping_candidate_count: int
    matched_stable_aliases: list[str]
    ambiguous_name: bool


def _clip(value: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _normalize_query(value: str) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_account(value: str) -> str:
    return str(value or "").strip().lstrip("@").lower()


def _tweet_text(tweet: XSearchTweet) -> str:
    return " ".join(
        part
        for part in [
            tweet.author,
            tweet.author_name,
            tweet.text,
            tweet.title,
            tweet.snippet,
        ]
        if part
    )


def _tweet_score(tweet: XSearchTweet) -> tuple[int, int, int]:
    return (tweet.likes + tweet.retweets + tweet.replies, tweet.views, len(tweet.text))


def _unique_extend(target: list[str], values: Iterable[str]) -> None:
    seen = {item.lower(): item for item in target}
    for raw in values:
        value = str(raw or "").strip()
        if not value:
            continue
        key = value.lower()
        if key not in seen:
            target.append(value)
            seen[key] = value


def _is_contract_address(value: str) -> bool:
    text = str(value or "").strip()
    return bool(_EVM_RE.fullmatch(text) or _SOLANA_RE.fullmatch(text))


def _normalized_contract(value: str) -> str:
    text = str(value or "").strip()
    if _EVM_RE.fullmatch(text):
        return text.lower()
    return text


def _coerce_contracts(values: Iterable[str]) -> list[str]:
    output: list[str] = []
    for raw in values:
        if not _is_contract_address(raw):
            continue
        contract = _normalized_contract(raw)
        if contract not in output:
            output.append(contract)
    return output


def _normalize_blocked_term(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _asset_text_fields(asset: CryptoAssetBriefTarget) -> list[tuple[str, str]]:
    fields: list[tuple[str, str]] = [
        ("asset_key", asset.asset_key),
        ("display_name", asset.display_name),
        ("symbol", asset.symbol),
    ]
    fields.extend(("alias", alias) for alias in asset.aliases)
    return [(label, str(value or "").strip()) for label, value in fields if str(value or "").strip()]


def _fetch_blocked_terms(conn: Any) -> list[str]:
    if not hasattr(conn, "execute"):
        return []
    rows = conn.execute(
        """
        select term
        from crypto_asset_blocklist
        order by term asc
        """
    ).fetchall()
    return [_normalize_blocked_term(row["term"]) for row in rows if _normalize_blocked_term(row["term"])]


def _find_blocked_match(asset: CryptoAssetBriefTarget, blocked_terms: Sequence[str]) -> BlockedAssetMatch | None:
    normalized_terms = [term for term in (_normalize_blocked_term(item) for item in blocked_terms) if term]
    if not normalized_terms:
        return None
    for field_name, field_value in _asset_text_fields(asset):
        lowered = field_value.lower()
        for term in normalized_terms:
            if term in lowered:
                return BlockedAssetMatch(term=term, source_field=field_name)
    return None


def _asset_alias_pool(asset: CryptoAssetBriefTarget) -> list[str]:
    values: list[str] = []
    _unique_extend(values, [asset.display_name, asset.symbol, *asset.aliases])
    return values


def _group_authors(group: SearchGroup) -> set[str]:
    return {_normalize_account(tweet.author or tweet.author_name) for tweet in group.tweets if tweet.author or tweet.author_name}


def _tokenize_for_overlap(text: str) -> list[str]:
    tokens: list[str] = []
    for token in _TOKEN_RE.findall(text or ""):
        lowered = token.lower()
        if lowered in _STOPWORDS:
            continue
        if len(lowered) <= 1:
            continue
        tokens.append(lowered)
    return tokens


def _keyword_counter(tweets: Sequence[XSearchTweet], *, ignored_tokens: set[str]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for tweet in tweets:
        for token in _tokenize_for_overlap(_tweet_text(tweet)):
            if token in ignored_tokens:
                continue
            counter[token] += 1
    return counter


def _top_keywords(tweets: Sequence[XSearchTweet], *, ignored_tokens: set[str], minimum_count: int = 1) -> list[str]:
    counter = _keyword_counter(tweets, ignored_tokens=ignored_tokens)
    return [
        token
        for token, count in counter.most_common(12)
        if count >= minimum_count
    ]


def _shared_aliases(asset: CryptoAssetBriefTarget, group: SearchGroup) -> list[str]:
    haystack = " ".join(_tweet_text(tweet).lower() for tweet in group.tweets)
    matched: list[str] = []
    for alias in _asset_alias_pool(asset):
        alias_text = alias.strip()
        if alias_text and alias_text.lower() in haystack and alias_text not in matched:
            matched.append(alias_text)
    return matched


def _stable_aliases(asset: CryptoAssetBriefTarget) -> list[str]:
    values: list[str] = []
    skipped = {asset.display_name.lower(), asset.symbol.lower()}
    for alias in asset.aliases:
        cleaned = alias.strip()
        if not cleaned or cleaned.lower() in skipped:
            continue
        collapsed = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", "", cleaned)
        if cleaned.isascii() and len(collapsed) < 4:
            continue
        if cleaned not in values:
            values.append(cleaned)
    return values


def _matched_stable_aliases(asset: CryptoAssetBriefTarget, group: SearchGroup) -> list[str]:
    haystack = " ".join(_tweet_text(tweet).lower() for tweet in group.tweets)
    matched: list[str] = []
    for alias in _stable_aliases(asset):
        if alias.lower() in haystack and alias not in matched:
            matched.append(alias)
    return matched


def _has_official_account_match(asset: CryptoAssetBriefTarget, group: SearchGroup) -> bool:
    official_accounts = {_normalize_account(account) for account in asset.x_accounts if _normalize_account(account)}
    if not official_accounts:
        return False
    authors = {
        _normalize_account(tweet.author or tweet.author_name)
        for tweet in group.tweets
        if tweet.author or tweet.author_name
    }
    return bool(official_accounts & authors)


def _tweet_topic_tokens(tweet: XSearchTweet, *, ignored_tokens: set[str]) -> set[str]:
    return {
        token
        for token in _tokenize_for_overlap(_tweet_text(tweet))
        if token not in ignored_tokens
    }


def _tweet_cluster_sizes(tweets: Sequence[XSearchTweet], *, ignored_tokens: set[str]) -> list[int]:
    if not tweets:
        return []

    parent = list(range(len(tweets)))
    token_sets = [_tweet_topic_tokens(tweet, ignored_tokens=ignored_tokens) for tweet in tweets]
    authors = [_normalize_account(tweet.author or tweet.author_name) for tweet in tweets]

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left in range(len(tweets)):
        for right in range(left + 1, len(tweets)):
            same_author = bool(authors[left] and authors[left] == authors[right])
            shared_tokens = token_sets[left] & token_sets[right]
            if same_author or len(shared_tokens) >= 2:
                union(left, right)

    cluster_sizes: Counter[int] = Counter(find(index) for index in range(len(tweets)))
    return sorted(cluster_sizes.values(), reverse=True)


def _looks_like_ambiguous_name(asset: CryptoAssetBriefTarget) -> bool:
    symbol = asset.symbol.strip().lower()
    display_name = asset.display_name.strip().lower()
    if symbol.isalpha() and 0 < len(symbol) <= 5:
        return True
    for raw in [display_name, *[alias.strip().lower() for alias in asset.aliases]]:
        if not raw:
            continue
        if raw in _COMMON_WORD_HINTS:
            return True
    return False


def _assess_identity_status(
    asset: CryptoAssetBriefTarget,
    *,
    name_group: SearchGroup,
    resolution: ExistingCAResolution | None,
    decisions: Sequence[CandidateDecision],
) -> IdentityAssessment:
    if resolution is not None:
        return IdentityAssessment(
            status=IDENTITY_STATUS_ANCHORED,
            reasons=[f"resolved_by:{resolution.resolved_by or resolution.status}"],
            official_account_match=_has_official_account_match(asset, name_group),
            dominant_cluster_ratio=1.0,
            cluster_count=1 if name_group.tweets else 0,
            overlapping_candidate_count=sum(1 for decision in decisions if decision.overlap.get("has_overlap")),
            matched_stable_aliases=_matched_stable_aliases(asset, name_group),
            ambiguous_name=_looks_like_ambiguous_name(asset),
        )

    ignored_tokens = {
        token.lower()
        for token in [asset.display_name, asset.symbol]
        if token
    }
    cluster_sizes = _tweet_cluster_sizes(name_group.tweets, ignored_tokens=ignored_tokens)
    dominant_cluster_ratio = (cluster_sizes[0] / len(name_group.tweets)) if name_group.tweets and cluster_sizes else 0.0
    official_account_match = _has_official_account_match(asset, name_group)
    matched_aliases = _matched_stable_aliases(asset, name_group)
    ambiguous_name = _looks_like_ambiguous_name(asset)
    overlapping_candidate_count = sum(1 for decision in decisions if decision.overlap.get("has_overlap"))
    multi_clusters = sum(1 for size in cluster_sizes if size >= 2) > 1 and dominant_cluster_ratio < 0.75

    ambiguous_reasons: list[str] = []
    fuzzy_reasons: list[str] = []
    if official_account_match:
        fuzzy_reasons.append("official_account_match")
    if matched_aliases:
        fuzzy_reasons.append("matched_stable_aliases")
    if dominant_cluster_ratio >= 0.7 and len(name_group.tweets) >= SUMMARY_MIN_TWEETS:
        fuzzy_reasons.append(f"dominant_cluster:{dominant_cluster_ratio:.2f}")
    if ambiguous_name:
        ambiguous_reasons.append("ambiguous_name")
    if overlapping_candidate_count > 1:
        ambiguous_reasons.append(f"multiple_candidate_clusters:{overlapping_candidate_count}")
    if multi_clusters:
        ambiguous_reasons.append(f"multiple_tweet_clusters:{cluster_sizes}")

    if ambiguous_reasons and ("multiple_candidate_clusters" in "".join(ambiguous_reasons) or "multiple_tweet_clusters" in "".join(ambiguous_reasons)):
        return IdentityAssessment(
            status=IDENTITY_STATUS_AMBIGUOUS,
            reasons=ambiguous_reasons,
            official_account_match=official_account_match,
            dominant_cluster_ratio=dominant_cluster_ratio,
            cluster_count=len(cluster_sizes),
            overlapping_candidate_count=overlapping_candidate_count,
            matched_stable_aliases=matched_aliases,
            ambiguous_name=ambiguous_name,
        )
    if fuzzy_reasons:
        return IdentityAssessment(
            status=IDENTITY_STATUS_FUZZY,
            reasons=fuzzy_reasons,
            official_account_match=official_account_match,
            dominant_cluster_ratio=dominant_cluster_ratio,
            cluster_count=len(cluster_sizes),
            overlapping_candidate_count=overlapping_candidate_count,
            matched_stable_aliases=matched_aliases,
            ambiguous_name=ambiguous_name,
        )
    return IdentityAssessment(
        status=IDENTITY_STATUS_AMBIGUOUS,
        reasons=ambiguous_reasons or ["insufficient_anchor_signals"],
        official_account_match=official_account_match,
        dominant_cluster_ratio=dominant_cluster_ratio,
        cluster_count=len(cluster_sizes),
        overlapping_candidate_count=overlapping_candidate_count,
        matched_stable_aliases=matched_aliases,
        ambiguous_name=ambiguous_name,
    )


def _candidate_group_overlap(
    asset: CryptoAssetBriefTarget,
    name_group: SearchGroup,
    candidate_group: SearchGroup,
) -> dict[str, Any]:
    ignored = {token.lower() for token in _asset_alias_pool(asset) if token}
    shared_accounts = sorted(_group_authors(name_group) & _group_authors(candidate_group))
    shared_aliases = [alias for alias in _shared_aliases(asset, candidate_group) if alias in _shared_aliases(asset, name_group)]
    name_keywords = _top_keywords(name_group.tweets, ignored_tokens=ignored, minimum_count=1)
    candidate_keywords = _top_keywords(candidate_group.tweets, ignored_tokens=ignored, minimum_count=1)
    shared_keywords = [token for token in name_keywords if token in candidate_keywords][:6]
    shared_project_fragments = [
        value
        for value in [asset.display_name, asset.symbol]
        if value and value.lower() in " ".join(_tweet_text(tweet).lower() for tweet in candidate_group.tweets)
    ]
    return {
        "shared_accounts": shared_accounts,
        "shared_aliases": shared_aliases,
        "shared_keywords": shared_keywords,
        "shared_project_fragments": shared_project_fragments,
        "has_overlap": bool(shared_accounts or shared_aliases or shared_keywords or shared_project_fragments),
    }


def _sample_group_tweets(tweets: Sequence[XSearchTweet], *, limit: int = 8) -> list[dict[str, Any]]:
    seen_urls: set[str] = set()
    rows: list[dict[str, Any]] = []
    for tweet in sorted(tweets, key=_tweet_score, reverse=True):
        if tweet.url in seen_urls:
            continue
        seen_urls.add(tweet.url)
        rows.append(
            {
                "url": tweet.url,
                "author": tweet.author,
                "author_name": tweet.author_name,
                "text": _clip(tweet.text or tweet.snippet or tweet.title, 280),
                "created_at": tweet.created_at,
                "likes": tweet.likes,
                "retweets": tweet.retweets,
                "replies": tweet.replies,
                "views": tweet.views,
                "query_variant": tweet.query_variant,
            }
        )
        if len(rows) >= limit:
            break
    return rows


def _group_payload(asset: CryptoAssetBriefTarget, group: SearchGroup) -> dict[str, Any]:
    ignored = {token.lower() for token in _asset_alias_pool(asset) if token}
    return {
        "label": group.label,
        "queries": group.queries,
        "tweet_count": len(group.tweets),
        "authors": sorted(_group_authors(group)),
        "top_keywords": _top_keywords(group.tweets, ignored_tokens=ignored, minimum_count=1)[:8],
        "shared_aliases": _shared_aliases(asset, group),
        "samples": _sample_group_tweets(group.tweets, limit=8),
    }


def _aggregate_usage(total: dict[str, int], usage: dict[str, Any] | None) -> None:
    payload = usage or {}
    total["input_tokens"] = int(total.get("input_tokens", 0)) + _safe_int(payload.get("input_tokens"))
    total["output_tokens"] = int(total.get("output_tokens", 0)) + _safe_int(payload.get("output_tokens"))


def _model_settings() -> Any:
    settings = load_settings()
    return settings.model_copy(update={"model": "gpt-5.4-mini", "fallback_models": []})


def _build_name_queries(asset: CryptoAssetBriefTarget, expanded_keywords: Sequence[str]) -> list[str]:
    queries: list[str] = []
    _unique_extend(queries, [asset.display_name])
    if asset.symbol:
        _unique_extend(queries, [asset.symbol])
    _unique_extend(queries, [account for account in asset.x_accounts if account])
    _unique_extend(queries, asset.aliases)
    _unique_extend(queries, expanded_keywords)
    return [_normalize_query(item) for item in queries if _normalize_query(item)]


def _build_candidate_queries(asset: CryptoAssetBriefTarget, candidate: OKXTokenSearchCandidate | ExistingCAResolution) -> list[str]:
    contract_address = candidate.contract_address
    queries = [contract_address]
    if asset.display_name:
        queries.append(f'"{contract_address}" {asset.display_name}')
    if asset.symbol:
        queries.append(f'"{contract_address}" {asset.symbol}')
    return [_normalize_query(item) for item in queries if _normalize_query(item)]


def _search_group(label: str, queries: Sequence[str], *, group_limit: int) -> SearchGroup:
    tweets: list[XSearchTweet] = []
    warnings: list[str] = []
    errors: list[str] = []
    seen_urls: set[str] = set()
    per_query_limit = max(5, min(10, group_limit))
    for query in queries:
        if len(tweets) >= group_limit:
            break
        try:
            result = search_x_posts(query, limit=per_query_limit)
        except Exception as exc:
            errors.append(f"{query}: {_clip(str(exc), 160)}")
            continue
        if result.warning:
            warnings.append(f"{query}: {result.warning}")
        for tweet in result.tweets:
            if tweet.url in seen_urls:
                continue
            seen_urls.add(tweet.url)
            tweets.append(tweet)
            if len(tweets) >= group_limit:
                break
    return SearchGroup(
        label=label,
        queries=list(queries),
        tweets=tweets[:group_limit],
        warning_messages=warnings,
        error_messages=errors,
    )


def _candidate_strength_score(candidate: OKXTokenSearchCandidate) -> float:
    score = 0.0
    score += 1000.0 if candidate.community_recognized else 0.0
    score += math.log10(max(candidate.holder_count or 0.0, 1.0))
    score += math.log10(max(candidate.liquidity or 0.0, 1.0))
    score += math.log10(max(candidate.market_cap or 0.0, 1.0))
    return score


def _decide_candidate_pass(
    *,
    overlap: dict[str, Any],
    same_project: bool,
    confidence: float,
) -> bool:
    if not same_project or confidence < MATCH_CONFIDENCE_THRESHOLD:
        return False
    if overlap["shared_accounts"]:
        return True
    if len(overlap["shared_keywords"]) >= 2:
        return True
    if overlap["shared_aliases"]:
        return True
    return False


def _decision_rank_key(decision: CandidateDecision) -> tuple[float, int, float]:
    shared_count = (
        len(decision.overlap["shared_accounts"])
        + len(decision.overlap["shared_aliases"])
        + len(decision.overlap["shared_keywords"])
        + len(decision.overlap["shared_project_fragments"])
    )
    return (decision.confidence, shared_count, _candidate_strength_score(decision.candidate))


def _extract_existing_resolution(asset: CryptoAssetBriefTarget) -> ExistingCAResolution | None:
    contracts = _coerce_contracts([*asset.contract_addresses, *asset.raw_identifiers])
    if not contracts:
        return None
    return ExistingCAResolution(
        contract_address=contracts[0],
        chain_index="",
        status="existing_identifier",
        resolved_by="existing_identifier",
    )


def _search_okx_candidates(asset: CryptoAssetBriefTarget) -> list[OKXTokenSearchCandidate]:
    query_terms: list[str] = [asset.display_name]
    if asset.symbol:
        query_terms.append(asset.symbol)
    query_terms.extend(asset.aliases[:4])
    deduped_queries = [_normalize_query(item) for item in query_terms if _normalize_query(item)]
    unique: dict[tuple[str, str], OKXTokenSearchCandidate] = {}
    client = OKXWeb3Client.from_env()
    for query in deduped_queries:
        for candidate in search_token_candidates(client, query, limit=MAX_CANDIDATES):
            key = (candidate.chain_index, candidate.contract_address)
            if key not in unique:
                unique[key] = candidate
            if len(unique) >= MAX_CANDIDATES:
                break
        if len(unique) >= MAX_CANDIDATES:
            break
    return sorted(unique.values(), key=_candidate_strength_score, reverse=True)[:MAX_CANDIDATES]


def _generate_expanded_keywords(
    client: Any,
    asset: CryptoAssetBriefTarget,
    usage_totals: dict[str, int],
) -> list[str]:
    payload = {
        "asset_key": asset.asset_key,
        "display_name": asset.display_name,
        "symbol": asset.symbol,
        "aliases": asset.aliases,
        "x_accounts": asset.x_accounts,
        "chain": asset.chain,
    }
    result = client.generate_json(
        build_crypto_asset_keyword_messages(payload),
        required_keys=CRYPTO_KEYWORD_EXPANSION_REQUIRED_KEYS,
        max_tokens=300,
    )
    _aggregate_usage(usage_totals, result.usage)
    keywords = []
    for item in _string_list(result.parsed.get("keywords")):
        clean = _normalize_query(item)
        if clean and clean not in keywords:
            keywords.append(clean)
        if len(keywords) >= 5:
            break
    return keywords


def _match_candidate_with_ai(
    client: Any,
    *,
    asset: CryptoAssetBriefTarget,
    name_group: SearchGroup,
    candidate_group: SearchGroup,
    overlap: dict[str, Any],
    usage_totals: dict[str, int],
) -> tuple[bool, float, list[str], str]:
    name_count = len(name_group.tweets)
    candidate_count = len(candidate_group.tweets)
    if name_count < MIN_MATCH_SAMPLE_COUNT or candidate_count < MIN_MATCH_SAMPLE_COUNT:
        return False, 0.0, [], "sample_count_below_3"
    payload_left = _group_payload(asset, name_group)
    payload_right = _group_payload(asset, candidate_group)
    payload_right["cheap_overlap"] = overlap
    result = client.generate_json(
        build_crypto_ca_match_messages(payload_left, payload_right),
        required_keys=CRYPTO_CA_MATCH_REQUIRED_KEYS,
        max_tokens=700,
    )
    _aggregate_usage(usage_totals, result.usage)
    same_project = _safe_bool(result.parsed.get("same_project"))
    confidence = max(0.0, min(1.0, _safe_float(result.parsed.get("confidence"))))
    if name_count < 5 or candidate_count < 5:
        confidence = min(confidence, LOW_SAMPLE_CAP)
    shared_signals = _string_list(result.parsed.get("shared_signals"))
    reason = _clip(str(result.parsed.get("reason") or ""), 240)
    return same_project, confidence, shared_signals, reason


def _resolve_candidate_via_similarity(
    client: Any,
    *,
    asset: CryptoAssetBriefTarget,
    name_group: SearchGroup,
    usage_totals: dict[str, int],
) -> tuple[ExistingCAResolution | None, list[CandidateDecision], dict[str, SearchGroup]]:
    decisions: list[CandidateDecision] = []
    candidate_groups: dict[str, SearchGroup] = {}
    try:
        candidates = _search_okx_candidates(asset)
    except Exception as exc:
        return None, decisions, {"__error__": SearchGroup("candidate_error", [], [], [], [_clip(str(exc), 200)])}

    for candidate in candidates:
        queries = _build_candidate_queries(asset, candidate)
        candidate_group = _search_group(
            f"candidate:{candidate.contract_address}",
            queries,
            group_limit=MAX_CANDIDATE_GROUP_TWEETS,
        )
        candidate_groups[candidate.contract_address] = candidate_group
        overlap = _candidate_group_overlap(asset, name_group, candidate_group)
        if not overlap["has_overlap"]:
            decisions.append(
                CandidateDecision(
                    candidate=candidate,
                    overlap=overlap,
                    same_project=False,
                    confidence=0.0,
                    shared_signals=[],
                    reason="cheap_overlap_rejected",
                    passes=False,
                    name_sample_count=len(name_group.tweets),
                    candidate_sample_count=len(candidate_group.tweets),
                )
            )
            continue
        same_project, confidence, shared_signals, reason = _match_candidate_with_ai(
            client,
            asset=asset,
            name_group=name_group,
            candidate_group=candidate_group,
            overlap=overlap,
            usage_totals=usage_totals,
        )
        decisions.append(
            CandidateDecision(
                candidate=candidate,
                overlap=overlap,
                same_project=same_project,
                confidence=confidence,
                shared_signals=shared_signals,
                reason=reason,
                passes=_decide_candidate_pass(overlap=overlap, same_project=same_project, confidence=confidence),
                name_sample_count=len(name_group.tweets),
                candidate_sample_count=len(candidate_group.tweets),
            )
        )

    passing = [item for item in decisions if item.passes]
    if not passing:
        return None, decisions, candidate_groups
    best = sorted(passing, key=_decision_rank_key, reverse=True)[0]
    return (
        ExistingCAResolution(
            contract_address=best.candidate.contract_address,
            chain_index=best.candidate.chain_index,
            status="resolved",
            resolved_by="onchain_x_similarity",
        ),
        decisions,
        candidate_groups,
    )


def _candidate_decisions_payload(decisions: Sequence[CandidateDecision]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for decision in decisions:
        payload.append(
            {
                "contract_address": decision.candidate.contract_address,
                "chain_index": decision.candidate.chain_index,
                "display_name": decision.candidate.display_name,
                "symbol": decision.candidate.symbol,
                "chain_name": decision.candidate.chain_name,
                "community_recognized": decision.candidate.community_recognized,
                "holder_count": decision.candidate.holder_count,
                "liquidity": decision.candidate.liquidity,
                "market_cap": decision.candidate.market_cap,
                "same_project": decision.same_project,
                "confidence": decision.confidence,
                "shared_signals": decision.shared_signals,
                "overlap": decision.overlap,
                "passes": decision.passes,
                "reason": decision.reason,
                "name_sample_count": decision.name_sample_count,
                "candidate_sample_count": decision.candidate_sample_count,
            }
        )
    return payload


def _collect_source_urls(name_group: SearchGroup, ca_group: SearchGroup | None) -> list[str]:
    return list(
        dict.fromkeys(
            [
                *[tweet.url for tweet in name_group.tweets],
                *([tweet.url for tweet in ca_group.tweets] if ca_group else []),
            ]
        )
    )


def _build_query_set(
    *,
    expanded_keywords: Sequence[str],
    name_queries: Sequence[str],
    candidate_groups: dict[str, SearchGroup],
) -> dict[str, Any]:
    return {
        "name_queries": list(name_queries),
        "expanded_keywords": list(expanded_keywords),
        "candidate_queries": {
            key: group.queries
            for key, group in candidate_groups.items()
            if not key.startswith("__")
        },
    }


def _candidate_group_stats(candidate_groups: dict[str, SearchGroup]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, group in candidate_groups.items():
        payload[key] = {
            "label": group.label,
            "tweet_count": len(group.tweets),
            "errors": group.error_messages,
            "warnings": group.warning_messages,
        }
    return payload


def _build_source_stats(
    *,
    name_group: SearchGroup,
    chosen_group: SearchGroup | None,
    candidate_payloads: Sequence[dict[str, Any]],
    candidate_groups: dict[str, SearchGroup],
    identity: IdentityAssessment | None,
) -> dict[str, Any]:
    return {
        "name_group_tweet_count": len(name_group.tweets),
        "candidate_group_tweet_count": len(chosen_group.tweets) if chosen_group else 0,
        "name_group_errors": name_group.error_messages,
        "candidate_group_errors": [] if chosen_group is None else chosen_group.error_messages,
        "name_group_warnings": name_group.warning_messages,
        "candidate_group_warnings": [] if chosen_group is None else chosen_group.warning_messages,
        "candidate_decision_count": len(candidate_payloads),
        "candidate_groups": _candidate_group_stats(candidate_groups),
        "identity_status": None if identity is None else identity.status,
        "identity_reasons": [] if identity is None else identity.reasons,
        "identity_official_account_match": False if identity is None else identity.official_account_match,
        "identity_dominant_cluster_ratio": 0.0 if identity is None else identity.dominant_cluster_ratio,
        "identity_cluster_count": 0 if identity is None else identity.cluster_count,
        "identity_overlapping_candidate_count": 0 if identity is None else identity.overlapping_candidate_count,
        "identity_matched_stable_aliases": [] if identity is None else identity.matched_stable_aliases,
        "identity_ambiguous_name": False if identity is None else identity.ambiguous_name,
    }


def _summary_sample_error(name_group: SearchGroup, ca_group: SearchGroup | None) -> str:
    merged_count = len(_collect_source_urls(name_group, ca_group))
    details = [
        f"not enough X samples for summary (merged={merged_count}, name={len(name_group.tweets)}, candidate={len(ca_group.tweets) if ca_group else 0})"
    ]
    if name_group.error_messages:
        details.append(f"name_errors={'; '.join(name_group.error_messages[:2])}")
    if ca_group and ca_group.error_messages:
        details.append(f"candidate_errors={'; '.join(ca_group.error_messages[:2])}")
    if name_group.warning_messages:
        details.append(f"name_warnings={'; '.join(name_group.warning_messages[:2])}")
    if ca_group and ca_group.warning_messages:
        details.append(f"candidate_warnings={'; '.join(ca_group.warning_messages[:2])}")
    return _clip(" | ".join(details), 800)


def _ensure_ambiguous_summary_guard(summary_text: str) -> str:
    guard_markers = ("身份", "混淆", "同名", "确认", "样本不足")
    if any(marker in summary_text for marker in guard_markers):
        return summary_text
    return _clip(f"当前样本不足以完全确认项目身份，以下为保守概括：{summary_text}", 240)


def _summarize_asset(
    client: Any,
    *,
    asset: CryptoAssetBriefTarget,
    name_group: SearchGroup,
    ca_group: SearchGroup | None,
    resolution: ExistingCAResolution | None,
    identity: IdentityAssessment,
    usage_totals: dict[str, int],
) -> tuple[str, str]:
    merged_tweets = list(name_group.tweets)
    merged_urls = {tweet.url for tweet in merged_tweets}
    if ca_group is not None:
        for tweet in ca_group.tweets:
            if tweet.url not in merged_urls:
                merged_tweets.append(tweet)
                merged_urls.add(tweet.url)
    merged_tweets = sorted(merged_tweets, key=_tweet_score, reverse=True)[:MAX_SUMMARY_TWEETS]
    if len(merged_tweets) < SUMMARY_MIN_TWEETS:
        raise ValueError(_summary_sample_error(name_group, ca_group))
    payload = {
        "asset": {
            "asset_key": asset.asset_key,
            "display_name": asset.display_name,
            "symbol": asset.symbol,
            "chain": asset.chain,
            "aliases": asset.aliases,
            "x_accounts": asset.x_accounts,
            "contract_address": resolution.contract_address if resolution else "",
            "chain_index": resolution.chain_index if resolution else "",
            "identity_status": identity.status,
            "identity_reasons": identity.reasons,
        },
        "name_group": _group_payload(asset, name_group),
        "candidate_group": None if ca_group is None else _group_payload(asset, ca_group),
        "tweet_samples": _sample_group_tweets(merged_tweets, limit=12),
    }
    result = client.generate_json(
        build_crypto_asset_brief_messages(payload),
        required_keys=CRYPTO_ASSET_BRIEF_REQUIRED_KEYS,
        max_tokens=500,
    )
    _aggregate_usage(usage_totals, result.usage)
    summary_text = _clip(str(result.parsed.get("summary_text") or "").strip(), 240)
    if not summary_text:
        raise RuntimeError("AI response did not include summary_text")
    if identity.status == IDENTITY_STATUS_AMBIGUOUS:
        summary_text = _ensure_ambiguous_summary_guard(summary_text)
    return summary_text, result.model_name


def _fetch_targets(
    conn: Any,
    *,
    days: int,
    limit: int | None,
    asset_keys: Sequence[str] | None,
) -> list[CryptoAssetBriefTarget]:
    cutoff_date = (datetime.now(SHANGHAI_TZ).date() - timedelta(days=max(1, int(days)) - 1)).isoformat()
    params: list[Any] = [cutoff_date]
    filters = ["summary.latest_seen_date >= %s::date"]
    if asset_keys:
        params.append(list(asset_keys))
        filters.append("summary.asset_key = any(%s)")
    sql = f"""
        with summary as (
          select
            ce.asset_key,
            ce.display_name,
            coalesce(ce.symbol, '') as symbol,
            coalesce(ce.chain, '') as chain,
            coalesce(ce.identifier_type, '') as identifier_type,
            coalesce(ce.aliases_json, '[]'::jsonb) as aliases_json,
            coalesce(ce.raw_identifiers_json, '[]'::jsonb) as raw_identifiers_json,
            coalesce(ce.contract_addresses_json, '[]'::jsonb) as contract_addresses_json,
            coalesce(ce.x_accounts_json, '[]'::jsonb) as x_accounts_json,
            min(cdv.date_key)::date as first_seen_date,
            max(cdv.date_key)::date as latest_seen_date,
            coalesce(sum(cdv.mention_count), 0)::int as mention_count
          from crypto_entities ce
          join crypto_entity_daily_views cdv on cdv.crypto_entity_id = ce.id
          left join crypto_asset_admin_deletions deleted on deleted.asset_key = ce.asset_key
          where deleted.asset_key is null
          group by ce.id
        )
        select *
        from summary
        where {" and ".join(filters)}
        order by latest_seen_date desc, mention_count desc, display_name asc
    """
    if limit is not None:
        sql += " limit %s"
        params.append(max(1, int(limit)))
    rows = conn.execute(sql, tuple(params)).fetchall()
    return [
        CryptoAssetBriefTarget(
            asset_key=str(row["asset_key"]),
            display_name=str(row["display_name"] or row["asset_key"]),
            symbol=str(row["symbol"] or "").strip(),
            chain=str(row["chain"] or "").strip(),
            identifier_type=str(row["identifier_type"] or "").strip(),
            aliases=_string_list(row["aliases_json"]),
            raw_identifiers=_string_list(row["raw_identifiers_json"]),
            contract_addresses=_string_list(row["contract_addresses_json"]),
            x_accounts=_string_list(row["x_accounts_json"]),
            first_seen_date=str(row["first_seen_date"]),
            latest_seen_date=str(row["latest_seen_date"]),
            mention_count=_safe_int(row["mention_count"]),
        )
        for row in rows
    ]


def _fetch_existing_success(conn: Any, asset_key: str) -> dict[str, Any] | None:
    return conn.execute(
        """
        select asset_key, status, summary_text, updated_at
        from crypto_asset_narrative_briefs
        where asset_key = %s
          and status = 'succeeded'
          and nullif(summary_text, '') is not null
        """,
        (asset_key,),
    ).fetchone()


def _upsert_brief(
    conn: Any,
    *,
    asset: CryptoAssetBriefTarget,
    status: str,
    identity_status: str | None,
    ca_resolution_status: str,
    contract_address: str,
    chain_index: str,
    resolved_by: str,
    summary_text: str,
    candidate_contracts: list[dict[str, Any]],
    query_set: dict[str, Any],
    source_urls: list[str],
    source_stats: dict[str, Any],
    model_name: str | None,
    usage: dict[str, Any],
    error_text: str = "",
) -> None:
    conn.execute(
        """
        insert into crypto_asset_narrative_briefs (
          asset_key, status, identity_status, ca_resolution_status, contract_address, chain_index, resolved_by,
          summary_text, candidate_contracts_json, query_set_json, source_urls_json, source_stats_json,
          model_name, prompt_version, usage_json, error_text, first_seen_date, latest_seen_date, updated_at
        )
        values (
          %s, %s, nullif(%s, ''), %s, nullif(%s, ''), nullif(%s, ''), %s,
          %s, %s, %s, %s, %s,
          %s, %s, %s, %s, %s::date, %s::date, now()
        )
        on conflict (asset_key) do update set
          status = excluded.status,
          identity_status = excluded.identity_status,
          ca_resolution_status = excluded.ca_resolution_status,
          contract_address = excluded.contract_address,
          chain_index = excluded.chain_index,
          resolved_by = excluded.resolved_by,
          summary_text = excluded.summary_text,
          candidate_contracts_json = excluded.candidate_contracts_json,
          query_set_json = excluded.query_set_json,
          source_urls_json = excluded.source_urls_json,
          source_stats_json = excluded.source_stats_json,
          model_name = excluded.model_name,
          prompt_version = excluded.prompt_version,
          usage_json = excluded.usage_json,
          error_text = excluded.error_text,
          first_seen_date = excluded.first_seen_date,
          latest_seen_date = excluded.latest_seen_date,
          updated_at = now()
        """,
        (
            asset.asset_key,
            status,
            identity_status,
            ca_resolution_status,
            contract_address,
            chain_index,
            resolved_by,
            summary_text,
            Jsonb(candidate_contracts),
            Jsonb(query_set),
            Jsonb(source_urls),
            Jsonb(source_stats),
            model_name,
            PROMPT_VERSION,
            Jsonb(usage),
            _clip(error_text, 800),
            asset.first_seen_date,
            asset.latest_seen_date,
        ),
    )


def _persist_brief(**kwargs: Any) -> None:
    with postgres_connection() as conn:
        _upsert_brief(conn, **kwargs)


def generate_crypto_asset_briefs_once(
    *,
    days: int = 30,
    limit: int | None = None,
    asset_keys: Sequence[str] | None = None,
    force: bool = False,
) -> int:
    settings = _model_settings()
    with postgres_connection() as conn:
        targets = _fetch_targets(conn, days=days, limit=limit, asset_keys=asset_keys)
        blocked_terms = _fetch_blocked_terms(conn)
        existing_success_by_key = {
            asset.asset_key: _fetch_existing_success(conn, asset.asset_key)
            for asset in targets
        }
        if not targets:
            print("[public-worker] crypto_asset_brief skipped reason=no_recent_assets")
            return 0
    client: Any = None
    failures = 0
    processed = 0
    skipped = 0
    for asset in targets:
        existing = existing_success_by_key.get(asset.asset_key)
        if existing and not force:
            skipped += 1
            continue

        blocked_match = _find_blocked_match(asset, blocked_terms)
        if blocked_match is not None:
            _persist_brief(
                asset=asset,
                status="skipped",
                identity_status=None,
                ca_resolution_status="unresolved",
                contract_address="",
                chain_index="",
                resolved_by="blocked_term",
                summary_text="",
                candidate_contracts=[],
                query_set={},
                source_urls=[],
                source_stats={
                    "skip_reason": "blocked_term",
                    "blocked_term": blocked_match.term,
                    "matched_field": blocked_match.source_field,
                },
                model_name=None,
                usage={},
                error_text=f"blocked term matched: {blocked_match.term}",
            )
            skipped += 1
            print(
                "[public-worker] crypto_asset_brief "
                f"asset_key={asset.asset_key} status=skipped reason=blocked_term term={blocked_match.term}"
            )
            continue

        usage_totals = {"input_tokens": 0, "output_tokens": 0}
        expanded_keywords: list[str] = []
        name_queries: list[str] = []
        name_group = SearchGroup("name", [], [], [], [])
        resolution: ExistingCAResolution | None = None
        decisions: list[CandidateDecision] = []
        candidate_groups: dict[str, SearchGroup] = {}
        chosen_group: SearchGroup | None = None
        candidate_payloads: list[dict[str, Any]] = []
        identity: IdentityAssessment | None = None
        query_set: dict[str, Any] = {}
        source_urls: list[str] = []
        source_stats: dict[str, Any] = {}
        model_name: str | None = None
        try:
            if client is None:
                from packages.ai.client import LLMJsonClient

                client = LLMJsonClient(settings)
            expanded_keywords = _generate_expanded_keywords(client, asset, usage_totals)
            name_queries = _build_name_queries(asset, expanded_keywords)
            name_group = _search_group("name", name_queries, group_limit=MAX_NAME_GROUP_TWEETS)

            resolution = _extract_existing_resolution(asset)
            if resolution is None:
                resolution, decisions, candidate_groups = _resolve_candidate_via_similarity(
                    client,
                    asset=asset,
                    name_group=name_group,
                    usage_totals=usage_totals,
                )
            else:
                candidate_groups[resolution.contract_address] = _search_group(
                    "existing_ca",
                    _build_candidate_queries(asset, resolution),
                    group_limit=MAX_CANDIDATE_GROUP_TWEETS,
                )
            candidate_payloads = _candidate_decisions_payload(decisions)

            chosen_group = None if resolution is None else candidate_groups.get(resolution.contract_address)
            identity = _assess_identity_status(
                asset,
                name_group=name_group,
                resolution=resolution,
                decisions=decisions,
            )
            query_set = _build_query_set(
                expanded_keywords=expanded_keywords,
                name_queries=name_queries,
                candidate_groups=candidate_groups,
            )
            source_urls = _collect_source_urls(name_group, chosen_group)
            source_stats = _build_source_stats(
                name_group=name_group,
                chosen_group=chosen_group,
                candidate_payloads=candidate_payloads,
                candidate_groups=candidate_groups,
                identity=identity,
            )
            summary_text, model_name = _summarize_asset(
                client,
                asset=asset,
                name_group=name_group,
                ca_group=chosen_group,
                resolution=resolution,
                identity=identity,
                usage_totals=usage_totals,
            )
            _persist_brief(
                asset=asset,
                status="succeeded",
                identity_status=identity.status,
                ca_resolution_status=resolution.status if resolution else "unresolved",
                contract_address="" if resolution is None else resolution.contract_address,
                chain_index="" if resolution is None else resolution.chain_index,
                resolved_by="" if resolution is None else resolution.resolved_by,
                summary_text=summary_text,
                candidate_contracts=candidate_payloads,
                query_set=query_set,
                source_urls=source_urls,
                source_stats=source_stats,
                model_name=model_name,
                usage=usage_totals,
            )
            processed += 1
            print(
                "[public-worker] crypto_asset_brief "
                f"asset_key={asset.asset_key} status=succeeded "
                f"identity_status={identity.status} "
                f"ca_status={resolution.status if resolution else 'unresolved'} "
                f"name_tweets={len(name_group.tweets)} "
                f"candidate_tweets={len(chosen_group.tweets) if chosen_group else 0}"
            )
        except Exception as exc:
            failures += 1
            if not query_set:
                query_set = _build_query_set(
                    expanded_keywords=expanded_keywords,
                    name_queries=name_queries,
                    candidate_groups=candidate_groups,
                )
            if not source_urls:
                source_urls = _collect_source_urls(name_group, chosen_group)
            if not source_stats:
                source_stats = _build_source_stats(
                    name_group=name_group,
                    chosen_group=chosen_group,
                    candidate_payloads=candidate_payloads,
                    candidate_groups=candidate_groups,
                    identity=identity,
                )
            _persist_brief(
                asset=asset,
                status="failed",
                identity_status=None if identity is None else identity.status,
                ca_resolution_status=resolution.status if resolution else "unresolved",
                contract_address="" if resolution is None else resolution.contract_address,
                chain_index="" if resolution is None else resolution.chain_index,
                resolved_by="" if resolution is None else resolution.resolved_by,
                summary_text="",
                candidate_contracts=candidate_payloads,
                query_set=query_set,
                source_urls=source_urls,
                source_stats=source_stats,
                model_name=model_name,
                usage=usage_totals,
                error_text=str(exc),
            )
            print(
                "[public-worker] crypto_asset_brief failed "
                f"asset_key={asset.asset_key} "
                f"identity_status={identity.status if identity else '-'} "
                f"error={_clip(str(exc), 180)}"
            )

    print(
        "[public-worker] crypto_asset_brief_done "
        f"processed={processed} skipped={skipped} failures={failures}"
    )
    return 1 if failures else 0
