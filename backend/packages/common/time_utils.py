from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def now_shanghai() -> datetime:
    return datetime.now(SHANGHAI_TZ)


def now_iso() -> str:
    return now_shanghai().isoformat(timespec="seconds")


def today_date_key() -> str:
    return now_shanghai().date().isoformat()


def _parse_datetime(value: str) -> datetime | None:
    raw = value.strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00").replace("/", "-")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(normalized, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=SHANGHAI_TZ)
    return dt.astimezone(SHANGHAI_TZ)


def parse_datetime(value: str | None) -> datetime | None:
    return _parse_datetime(value or "")


def is_older_than_days(value: str | None, *, days: int, reference_time: str | None = None) -> bool:
    if days <= 0:
        return False
    target = parse_datetime(value)
    if target is None:
        return False
    reference = parse_datetime(reference_time) or now_shanghai()
    age = reference - target.astimezone(SHANGHAI_TZ)
    return age.total_seconds() > days * 86400


def note_date_key(publish_time: str | None, fetched_at: str) -> str:
    for candidate in (publish_time or "", fetched_at):
        dt = _parse_datetime(candidate)
        if dt is not None:
            return dt.astimezone(SHANGHAI_TZ).date().isoformat()
    return today_date_key()
