from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field, field_validator


DEFAULT_SCHEDULE_TIMES = ["10:00", "22:00"]


class RuntimeSettings(BaseModel):
    schedule_times: list[str] = Field(default_factory=lambda: list(DEFAULT_SCHEDULE_TIMES))

    @field_validator("schedule_times")
    @classmethod
    def _validate_schedule_times(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            raw = item.strip()
            if not raw:
                continue
            parts = raw.split(":", 1)
            if len(parts) != 2:
                raise ValueError("schedule_times must use HH:MM format.")
            try:
                hour = int(parts[0])
                minute = int(parts[1])
            except ValueError as exc:
                raise ValueError("schedule_times must use HH:MM format.") from exc
            if hour < 0 or hour > 23 or minute < 0 or minute > 59:
                raise ValueError("schedule_times must use valid HH:MM values.")
            normalized = f"{hour:02d}:{minute:02d}"
            if normalized not in cleaned:
                cleaned.append(normalized)
        if not cleaned:
            raise ValueError("schedule_times must include at least one time.")
        return cleaned


def load_runtime_settings(path: str | Path) -> RuntimeSettings:
    config_path = Path(path)
    if not config_path.exists():
        return RuntimeSettings()
    payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
    return RuntimeSettings.model_validate(payload)
