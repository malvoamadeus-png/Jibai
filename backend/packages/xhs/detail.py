from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from lxml.etree import HTML
from yaml import safe_load

INITIAL_STATE_PREFIX = "window.__INITIAL_STATE__="
INITIAL_STATE_XPATH = "//script/text()"
ILLEGAL_YAML_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

PHONE_NOTE_KEYS = ("noteData", "data", "noteData")
PC_NOTE_KEYS = ("note", "noteDetailMap", "[-1]", "note")

DEFAULT_HEADERS = {
    "accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
        "image/webp,image/apng,*/*;q=0.8"
    ),
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
    "referer": "https://www.xiaohongshu.com/",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
    ),
}


@dataclass(slots=True)
class NoteText:
    note_id: str
    url: str
    title: str
    desc: str
    author_id: str
    author_nickname: str
    note_type: str
    publish_time: str | None
    last_update_time: str | None
    like_count: int | None
    collect_count: int | None
    comment_count: int | None
    share_count: int | None


@dataclass(slots=True)
class NoteFetchContext:
    requested_url: str
    final_url: str
    status_code: int | None
    page_title: str = ""
    anonymous_detail_error: str | None = None


class NoteFetchError(RuntimeError):
    def __init__(self, message: str, *, code: str, context: NoteFetchContext):
        super().__init__(message)
        self.code = code
        self.context = context

    @property
    def is_anonymous_access_restricted(self) -> bool:
        return self.code == "anonymous_access_restricted"


def create_client(cookie: str = "", proxy: str | None = None) -> httpx.Client:
    headers = DEFAULT_HEADERS.copy()
    if cookie:
        headers["cookie"] = cookie
    return httpx.Client(
        headers=headers,
        follow_redirects=True,
        timeout=20,
        proxy=proxy,
        trust_env=True,
    )


def fetch_response(client: httpx.Client, url: str) -> httpx.Response:
    return client.get(url)


def find_initial_state_script(html: str) -> str:
    tree = HTML(html)
    if tree is None:
        raise ValueError("Failed to parse detail page HTML.")
    scripts = tree.xpath(INITIAL_STATE_XPATH)
    for script in reversed(scripts):
        if isinstance(script, str) and script.startswith(INITIAL_STATE_PREFIX):
            return script
    raise ValueError("window.__INITIAL_STATE__ not found in detail page.")


def parse_initial_state(html: str) -> dict[str, Any]:
    script = find_initial_state_script(html)
    cleaned = ILLEGAL_YAML_CHARS.sub("", script.removeprefix(INITIAL_STATE_PREFIX))
    cleaned = cleaned.strip()
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1]
    data = safe_load(cleaned)
    if not isinstance(data, dict):
        raise ValueError("window.__INITIAL_STATE__ is not an object.")
    return data


def deep_get(data: Any, keys: tuple[str, ...], default: Any = None) -> Any:
    current = data
    for key in keys:
        if isinstance(key, str) and key.startswith("[") and key.endswith("]"):
            index = int(key[1:-1])
            if isinstance(current, dict):
                values = list(current.values())
                if -len(values) <= index < len(values):
                    current = values[index]
                    continue
                return default
            if isinstance(current, list):
                if -len(current) <= index < len(current):
                    current = current[index]
                    continue
                return default
            return default
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def extract_note_payload(state: dict[str, Any]) -> dict[str, Any]:
    note = deep_get(state, PHONE_NOTE_KEYS) or deep_get(state, PC_NOTE_KEYS) or {}
    if not isinstance(note, dict) or not note:
        raise ValueError("Note payload not found in detail page state.")
    return note


def normalize_time(timestamp_ms: Any) -> str | None:
    if not timestamp_ms:
        return None
    try:
        return datetime.fromtimestamp(int(timestamp_ms) / 1000).isoformat(sep=" ")
    except (TypeError, ValueError, OSError):
        return None


def to_int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_note(url: str, payload: dict[str, Any]) -> NoteText:
    user = payload.get("user") or {}
    interact = payload.get("interactInfo") or {}
    return NoteText(
        note_id=str(payload.get("noteId") or ""),
        url=url,
        title=str(payload.get("title") or ""),
        desc=str(payload.get("desc") or ""),
        author_id=str(user.get("userId") or ""),
        author_nickname=str(user.get("nickname") or user.get("nickName") or ""),
        note_type=str(payload.get("type") or ""),
        publish_time=normalize_time(payload.get("time")),
        last_update_time=normalize_time(payload.get("lastUpdateTime")),
        like_count=to_int_or_none(interact.get("likedCount")),
        collect_count=to_int_or_none(interact.get("collectedCount")),
        comment_count=to_int_or_none(interact.get("commentCount")),
        share_count=to_int_or_none(interact.get("shareCount")),
    )


def extract_page_title(html: str) -> str:
    tree = HTML(html)
    if tree is None:
        return ""
    titles = tree.xpath("//title/text()")
    for title in titles:
        if isinstance(title, str) and title.strip():
            return title.strip()
    return ""


def classify_anonymous_detail_error(final_url: str) -> str | None:
    parsed = urlparse(final_url)
    query = parse_qs(parsed.query)
    if "website-login/error" in parsed.path:
        error_code = (query.get("error_code") or [""])[0].strip()
        return (
            f"xhs_login_required_{error_code}"
            if error_code
            else "xhs_login_required"
        )
    if parsed.path == "/404" and (
        query.get("noteId")
        or query.get("errorCode")
        or (query.get("source") or [""])[0] == "note"
    ):
        error_code = (query.get("errorCode") or [""])[0].strip()
        return f"xhs_404_{error_code}" if error_code else "xhs_404_restricted"
    return None


def fetch_note_text(client: httpx.Client, url: str) -> NoteText:
    try:
        response = fetch_response(client, url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        final_url = str(getattr(getattr(exc, "response", None), "url", url))
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        context = NoteFetchContext(
            requested_url=url,
            final_url=final_url,
            status_code=status_code,
        )
        raise NoteFetchError(
            f"Detail request failed: {exc}",
            code="request_error",
            context=context,
        ) from exc

    html = response.text
    final_url = str(response.url)
    page_title = extract_page_title(html)
    anonymous_detail_error = classify_anonymous_detail_error(final_url)
    context = NoteFetchContext(
        requested_url=url,
        final_url=final_url,
        status_code=response.status_code,
        page_title=page_title,
        anonymous_detail_error=anonymous_detail_error,
    )
    if anonymous_detail_error:
        raise NoteFetchError(
            f"Anonymous detail access restricted: {anonymous_detail_error}",
            code="anonymous_access_restricted",
            context=context,
        )

    try:
        state = parse_initial_state(html)
        payload = extract_note_payload(state)
        return normalize_note(url, payload)
    except ValueError as exc:
        raise NoteFetchError(
            str(exc),
            code="parse_error",
            context=context,
        ) from exc
