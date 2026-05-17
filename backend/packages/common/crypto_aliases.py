from __future__ import annotations

import re
from dataclasses import dataclass, replace

from .io import read_json, safe_filename
from .paths import AppPaths


@dataclass(frozen=True, slots=True)
class CryptoIdentity:
    asset_key: str
    display_name: str
    symbol: str | None = None
    identifier_type: str = "unknown"
    raw_identifiers: tuple[str, ...] = ()
    contract_addresses: tuple[str, ...] = ()
    x_accounts: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    chain: str | None = None
    normalized_status: str = "temporary"


_SPACE_RE = re.compile(r"\s+")
_EVM_CA_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
_SOLANA_ADDR_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
_X_ACCOUNT_RE = re.compile(r"^@[A-Za-z0-9_]{1,15}$")
_SYMBOL_RE = re.compile(r"^\$?[A-Za-z][A-Za-z0-9_]{1,20}$")


def _normalize_lookup(value: str) -> str:
    return _SPACE_RE.sub(" ", value.strip()).casefold()


def _clean_identifier(value: str) -> str:
    return value.strip().strip("[](){}<>:;,，。；")


def _dedupe(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in values:
        item = _clean_identifier(str(raw))
        if not item:
            continue
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return tuple(result)


def infer_identifier_type(identifier: str) -> str:
    value = _clean_identifier(identifier)
    if _EVM_CA_RE.fullmatch(value):
        return "evm_contract"
    if _X_ACCOUNT_RE.fullmatch(value):
        return "project_account"
    if _SOLANA_ADDR_RE.fullmatch(value):
        return "solana_address"
    if _SYMBOL_RE.fullmatch(value):
        return "symbol"
    return "project_name"


def _asset_key_from_identifier(identifier: str, identifier_type: str) -> str:
    value = _clean_identifier(identifier)
    if identifier_type == "evm_contract":
        return f"ca:{value.lower()}"
    if identifier_type == "solana_address":
        return f"sol:{value}"
    if identifier_type == "project_account":
        return "x:" + value.lstrip("@").casefold()
    if identifier_type == "meme_ticker":
        return "meme:" + value.lstrip("$").casefold()
    if identifier_type == "symbol":
        return "sym:" + value.lstrip("$").casefold()
    return "tmp:" + safe_filename(value.casefold(), default="crypto")


def _identity_from_payload(alias: str, payload: dict[str, object]) -> CryptoIdentity | None:
    asset_key = str(payload.get("asset_key") or "").strip()
    display_name = str(payload.get("display_name") or alias).strip()
    if not asset_key or not display_name:
        return None
    raw_identifiers = _dedupe([alias, *(payload.get("raw_identifiers") or [])]) if isinstance(payload.get("raw_identifiers"), list) else _dedupe([alias])
    aliases = _dedupe(payload.get("aliases") or []) if isinstance(payload.get("aliases"), list) else ()
    contract_addresses = (
        _dedupe(payload.get("contract_addresses") or [])
        if isinstance(payload.get("contract_addresses"), list)
        else ()
    )
    x_accounts = _dedupe(payload.get("x_accounts") or []) if isinstance(payload.get("x_accounts"), list) else ()
    return CryptoIdentity(
        asset_key=asset_key,
        display_name=display_name,
        symbol=str(payload.get("symbol") or "").strip() or None,
        identifier_type=str(payload.get("identifier_type") or "project_name").strip() or "project_name",
        raw_identifiers=raw_identifiers,
        contract_addresses=contract_addresses,
        x_accounts=x_accounts,
        aliases=aliases,
        chain=str(payload.get("chain") or "").strip() or None,
        normalized_status=str(payload.get("normalized_status") or "canonical").strip() or "canonical",
    )


def _register_identity(aliases: dict[str, CryptoIdentity], identity: CryptoIdentity) -> None:
    keys = [
        identity.asset_key,
        identity.display_name,
        *(identity.raw_identifiers or ()),
        *(identity.aliases or ()),
        *(identity.contract_addresses or ()),
        *(identity.x_accounts or ()),
    ]
    if identity.symbol:
        keys.extend([identity.symbol, f"${identity.symbol}"])
    for key in keys:
        lookup = _normalize_lookup(key)
        if lookup:
            aliases[lookup] = identity


def load_crypto_aliases(paths: AppPaths) -> dict[str, CryptoIdentity]:
    payload = read_json(paths.config_dir / "crypto_aliases.json", default={}) or {}
    aliases: dict[str, CryptoIdentity] = {}
    if not isinstance(payload, dict):
        return aliases
    for alias, raw in payload.items():
        if not isinstance(alias, str) or not alias.strip() or not isinstance(raw, dict):
            continue
        identity = _identity_from_payload(alias, raw)
        if identity is not None:
            _register_identity(aliases, identity)
    return aliases


def resolve_crypto_identity(
    *,
    entity_name: str,
    entity_code_or_name: str | None = None,
    entity_identifier_type: str | None = None,
    raw_identifiers: list[str] | None = None,
    aliases: dict[str, CryptoIdentity] | None = None,
) -> CryptoIdentity | None:
    candidates = _dedupe(
        [
            *(raw_identifiers or []),
            entity_code_or_name or "",
            entity_name,
        ]
    )
    alias_map = aliases or {}
    for candidate in candidates:
        hit = alias_map.get(_normalize_lookup(candidate))
        if hit is not None:
            merged_raw = _dedupe([*hit.raw_identifiers, *candidates])
            return replace(hit, raw_identifiers=merged_raw)

    primary = next((item for item in candidates if item), "")
    if not primary:
        return None
    identifier_type = entity_identifier_type or infer_identifier_type(primary)
    if identifier_type == "unknown":
        identifier_type = infer_identifier_type(primary)
    display_name = entity_name.strip() or entity_code_or_name or primary
    symbol = None
    if identifier_type in {"symbol", "meme_ticker"}:
        symbol = primary.lstrip("$").upper()
    elif entity_code_or_name and infer_identifier_type(entity_code_or_name) == "symbol":
        symbol = entity_code_or_name.lstrip("$").upper()

    contract_addresses = tuple(item for item in candidates if infer_identifier_type(item) == "evm_contract")
    x_accounts = tuple(item for item in candidates if infer_identifier_type(item) == "project_account")
    return CryptoIdentity(
        asset_key=_asset_key_from_identifier(primary, identifier_type),
        display_name=display_name,
        symbol=symbol,
        identifier_type=identifier_type,
        raw_identifiers=candidates,
        contract_addresses=contract_addresses,
        x_accounts=x_accounts,
        aliases=(),
        chain="EVM" if identifier_type == "evm_contract" else "Solana" if identifier_type == "solana_address" else None,
        normalized_status="temporary",
    )
