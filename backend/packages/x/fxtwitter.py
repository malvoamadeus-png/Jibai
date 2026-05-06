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


def fetch_user_statuses(
    username: str,
    *,
    count: int = 20,
    cursor: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    params: dict[str, Any] = {"count": max(1, min(int(count), 100))}
    if cursor:
        params["cursor"] = cursor
    response = requests.get(
        f"{API_ROOT}/2/profile/{username}/statuses",
        headers=HEADERS,
        params=params,
        timeout=20,
    )
    if response.status_code == 204:
        return [], None
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        return [], None

    raw_results = payload.get("results")
    results = [item for item in raw_results if isinstance(item, dict)] if isinstance(raw_results, list) else []
    raw_cursor = payload.get("cursor")
    cursor_payload = raw_cursor if isinstance(raw_cursor, dict) else None
    return results, cursor_payload


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
