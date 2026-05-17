from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from .models import CHAIN_BY_INDEX


def parse_decimal(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def decimal_to_str(value: Decimal) -> str:
    normalized = value.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def normalize_address(value: Any, *, is_evm: bool = True) -> str:
    raw = str(value or "").strip()
    return raw.lower() if is_evm else raw


def short_address(value: str) -> str:
    raw = str(value or "").strip()
    if len(raw) <= 14:
        return raw
    return f"{raw[:6]}...{raw[-4:]}"


def token_key(
    *,
    chain_index: str,
    token_contract_address: str,
    symbol: str,
    is_evm: bool = True,
) -> str:
    normalized_chain = str(chain_index or "").strip()
    normalized_token = normalize_address(token_contract_address, is_evm=is_evm)
    if normalized_token:
        return f"{normalized_chain}:{normalized_token}"
    return f"{normalized_chain}:native:{str(symbol or '').strip().upper()}"


def chain_key_for_index(chain_index: str) -> str:
    chain = CHAIN_BY_INDEX.get(str(chain_index or "").strip())
    return chain.key if chain else ""
