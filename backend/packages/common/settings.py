from __future__ import annotations

import json
import os
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from .paths import get_paths

AIProvider = Literal["openai-compatible", "anthropic"]
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-5.4"
DEFAULT_OPENAI_FALLBACK_MODELS = ["gpt-4.1"]


class AppSettings(BaseModel):
    provider: AIProvider = "openai-compatible"
    api_key: str | None = None
    model: str = DEFAULT_OPENAI_MODEL
    fallback_models: list[str] = Field(
        default_factory=lambda: list(DEFAULT_OPENAI_FALLBACK_MODELS)
    )
    reasoning_effort: str | None = None
    base_url: str | None = DEFAULT_OPENAI_BASE_URL


def _split_models(raw: str | list[str] | None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        values = [str(item).strip() for item in raw if str(item).strip()]
    else:
        values = [item.strip() for item in str(raw).split(",") if item.strip()]

    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped


def _normalize_provider(raw: Any) -> AIProvider | None:
    value = str(raw or "").strip().casefold()
    if not value:
        return None
    if value in {"openai", "openai-compatible", "openai_compatible", "openai-compatible-endpoint"}:
        return "openai-compatible"
    if value in {"anthropic", "claude"}:
        return "anthropic"
    return None


def _read_local_ai_settings() -> dict[str, Any]:
    paths = get_paths()
    config_path = paths.ai_settings_path
    if not config_path.exists():
        return {}

    try:
        payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _pick_first(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _pick_provider(local_settings: dict[str, Any]) -> AIProvider:
    local_provider = _normalize_provider(local_settings.get("provider"))
    if local_provider:
        return local_provider

    env_provider = _normalize_provider(os.getenv("AI_PROVIDER"))
    if env_provider:
        return env_provider

    if _pick_first(os.getenv("ANTHROPIC_API_KEY")):
        return "anthropic"
    return "openai-compatible"


def load_settings() -> AppSettings:
    paths = get_paths()
    load_dotenv(paths.root_dir / ".env", override=False)

    local_settings = _read_local_ai_settings()
    provider = _pick_provider(local_settings)

    if provider == "anthropic":
        api_key = _pick_first(
            local_settings.get("api_key"),
            os.getenv("AI_API_KEY"),
            os.getenv("ANTHROPIC_API_KEY"),
        )
        model = _pick_first(
            local_settings.get("model"),
            os.getenv("AI_MODEL"),
            os.getenv("ANTHROPIC_MODEL"),
            os.getenv("ANTHROPIC_MODEL_NAME"),
            DEFAULT_OPENAI_MODEL,
        )
        fallback_models = _split_models(
            local_settings.get("fallback_models")
            or os.getenv("AI_FALLBACK_MODELS")
            or os.getenv("ANTHROPIC_FALLBACK_MODELS")
        )
        reasoning_effort = _pick_first(
            local_settings.get("reasoning_effort"),
            os.getenv("AI_REASONING_EFFORT"),
        )
        base_url = None
    else:
        api_key = _pick_first(
            local_settings.get("api_key"),
            os.getenv("AI_API_KEY"),
            os.getenv("OPENAI_API_KEY"),
            os.getenv("GPT_API_KEY"),
        )
        base_url = _pick_first(
            local_settings.get("base_url"),
            os.getenv("AI_BASE_URL"),
            os.getenv("OPENAI_BASE_URL"),
            os.getenv("GPT_BASE_URL"),
            DEFAULT_OPENAI_BASE_URL,
        )
        model = _pick_first(
            local_settings.get("model"),
            os.getenv("AI_MODEL"),
            os.getenv("OPENAI_MODEL_NAME"),
            os.getenv("OPENAI_RESEARCH_MODEL"),
            os.getenv("GPT_SUMMARY_MODEL"),
            DEFAULT_OPENAI_MODEL,
        )
        fallback_models = _split_models(
            local_settings.get("fallback_models")
            or os.getenv("AI_FALLBACK_MODELS")
            or os.getenv("OPENAI_FALLBACK_MODELS")
            or ",".join(DEFAULT_OPENAI_FALLBACK_MODELS)
        )
        reasoning_effort = _pick_first(
            local_settings.get("reasoning_effort"),
            os.getenv("AI_REASONING_EFFORT"),
            os.getenv("OPENAI_REASONING_EFFORT"),
            os.getenv("GPT_REASONING_EFFORT"),
        )

    return AppSettings(
        provider=provider,
        api_key=api_key,
        base_url=base_url.strip() if isinstance(base_url, str) and base_url.strip() else None,
        model=(model or DEFAULT_OPENAI_MODEL).strip(),
        fallback_models=(
            fallback_models
            if fallback_models
            else (
                list(DEFAULT_OPENAI_FALLBACK_MODELS)
                if provider == "openai-compatible"
                else []
            )
        ),
        reasoning_effort=reasoning_effort.strip() if reasoning_effort else None,
    )
