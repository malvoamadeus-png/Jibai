from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .io import read_json, safe_filename
from .paths import AppPaths


@dataclass(frozen=True, slots=True)
class SecurityIdentity:
    security_key: str
    display_name: str
    ticker: str | None = None
    market: str | None = None


_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
_SPACE_RE = re.compile(r"\s+")
_SPLIT_RE = re.compile(r"[/\\|｜／]+")
_GENERIC_MARKERS = (
    "对应标的",
    "未明确提及具体公司",
    "龙头公司",
    "相关标的",
    "某公司",
    "某股",
    "收益来源",
)
_GENERIC_EXACT = {
    "股票",
    "个股",
    "标的",
    "公司",
    "大哥",
}
_TICKER_WITH_SUFFIX_RE = re.compile(r"\b([A-Z0-9]{1,10})\.([A-Z]{1,4})\b", re.IGNORECASE)
_PLAIN_TICKER_RE = re.compile(r"\b[A-Z][A-Z0-9]{0,9}(?:\.[A-Z])?\b")
_A_SHARE_WITH_SUFFIX_RE = re.compile(r"\b(\d{6})\.(SZ|SH|SS)\b", re.IGNORECASE)
_A_SHARE_CODE_RE = re.compile(r"\b\d{6}\b")
_MARKET_SUFFIX_MAP = {
    "SZ": "SZSE",
    "SH": "SSE",
    "SS": "SSE",
    "BJ": "BJSE",
    "KS": "KRX",
    "KQ": "KOSDAQ",
    "L": "LSE",
    "PA": "EPA",
    "AS": "EURONEXT",
    "BR": "EBR",
    "MI": "XMIL",
    "SW": "SIX",
    "TO": "TSX",
    "V": "TSXV",
    "DE": "XETRA",
}


def _normalize_alias_key(value: str) -> str:
    return _SPACE_RE.sub(" ", value.strip()).casefold()


def _strip_wrappers(value: str) -> str:
    return value.strip().strip("[](){}<>:;,，。；·")


def _has_chinese(value: str) -> bool:
    return bool(_CHINESE_RE.search(value))


def _clean_segment(value: str) -> str:
    cleaned = _strip_wrappers(value)
    if not cleaned:
        return ""

    for pattern in (
        r"(?i)^代码\s*([A-Z0-9.]+)(?:对应标的)?$",
        r"(?i)^([A-Z0-9.]+)\s*代码对应标的$",
        r"(?i)^([A-Z0-9.]+)\s*对应标的$",
    ):
        match = re.match(pattern, cleaned)
        if match:
            return match.group(1).upper()

    cleaned = re.sub(r"(?i)^代码\s*", "", cleaned).strip()
    cleaned = re.sub(r"(?i)对应标的$", "", cleaned).strip()
    cleaned = re.sub(r"(?i)代码$", "", cleaned).strip()
    return _strip_wrappers(cleaned)


def _split_candidates(*values: str) -> list[str]:
    candidates: list[str] = []
    for raw in values:
        text = raw.strip()
        if not text:
            continue
        parts = _SPLIT_RE.split(text)
        items = parts if len(parts) > 1 else [text]
        for item in items:
            cleaned = _clean_segment(item)
            if cleaned and cleaned not in candidates:
                candidates.append(cleaned)
    return candidates


def _looks_generic(value: str) -> bool:
    compact = value.strip().casefold()
    if not compact:
        return True
    if compact in {item.casefold() for item in _GENERIC_EXACT}:
        return True
    return any(marker.casefold() in compact for marker in _GENERIC_MARKERS)


def _normalize_market(market: str | None) -> str | None:
    if not market:
        return None
    raw = market.strip().upper()
    if not raw:
        return None
    aliases = {
        "NASDAQ": "NASDAQ",
        "NYSE": "NYSE",
        "AMEX": "AMEX",
        "SSE": "SSE",
        "SH": "SSE",
        "SZSE": "SZSE",
        "SZ": "SZSE",
        "BJSE": "BJSE",
        "BJ": "BJSE",
        "KRX": "KRX",
        "KOSDAQ": "KOSDAQ",
        "LSE": "LSE",
        "XLON": "LSE",
        "XETRA": "XETRA",
        "XETR": "XETRA",
        "EPA": "EPA",
        "EURONEXT": "EURONEXT",
        "EBR": "EBR",
        "XMIL": "XMIL",
        "SIX": "SIX",
        "TSX": "TSX",
        "TSXV": "TSXV",
    }
    return aliases.get(raw, raw)


def _infer_a_share_market(code: str) -> str | None:
    if len(code) != 6 or not code.isdigit():
        return None
    if code.startswith(("000", "001", "002", "003", "300", "301")):
        return "SZSE"
    if code.startswith(("600", "601", "603", "605", "688", "689")):
        return "SSE"
    if code.startswith(("430", "830", "831", "832", "833", "834", "835", "836", "837", "838", "839", "870", "871", "872", "873", "874", "875", "876", "920")):
        return "BJSE"
    return None


def _extract_ticker_and_market(*values: str) -> tuple[str | None, str | None]:
    for raw in values:
        text = raw.strip()
        if not text:
            continue

        match = _A_SHARE_WITH_SUFFIX_RE.search(text)
        if match:
            ticker = match.group(1)
            market = _normalize_market(match.group(2))
            return ticker, market

        match = _TICKER_WITH_SUFFIX_RE.search(text)
        if match:
            ticker = match.group(1).upper()
            suffix = match.group(2).upper()
            if suffix in _MARKET_SUFFIX_MAP:
                market = _normalize_market(_MARKET_SUFFIX_MAP[suffix])
                return ticker, market

        match = _A_SHARE_CODE_RE.search(text)
        if match:
            ticker = match.group(0)
            market = _infer_a_share_market(ticker)
            if market:
                return ticker, market

    for raw in values:
        text = raw.strip()
        if not text:
            continue
        match = _PLAIN_TICKER_RE.search(text.upper())
        if match:
            return match.group(0).upper(), None

    return None, None


def _lookup_alias(
    aliases: dict[str, SecurityIdentity],
    *values: str,
) -> SecurityIdentity | None:
    seen: set[str] = set()
    for candidate in _split_candidates(*values):
        lookup_key = _normalize_alias_key(candidate)
        if not lookup_key or lookup_key in seen:
            continue
        seen.add(lookup_key)
        if lookup_key in aliases:
            return aliases[lookup_key]
    return None


def _pick_display_name(
    ticker: str | None,
    *values: str,
) -> str:
    candidates = [item for item in _split_candidates(*values) if not _looks_generic(item)]
    chinese = [item for item in candidates if _has_chinese(item)]
    if chinese:
        return chinese[0]

    named = [item for item in candidates if not ticker or item.upper() != ticker.upper()]
    if named:
        named.sort(key=lambda item: (len(item), item), reverse=True)
        return named[0]

    if ticker:
        return ticker

    if candidates:
        return candidates[0]

    return ""


def _build_security_key(
    raw_name: str,
    display_name: str,
    ticker: str | None,
    market: str | None,
) -> str:
    raw_text = raw_name.strip()
    raw_is_plain_ticker = bool(raw_text) and bool(_PLAIN_TICKER_RE.fullmatch(raw_text.upper()))

    if ticker:
        normalized_market = _normalize_market(market)
        if normalized_market == "SZSE":
            return f"{ticker}.sz"
        if normalized_market == "SSE":
            return f"{ticker}.sh"
        if normalized_market == "BJSE":
            return f"{ticker}.bj"
        if normalized_market in {"KRX", "KOSDAQ"}:
            return f"{ticker}.{normalized_market.casefold()}"
        if raw_is_plain_ticker or not _has_chinese(display_name):
            return ticker.casefold()

    return safe_filename(display_name.casefold(), default="security")


def load_security_aliases(paths: AppPaths) -> dict[str, SecurityIdentity]:
    payload = read_json(paths.security_aliases_path, default={}) or {}
    aliases: dict[str, SecurityIdentity] = {}
    if not isinstance(payload, dict):
        return aliases
    for alias, raw in payload.items():
        if not isinstance(alias, str) or not alias.strip() or not isinstance(raw, dict):
            continue
        security_key = str(raw.get("security_key") or "").strip()
        display_name = str(raw.get("display_name") or alias).strip()
        if not security_key or not display_name:
            continue
        aliases[_normalize_alias_key(alias)] = SecurityIdentity(
            security_key=security_key,
            display_name=display_name,
            ticker=str(raw.get("ticker") or "").strip() or None,
            market=_normalize_market(str(raw.get("market") or "").strip() or None),
        )
    return aliases


def resolve_security_identity(
    raw_name: str,
    stock_name: str | None,
    aliases: dict[str, SecurityIdentity],
) -> SecurityIdentity | None:
    alias_hit = _lookup_alias(aliases, raw_name, stock_name or "")
    if alias_hit is not None:
        return alias_hit

    ticker, market = _extract_ticker_and_market(raw_name, stock_name or "")
    display_name = _pick_display_name(ticker, stock_name or "", raw_name)
    if not display_name:
        return None
    if _looks_generic(display_name) and not ticker:
        return None
    if ticker and display_name.upper() == ticker.upper():
        display_name = ticker

    return SecurityIdentity(
        security_key=_build_security_key(raw_name, display_name, ticker, market),
        display_name=display_name,
        ticker=ticker,
        market=market,
    )


def dump_security_aliases_example() -> str:
    payload = {
        "谷歌": {
            "security_key": "google",
            "display_name": "Google",
            "ticker": "GOOGL",
            "market": "NASDAQ",
        },
        "Google": {
            "security_key": "google",
            "display_name": "Google",
            "ticker": "GOOGL",
            "market": "NASDAQ",
        },
        "三星": {
            "security_key": "samsung",
            "display_name": "三星电子",
            "ticker": "005930",
            "market": "KRX",
        },
        "Samsung": {
            "security_key": "samsung",
            "display_name": "三星电子",
            "ticker": "005930",
            "market": "KRX",
        },
        "英伟达": {
            "security_key": "nvidia",
            "display_name": "英伟达",
            "ticker": "NVDA",
            "market": "NASDAQ",
        },
        "NVIDIA": {
            "security_key": "nvidia",
            "display_name": "英伟达",
            "ticker": "NVDA",
            "market": "NASDAQ",
        },
        "新易盛": {
            "security_key": "300502.sz",
            "display_name": "新易盛",
            "ticker": "300502",
            "market": "SZSE",
        },
        "XYS": {
            "security_key": "300502.sz",
            "display_name": "新易盛",
            "ticker": "300502",
            "market": "SZSE",
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
