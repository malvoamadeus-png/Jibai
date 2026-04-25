from __future__ import annotations

from datetime import datetime
from typing import Any

import requests

from packages.common.time_utils import SHANGHAI_TZ


API_ROOT = "https://api.fxtwitter.com"
HEADERS = {"User-Agent": "insight-local-x-monitor/1.0"}


def _request_json(url: str) -> dict[str, Any] | None:
    response = requests.get(url, headers=HEADERS, timeout=15)
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else None


def fetch_user_info(username: str) -> dict[str, Any]:
    payload = _request_json(f"{API_ROOT}/{username}") or {}
    user = payload.get("user")
    return user if isinstance(user, dict) else {}


def fetch_tweet_detail(username: str, tweet_id: str) -> dict[str, Any]:
    payload = _request_json(f"{API_ROOT}/{username}/status/{tweet_id}") or {}
    tweet = payload.get("tweet")
    return tweet if isinstance(tweet, dict) else {}


def parse_created_at(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        dt = datetime.strptime(raw, "%a %b %d %H:%M:%S %z %Y")
    except ValueError:
        return None
    return dt.astimezone(SHANGHAI_TZ).isoformat(timespec="seconds")
