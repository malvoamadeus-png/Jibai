from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator


DEFAULT_XIAOHONGSHU_SCHEDULE_TIMES = ["10:00", "22:00"]
DEFAULT_X_SCHEDULE_TIMES = ["10:00", "22:00"]


class RuntimeSettings(BaseModel):
    xiaohongshu_schedule_times: list[str] = Field(
        default_factory=lambda: list(DEFAULT_XIAOHONGSHU_SCHEDULE_TIMES)
    )
    x_schedule_times: list[str] = Field(default_factory=lambda: list(DEFAULT_X_SCHEDULE_TIMES))

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_schedule_times(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        legacy_schedule_times = payload.get("schedule_times")
        if "xhs_schedule_times" in payload and "xiaohongshu_schedule_times" not in payload:
            payload["xiaohongshu_schedule_times"] = payload["xhs_schedule_times"]
        if legacy_schedule_times is not None:
            payload.setdefault("xiaohongshu_schedule_times", legacy_schedule_times)
            payload.setdefault("x_schedule_times", legacy_schedule_times)
        return payload

    @field_validator("xiaohongshu_schedule_times", "x_schedule_times")
    @classmethod
    def _validate_schedule_times(
        cls,
        value: list[str],
        info: ValidationInfo,
    ) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            raw = item.strip()
            if not raw:
                continue
            parts = raw.split(":", 1)
            if len(parts) != 2:
                raise ValueError(f"{info.field_name} must use HH:MM format.")
            try:
                hour = int(parts[0])
                minute = int(parts[1])
            except ValueError as exc:
                raise ValueError(f"{info.field_name} must use HH:MM format.") from exc
            if hour < 0 or hour > 23 or minute < 0 or minute > 59:
                raise ValueError(f"{info.field_name} must use valid HH:MM values.")
            normalized = f"{hour:02d}:{minute:02d}"
            if normalized not in cleaned:
                cleaned.append(normalized)
        if not cleaned:
            raise ValueError(f"{info.field_name} must include at least one time.")
        return cleaned


def load_runtime_settings(path: str | Path) -> RuntimeSettings:
    config_path = Path(path)
    if not config_path.exists():
        return RuntimeSettings()
    payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
    return RuntimeSettings.model_validate(payload)
