from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_BACKEND = "browser"
DEFAULT_TIMEOUT_SECONDS = 180


@dataclass(frozen=True, slots=True)
class XSearchTweet:
    url: str
    author: str
    author_name: str
    text: str
    created_at: str
    tweet_id: str
    likes: int
    retweets: int
    replies: int
    views: int
    title: str
    snippet: str
    query_variant: str


@dataclass(frozen=True, slots=True)
class XSearchResult:
    query: str
    backend: str
    search_queries: list[str]
    tweets: list[XSearchTweet]
    warning: str | None = None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _fetch_script_path() -> Path:
    return _repo_root() / "Reference" / "x-tweet-fetcher" / "scripts" / "fetch_tweet.py"


def _timeout_seconds() -> int:
    try:
        return max(30, int(os.getenv("PUBLIC_X_SEARCH_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))))
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS


def _backend_name() -> str:
    value = os.getenv("PUBLIC_X_SEARCH_BACKEND", DEFAULT_BACKEND).strip().lower()
    return value if value in {"auto", "nitter", "browser"} else DEFAULT_BACKEND


def _extract_json_payload(stdout: str) -> dict[str, Any]:
    text = stdout.strip()
    if not text:
        raise RuntimeError("x search returned empty stdout")
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError("x search stdout did not contain JSON")
    payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise RuntimeError("x search JSON payload is not an object")
    return payload


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _normalize_tweet(raw: Any) -> XSearchTweet | None:
    if not isinstance(raw, dict):
        return None
    url = str(raw.get("url") or "").strip()
    if not url:
        return None
    return XSearchTweet(
        url=url,
        author=str(raw.get("author") or "").strip(),
        author_name=str(raw.get("author_name") or "").strip(),
        text=str(raw.get("text") or "").strip(),
        created_at=str(raw.get("created_at") or raw.get("time_ago") or "").strip(),
        tweet_id=str(raw.get("tweet_id") or "").strip(),
        likes=_as_int(raw.get("likes")),
        retweets=_as_int(raw.get("retweets")),
        replies=_as_int(raw.get("replies")),
        views=_as_int(raw.get("views")),
        title=str(raw.get("title") or "").strip(),
        snippet=str(raw.get("snippet") or "").strip(),
        query_variant=str(raw.get("query_variant") or "").strip(),
    )


def search_x_posts(query: str, *, limit: int = 20, backend: str | None = None) -> XSearchResult:
    script_path = _fetch_script_path()
    if not script_path.exists():
        raise RuntimeError(f"x search script not found: {script_path}")

    safe_backend = backend or _backend_name()
    safe_limit = max(1, min(int(limit), 50))
    command = [
        sys.executable,
        str(script_path),
        "--search",
        query,
        "--limit",
        str(safe_limit),
        "--backend",
        safe_backend,
    ]
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    completed = subprocess.run(
        command,
        cwd=str(script_path.parent),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_timeout_seconds(),
        env=env,
        check=False,
    )
    if completed.returncode != 0 and not completed.stdout.strip():
        stderr = " ".join(completed.stderr.split())[:400]
        raise RuntimeError(f"x search failed exit={completed.returncode} stderr={stderr}")

    payload = _extract_json_payload(completed.stdout)
    error_text = str(payload.get("error") or "").strip()
    if error_text:
        raise RuntimeError(error_text[:400])

    tweets = [
        tweet
        for item in (payload.get("tweets") or [])
        if (tweet := _normalize_tweet(item)) is not None
    ]
    return XSearchResult(
        query=str(payload.get("query") or query),
        backend=str(payload.get("backend") or safe_backend),
        search_queries=[
            str(item).strip()
            for item in (payload.get("search_queries") or [])
            if str(item).strip()
        ],
        tweets=tweets,
        warning=str(payload.get("warning") or "").strip() or None,
    )
