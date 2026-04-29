from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from packages.common.io import safe_filename


def _normalize_profile_url(value: str) -> str:
    raw = value.strip()
    if raw and "://" not in raw:
        raw = f"https://{raw.lstrip('/')}"
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("profile_url must be http/https.")
    if "/user/profile/" not in parsed.path:
        raise ValueError("profile_url must be a full Xiaohongshu profile URL.")

    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    if not any(key == "xsec_token" and item for key, item in query_items):
        raise ValueError("profile_url must include xsec_token.")

    normalized_query = urlencode(query_items)
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            normalized_query,
            "",
        )
    )


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
    def site(self) -> str:
        return "rednote" if "rednote.com" in self.profile_url else "xiaohongshu"


class WatchlistConfig(BaseModel):
    enabled: bool = True
    browser_channel: str | None = "chrome"
    headless: bool = False
    inter_account_delay_sec: float = 5.0
    inter_account_delay_jitter_sec: float = 3.0
    detail_delay_sec: float = 0.8
    detail_fallback_enabled: bool = True
    detail_fallback_limit_per_account: int = 2
    exclude_old_posts: bool = True
    max_post_age_days: int = 5
    accounts: list[AccountTarget] = Field(default_factory=list)

    @field_validator(
        "inter_account_delay_sec",
        "inter_account_delay_jitter_sec",
        "detail_delay_sec",
    )
    @classmethod
    def _validate_delay(cls, value: float) -> float:
        if value < 0:
            raise ValueError("delay values must be >= 0.")
        return value

    @field_validator("detail_fallback_limit_per_account")
    @classmethod
    def _validate_fallback_limit(cls, value: int) -> int:
        if value < 0 or value > 5:
            raise ValueError("detail_fallback_limit_per_account must be between 0 and 5.")
        return value

    @field_validator("max_post_age_days")
    @classmethod
    def _validate_max_post_age_days(cls, value: int) -> int:
        if value < 1 or value > 30:
            raise ValueError("max_post_age_days must be between 1 and 30.")
        return value

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
