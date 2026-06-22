from __future__ import annotations

from dataclasses import dataclass


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
