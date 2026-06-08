from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path
from typing import Any

from .models import ScoringConfig


def normalize_account(raw: str) -> str:
    value = raw.strip()
    if value.startswith("@"):
        value = value[1:]
    if "://" in value:
        from urllib.parse import urlparse

        parsed = urlparse(value)
        value = parsed.path.strip("/").split("/", 1)[0]
    return value.strip().lstrip("@")


def load_config(path: Path | None = None) -> ScoringConfig:
    if path is None or not path.exists():
        return ScoringConfig()

    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"Scoring config must be a JSON object: {path}")

    allowed = {item.name for item in fields(ScoringConfig)}
    values: dict[str, Any] = {key: value for key, value in payload.items() if key in allowed}
    if "score_scales" not in values and "score_caps" in payload:
        values["score_scales"] = payload["score_caps"]
    if "accounts" in values:
        values["accounts"] = [normalize_account(str(item)) for item in values["accounts"] if str(item).strip()]
    if "horizons" in values:
        values["horizons"] = tuple(int(item) for item in values["horizons"])
    return ScoringConfig(**values)


def dump_example_config() -> str:
    config = ScoringConfig()
    payload = {
        "accounts": [f"@{item}" for item in config.accounts],
        "history_days": config.history_days,
        "price_days": config.price_days,
        "benchmark_symbol": config.benchmark_symbol,
        "benchmark_fallback_symbol": config.benchmark_fallback_symbol,
        "a_share_benchmark_symbol": config.a_share_benchmark_symbol,
        "a_share_benchmark_fallback_symbol": config.a_share_benchmark_fallback_symbol,
        "a_share_benchmark_extra_symbols": config.a_share_benchmark_extra_symbols,
        "horizons": list(config.horizons),
        "horizon_weights": config.horizon_weights,
        "score_scales": config.score_scales,
        "conviction_weights": config.conviction_weights,
        "min_ranked_events": config.min_ranked_events,
        "full_confidence_events": config.full_confidence_events,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
