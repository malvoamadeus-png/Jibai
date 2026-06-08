from __future__ import annotations

import json
from typing import Any, Callable

from packages.common.settings import AppSettings, load_settings

from .models import BloggerPost, StockSignalMention


REQUIRED_KEYS = ["mentions"]
MAX_POSTS_PER_BATCH = 36
MAX_CHARS_PER_BATCH = 42_000

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
                    "stock_name": {"type": "string"},
                    "ticker_or_code": {"type": ["string", "null"]},
                    "market_hint": {"type": ["string", "null"]},
                    "direction": {"type": "string", "enum": ["positive", "negative", "mixed", "unknown"]},
                    "signal_type": {"type": "string", "enum": ["explicit_stance", "logic_based", "informational", "mention_signal", "unknown"]},
                    "judgment_type": {"type": "string", "enum": ["direct", "implied", "factual_only", "quoted", "mention_only", "unknown"]},
                    "conviction": {"type": "string", "enum": ["strong", "medium", "weak", "none", "unknown"]},
                    "evidence_type": {
                        "type": "string",
                        "enum": [
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
                        ],
                    },
                    "time_horizon": {"type": "string", "enum": ["short_term", "medium_term", "long_term", "unspecified"]},
                    "confidence": {"type": "number"},
                    "logic": {"type": "string"},
                    "evidence": {"type": "string"},
                },
                "required": [
                    "tweet_id",
                    "stock_name",
                    "ticker_or_code",
                    "market_hint",
                    "direction",
                    "signal_type",
                    "judgment_type",
                    "conviction",
                    "evidence_type",
                    "time_horizon",
                    "confidence",
                    "logic",
                    "evidence",
                ],
            },
        }
    },
    "required": ["mentions"],
}


def chunk_posts(posts: list[BloggerPost], max_posts: int = MAX_POSTS_PER_BATCH, max_chars: int = MAX_CHARS_PER_BATCH) -> list[list[BloggerPost]]:
    chunks: list[list[BloggerPost]] = []
    current: list[BloggerPost] = []
    current_chars = 0
    for post in posts:
        post_chars = len(post.text) + 360
        if current and (len(current) >= max_posts or current_chars + post_chars > max_chars):
            chunks.append(current)
            current = []
            current_chars = 0
        current.append(post)
        current_chars += post_chars
    if current:
        chunks.append(current)
    return chunks


def build_messages(posts: list[BloggerPost]) -> list[dict[str, str]]:
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
                "你是一个股票博主观点验证系统的数据抽取助手。只输出 JSON 对象。"
                "从 X 帖子中抽取作者本人对具体上市股票或证券的方向性观点。"
                "不要抽取指数、宏观主题、行业、非上市项目或纯 crypto token。"
                "股票可以由 ticker、公司名、证券名、常见简称、产品线明确指向上市公司。"
                "只要作者基于产业链位置、竞争格局、订单、利润率、估值、财报、管理层信号等证据推出看多/看空结论，即使语气客观、不喊单，也应抽取为 logic_based。"
                "direction 只能是 positive、negative、mixed、unknown；只有作者本人观点明确时才用 positive/negative。"
                "signal_type 用 explicit_stance 或 logic_based；纯新闻、行情、列表、转述或仅提及用 informational/mention_signal。"
                "judgment_type 用 direct 或 implied；factual_only、quoted、mention_only 后续不会评分。"
                "conviction 不是喊单夸张程度，而是判断清晰度和确信度：strong 可来自明确 thesis、仓位动作、目标价、强催化或持续高确信逻辑；medium 是清晰方向和理由但语气保留；weak 是关注/可能/倾向。"
                "time_horizon 判断作者表达的周期，无法判断用 unspecified。"
                "logic 写成短句，说明基于什么证据得出什么股票结论；evidence 贴近原文但不要大段照抄。"
                "没有有效股票观点时 mentions 返回空数组。"
            ),
        },
        {
            "role": "user",
            "content": "请抽取以下 X 帖子的股票观点事件：\n\n" + json.dumps(payload, ensure_ascii=False),
        },
    ]


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
                "name": "stock_blogger_signal_mentions",
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


def _normalize_string(value: Any, allowed: set[str], default: str) -> str:
    raw = str(value or "").strip()
    return raw if raw in allowed else default


def _mention_from_payload(item: dict[str, Any], posts_by_id: dict[str, BloggerPost]) -> StockSignalMention | None:
    tweet_id = str(item.get("tweet_id") or "").strip()
    stock_name = str(item.get("stock_name") or "").strip()
    if not tweet_id or not stock_name or tweet_id not in posts_by_id:
        return None
    post = posts_by_id[tweet_id]
    try:
        confidence = max(0.0, min(1.0, float(item.get("confidence") if item.get("confidence") is not None else 0.0)))
    except (TypeError, ValueError):
        confidence = 0.0

    return StockSignalMention(
        tweet_id=tweet_id,
        author=post.author,
        author_name=post.author_name,
        published_at=post.published_at,
        tweet_url=post.url,
        raw_text=post.text,
        stock_name=stock_name,
        ticker_or_code=str(item.get("ticker_or_code") or "").strip() or None,
        market_hint=str(item.get("market_hint") or "").strip() or None,
        direction=_normalize_string(item.get("direction"), {"positive", "negative", "mixed", "unknown"}, "unknown"),
        signal_type=_normalize_string(item.get("signal_type"), {"explicit_stance", "logic_based", "informational", "mention_signal", "unknown"}, "unknown"),
        judgment_type=_normalize_string(item.get("judgment_type"), {"direct", "implied", "factual_only", "quoted", "mention_only", "unknown"}, "unknown"),
        conviction=_normalize_string(item.get("conviction"), {"strong", "medium", "weak", "none", "unknown"}, "unknown"),
        evidence_type=_normalize_string(
            item.get("evidence_type"),
            {"price_action", "earnings", "guidance", "management_commentary", "valuation", "policy", "rumor", "position", "capital_flow", "technical", "macro", "other", "unknown"},
            "unknown",
        ),
        time_horizon=_normalize_string(item.get("time_horizon"), {"short_term", "medium_term", "long_term", "unspecified"}, "unspecified"),
        confidence=confidence,
        logic=str(item.get("logic") or "").strip(),
        evidence=str(item.get("evidence") or "").strip(),
    )


def extract_mentions(
    posts: list[BloggerPost],
    *,
    model: str,
    settings: AppSettings | None = None,
    structured_call: Callable[[AppSettings, str, list[dict[str, str]]], dict[str, Any]] = _completion_with_schema,
    fallback_call: Callable[[AppSettings, str, list[dict[str, str]]], dict[str, Any]] = _fallback_json,
) -> list[StockSignalMention]:
    if not posts:
        return []
    settings = settings or load_settings()
    if not settings.api_key:
        raise ValueError("Missing AI API key. Configure AI_API_KEY/OPENAI_API_KEY or use --skip-ai with existing mentions.")

    posts_by_id = {post.tweet_id: post for post in posts}
    mentions: list[StockSignalMention] = []
    for chunk in chunk_posts(posts):
        mentions.extend(_extract_chunk_with_split(chunk, model=model, settings=settings, structured_call=structured_call, fallback_call=fallback_call, posts_by_id=posts_by_id))
    return mentions


def _extract_chunk_with_split(
    posts: list[BloggerPost],
    *,
    model: str,
    settings: AppSettings,
    structured_call: Callable[[AppSettings, str, list[dict[str, str]]], dict[str, Any]],
    fallback_call: Callable[[AppSettings, str, list[dict[str, str]]], dict[str, Any]],
    posts_by_id: dict[str, BloggerPost],
) -> list[StockSignalMention]:
    messages = build_messages(posts)
    try:
        payload = structured_call(settings, model, messages)
    except Exception:
        try:
            payload = fallback_call(settings, model, messages)
        except Exception:
            if len(posts) <= 1:
                raise
            midpoint = len(posts) // 2
            return [
                *_extract_chunk_with_split(posts[:midpoint], model=model, settings=settings, structured_call=structured_call, fallback_call=fallback_call, posts_by_id=posts_by_id),
                *_extract_chunk_with_split(posts[midpoint:], model=model, settings=settings, structured_call=structured_call, fallback_call=fallback_call, posts_by_id=posts_by_id),
            ]

    rows = payload.get("mentions") if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        return []
    mentions: list[StockSignalMention] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        mention = _mention_from_payload(row, posts_by_id)
        if mention is not None:
            mentions.append(mention)
    return mentions

