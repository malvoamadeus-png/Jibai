from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ChainSpec:
    key: str
    label: str
    chain_index: str
    is_evm: bool


SUPPORTED_CHAINS: tuple[ChainSpec, ...] = (
    ChainSpec(key="ethereum", label="Ethereum", chain_index="1", is_evm=True),
    ChainSpec(key="base", label="Base", chain_index="8453", is_evm=True),
    ChainSpec(key="bsc", label="BSC", chain_index="56", is_evm=True),
    ChainSpec(key="solana", label="Solana", chain_index="501", is_evm=False),
)

CHAIN_BY_KEY = {chain.key: chain for chain in SUPPORTED_CHAINS}
CHAIN_BY_INDEX = {chain.chain_index: chain for chain in SUPPORTED_CHAINS}


@dataclass(frozen=True, slots=True)
class OnchainWallet:
    id: str
    address: str
    admin_label: str
    chain_key: str
    chain_index: str


@dataclass(frozen=True, slots=True)
class TokenBalance:
    wallet_id: str
    address: str
    chain_key: str
    chain_index: str
    token_key: str
    token_contract_address: str
    symbol: str
    display_name: str
    balance: Decimal
    raw_balance: Decimal
    token_price_usd: Decimal
    holding_value_usd: Decimal
    is_native: bool
    is_risk_token: bool
    excluded: bool
    exclusion_reason: str


@dataclass(frozen=True, slots=True)
class FetchItemResult:
    wallet_id: str
    chain_key: str
    chain_index: str
    status: str
    token_count: int
    visible_token_count: int
    error_text: str = ""


@dataclass(frozen=True, slots=True)
class FetchRunResult:
    run_id: str
    status: str
    summary: str
    item_results: list[FetchItemResult]
    visible_balances: int
