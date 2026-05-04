from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,15}$")
RESERVED_PATHS = {
    "home",
    "explore",
    "i",
    "search",
    "messages",
    "notifications",
    "settings",
    "tos",
    "privacy",
    "compose",
}


def normalize_x_username(value: str) -> str:
    raw = value.strip()
    if not raw:
        raise ValueError("X account cannot be empty.")
    if raw.startswith("@"):
        raw = raw[1:]
    if "://" in raw:
        parsed = urlparse(raw)
        if parsed.netloc.lower() not in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
            raise ValueError("X profile URL must point to x.com or twitter.com.")
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) != 1:
            raise ValueError("X profile URL must be a direct user profile URL.")
        raw = parts[0].lstrip("@")
    username = raw.strip().strip("/")
    if username.lower() in RESERVED_PATHS or not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("Invalid X username.")
    return username.lower()


def profile_url_for_username(username: str) -> str:
    return urlunparse(("https", "x.com", f"/{normalize_x_username(username)}", "", "", ""))
