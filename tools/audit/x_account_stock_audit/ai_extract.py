from __future__ import annotations

import json
from typing import Any, Callable

from packages.common.settings import AppSettings, load_settings

from .models import AuditPost, StockMention


REQUIRED_KEYS = ["mentions"]
MAX_POSTS_PER_BATCH = 40
MAX_CHARS_PER_BATCH = 45_000

MENTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "mentions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "tweet_id": {"type": "string"},
                    "published_at": {"type": "string"},
                    "stock_name": {"type": "string"},
                    "ticker_or_code": {"type": ["string", "null"]},
                    "market_hint": {"type": ["string", "null"]},
                    "stance": {"type": "string", "enum": ["bull", "bear", "mention_only", "mixed"]},
                    "direction": {"type": "string"},
                    "judgment_type": {"type": "string"},
                    "confidence": {"type": "number"},
                    "viewpoint": {"type": "string"},
                    "evidence": {"type": "string"},
                },
                "required": [
                    "tweet_id",
                    "published_at",
                    "stock_name",
                    "ticker_or_code",
                    "market_hint",
                    "stance",
                    "direction",
                    "judgment_type",
                    "confidence",
                    "viewpoint",
                    "evidence",
                ],
            },
        }
    },
    "required": ["mentions"],
}


def chunk_posts(posts: list[AuditPost], max_posts: int = MAX_POSTS_PER_BATCH, max_chars: int = MAX_CHARS_PER_BATCH) -> list[list[AuditPost]]:
    chunks: list[list[AuditPost]] = []
    current: list[AuditPost] = []
    current_chars = 0
    for post in posts:
        post_chars = len(post.text) + 300
        if current and (len(current) >= max_posts or current_chars + post_chars > max_chars):
            chunks.append(current)
            current = []
            current_chars = 0
        current.append(post)
        current_chars += post_chars
    if current:
        chunks.append(current)
    return chunks


def build_messages(posts: list[AuditPost]) -> list[dict[str, str]]:
    payload = [
        {
            "tweet_id": post.tweet_id,
            "published_at": post.published_at,
            "url": post.url,
            "text": post.text,
        }
        for post in posts
    ]
    return [
        {
            "role": "system",
            "content": (
                "你是一个股票喊单审计数据抽取助手。只输出 JSON 对象。"
                "从 X 帖子中抽取具体上市股票或证券。股票可以由 ticker、公司名、证券名、常见简称、产品线明确指向上市公司。"
                "保留 bull、bear、mention_only、mixed 四类："
                "bull 表示作者本人明确看多、买入、持有、加仓或给出正向交易判断；"
                "bear 表示作者本人明确看空、卖出、减仓、避开或给出负向交易判断；"
                "mention_only 表示仅提到股票、新闻、财报、列表、价格播报或无明确方向；"
                "mixed 表示同一条里正负因素并存且无法压成单向。"
                "不要抽取指数、宏观主题、行业、非上市项目或纯 crypto token。"
                "每个 mention 必须包含 tweet_id, published_at, stock_name, ticker_or_code, market_hint, stance, direction, judgment_type, confidence, viewpoint, evidence。"
                "evidence 用短句贴近原文，不要大段照抄。"
            ),
        },
        {
            "role": "user",
            "content": "请抽取以下 X 帖子的股票提及和态度：\n\n" + json.dumps(payload, ensure_ascii=False),
        },
    ]


def normalize_stance(value: Any, direction: Any = None, judgment_type: Any = None) -> str:
    raw = str(value or "").strip().casefold()
    if raw in {"bull", "bullish", "positive", "long", "buy", "strong_bullish"}:
        return "bull"
    if raw in {"bear", "bearish", "negative", "short", "sell", "strong_bearish"}:
        return "bear"
    if raw in {"mixed"}:
        return "mixed"
    if raw in {"mention_only", "mention", "neutral", "none", "unknown", "factual_only", "quoted"}:
        return "mention_only"
    direction_raw = str(direction or "").strip().casefold()
    judgment_raw = str(judgment_type or "").strip().casefold()
    if judgment_raw in {"mention_only", "factual_only", "quoted"}:
        return "mention_only"
    if direction_raw == "positive":
        return "bull"
    if direction_raw == "negative":
        return "bear"
    if direction_raw == "mixed":
        return "mixed"
    return "mention_only"


def _completion_with_schema(settings: AppSettings, model: str, messages: list[dict[str, str]]) -> dict[str, Any]:
    from litellm import completion

    response = completion(
        model=model if "/" in model else f"openai/{model}",
        messages=messages,
        temperature=0.1,
        max_tokens=8000,
        api_key=settings.api_key,
        base_url=settings.base_url,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "x_account_stock_mentions",
                "schema": MENTION_SCHEMA,
                "strict": True,
            },
        },
    )
    payload = response.model_dump() if hasattr(response, "model_dump") else response
    text = payload["choices"][0]["message"]["content"]
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Structured output was not a JSON object")
    return parsed


def _fallback_json(settings: AppSettings, model: str, messages: list[dict[str, str]]) -> dict[str, Any]:
    from packages.ai.client import LLMJsonClient

    client = LLMJsonClient(settings.model_copy(update={"model": model, "fallback_models": []}))
    return client.generate_json(messages, required_keys=REQUIRED_KEYS, max_tokens=8000).parsed


def _mention_from_payload(item: dict[str, Any], posts_by_id: dict[str, AuditPost]) -> StockMention | None:
    tweet_id = str(item.get("tweet_id") or "").strip()
    stock_name = str(item.get("stock_name") or "").strip()
    if not tweet_id or not stock_name or tweet_id not in posts_by_id:
        return None
    post = posts_by_id[tweet_id]
    confidence_raw = item.get("confidence")
    try:
        confidence = max(0.0, min(1.0, float(confidence_raw if confidence_raw is not None else 0.0)))
    except (TypeError, ValueError):
        confidence = 0.0
    stance = normalize_stance(item.get("stance"), item.get("direction"), item.get("judgment_type"))
    return StockMention(
        tweet_id=tweet_id,
        published_at=str(item.get("published_at") or post.published_at),
        stock_name=stock_name,
        ticker_or_code=str(item.get("ticker_or_code") or "").strip() or None,
        market_hint=str(item.get("market_hint") or "").strip() or None,
        stance=stance,  # type: ignore[arg-type]
        direction=str(item.get("direction") or "").strip() or "unknown",
        judgment_type=str(item.get("judgment_type") or "").strip() or "unknown",
        confidence=confidence,
        viewpoint=str(item.get("viewpoint") or "").strip(),
        evidence=str(item.get("evidence") or "").strip(),
        tweet_url=post.url,
        raw_text=post.text,
    )


def extract_mentions(
    posts: list[AuditPost],
    *,
    model: str,
    settings: AppSettings | None = None,
    structured_call: Callable[[AppSettings, str, list[dict[str, str]]], dict[str, Any]] = _completion_with_schema,
    fallback_call: Callable[[AppSettings, str, list[dict[str, str]]], dict[str, Any]] = _fallback_json,
) -> list[StockMention]:
    if not posts:
        return []
    settings = settings or load_settings()
    if not settings.api_key:
        raise ValueError("Missing AI API key. Configure AI_API_KEY/OPENAI_API_KEY or use --skip-ai.")

    posts_by_id = {post.tweet_id: post for post in posts}
    mentions: list[StockMention] = []
    for chunk in chunk_posts(posts):
        mentions.extend(_extract_chunk_with_split(chunk, model=model, settings=settings, structured_call=structured_call, fallback_call=fallback_call, posts_by_id=posts_by_id))
    return mentions


def _extract_chunk_with_split(
    posts: list[AuditPost],
    *,
    model: str,
    settings: AppSettings,
    structured_call: Callable[[AppSettings, str, list[dict[str, str]]], dict[str, Any]],
    fallback_call: Callable[[AppSettings, str, list[dict[str, str]]], dict[str, Any]],
    posts_by_id: dict[str, AuditPost],
) -> list[StockMention]:
    messages = build_messages(posts)
    try:
        parsed = structured_call(settings, model, messages)
    except Exception:
        try:
            parsed = fallback_call(settings, model, messages)
        except Exception:
            if len(posts) <= 10:
                raise
            midpoint = len(posts) // 2
            return _extract_chunk_with_split(posts[:midpoint], model=model, settings=settings, structured_call=structured_call, fallback_call=fallback_call, posts_by_id=posts_by_id) + _extract_chunk_with_split(posts[midpoint:], model=model, settings=settings, structured_call=structured_call, fallback_call=fallback_call, posts_by_id=posts_by_id)

    raw_mentions = parsed.get("mentions") if isinstance(parsed, dict) else []
    if not isinstance(raw_mentions, list):
        raw_mentions = []
    results: list[StockMention] = []
    for raw in raw_mentions:
        if not isinstance(raw, dict):
            continue
        mention = _mention_from_payload(raw, posts_by_id)
        if mention is not None:
            results.append(mention)
    return results
