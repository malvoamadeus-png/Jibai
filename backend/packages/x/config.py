from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from packages.common.io import safe_filename


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
DEFAULT_NITTER_INSTANCES = [
    "nitter.tiekoetter.com",
    "xcancel.com",
    "nitter.catsarch.com",
]


def _normalize_profile_url(value: str) -> str:
    raw = value.strip()
    if raw and "://" not in raw:
        raw = f"https://{raw.lstrip('/')}"
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("profile_url must be http/https.")
    if parsed.netloc.lower() not in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
        raise ValueError("profile_url must point to x.com or twitter.com.")

    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) != 1:
        raise ValueError("profile_url must be a direct user profile URL.")

    username = path_parts[0].lstrip("@")
    if username.lower() in RESERVED_PATHS or not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("profile_url must contain a valid X username.")

    return urlunparse(("https", "x.com", f"/{username}", "", "", ""))


def username_from_profile_url(profile_url: str) -> str:
    parsed = urlparse(profile_url)
    path_parts = [part for part in parsed.path.split("/") if part]
    if not path_parts:
        raise ValueError("profile_url does not include a username.")
    return path_parts[0].lstrip("@")


class AccountTarget(BaseModel):
    name: str
    profile_url: str
    limit: int = 5

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name cannot be empty.")
        return value.strip()

    @field_validator("profile_url")
    @classmethod
    def _validate_profile_url(cls, value: str) -> str:
        return _normalize_profile_url(value)

    @field_validator("limit")
    @classmethod
    def _validate_limit(cls, value: int) -> int:
        if value < 1 or value > 20:
            raise ValueError("limit must be between 1 and 20.")
        return value

    @property
    def safe_name(self) -> str:
        return safe_filename(self.name, default="account")

    @property
    def username(self) -> str:
        return username_from_profile_url(self.profile_url)


class WatchlistConfig(BaseModel):
    enabled: bool = True
    headless: bool = True
    page_wait_sec: float = 6.0
    inter_account_delay_sec: float = 1.5
    inter_account_delay_jitter_sec: float = 1.0
    exclude_old_posts: bool = True
    max_post_age_days: int = 5
    nitter_instances: list[str] = Field(default_factory=lambda: list(DEFAULT_NITTER_INSTANCES))
    accounts: list[AccountTarget] = Field(default_factory=list)

    @field_validator("page_wait_sec", "inter_account_delay_sec", "inter_account_delay_jitter_sec")
    @classmethod
    def _validate_delay(cls, value: float) -> float:
        if value < 0:
            raise ValueError("delay values must be >= 0.")
        return value

    @field_validator("max_post_age_days")
    @classmethod
    def _validate_max_post_age_days(cls, value: int) -> int:
        if value < 1 or value > 30:
            raise ValueError("max_post_age_days must be between 1 and 30.")
        return value

    @field_validator("nitter_instances")
    @classmethod
    def _validate_instances(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            instance = item.strip().removeprefix("https://").removeprefix("http://").rstrip("/")
            if instance and instance not in cleaned:
                cleaned.append(instance)
        if not cleaned:
            raise ValueError("nitter_instances must include at least one instance.")
        return cleaned

    @field_validator("accounts")
    @classmethod
    def _validate_accounts(
        cls,
        value: list[AccountTarget],
        info: ValidationInfo,
    ) -> list[AccountTarget]:
        enabled = info.data.get("enabled", True)
        if enabled and not value:
            raise ValueError("watchlist must include at least one account.")
        return value


def load_watchlist(path: str) -> WatchlistConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    return WatchlistConfig.model_validate(payload)
