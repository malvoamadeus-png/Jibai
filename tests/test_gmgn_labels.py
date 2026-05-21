from __future__ import annotations

from typing import Any

from packages.onchain.gmgn_labels import (
    MAX_GMGN_LIMIT,
    fetch_gmgn_label_results,
    fetch_token_result,
)


class FakeOKXClient:
    def __init__(self) -> None:
        self.get_calls: list[tuple[str, dict[str, Any] | None]] = []
        self.post_calls: list[tuple[str, Any]] = []

    def get(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        self.get_calls.append((path, params))
        chain = str((params or {}).get("chainIndex") or "")
        if "holder" in path and chain == "56":
            return [
                {"holderWalletAddress": "0xA000000000000000000000000000000000000001"},
                {"holderWalletAddress": "0xA000000000000000000000000000000000000002"},
                {"holderWalletAddress": "0xA000000000000000000000000000000000000001"},
            ]
        if "top-trader" in path and chain == "56":
            return [{"holderWalletAddress": "0xA000000000000000000000000000000000000003"}]
        return []

    def post_json(self, path: str, json_body: Any) -> list[dict[str, Any]]:
        self.post_calls.append((path, json_body))
        if "basic-info" in path:
            return [{"tokenSymbol": "pnut"}]
        return []


def test_fetch_token_result_falls_back_to_next_evm_chain_and_ticker() -> None:
    client = FakeOKXClient()
    result = fetch_token_result(client, "0xF3525965A4AD3CA0AC13F4D2F237113691194444", limit=2)

    assert result.chain.key == "bsc"
    assert result.token_address == "0xf3525965a4ad3ca0ac13f4d2f237113691194444"
    assert result.ticker == "PNUT"
    assert [row["rank"] for row in result.top_holders] == [1, 2]
    assert result.top_holders[0]["holderWalletAddress"] == "0xa000000000000000000000000000000000000001"
    assert result.top_traders[0]["rank"] == 1


def test_fetch_gmgn_label_results_clamps_limit_and_collects_errors() -> None:
    client = FakeOKXClient()
    results, errors = fetch_gmgn_label_results(
        client,
        tokens=[
            "0xF3525965A4AD3CA0AC13F4D2F237113691194444",
            "0xF3525965A4AD3CA0AC13F4D2F237113691194444",
            "NoDataSolanaToken",
        ],
        limit=999,
    )

    assert len(results) == 1
    assert len(errors) == 1
    assert len(results[0].top_holders) <= MAX_GMGN_LIMIT
    assert errors[0].input_token == "NoDataSolanaToken"
