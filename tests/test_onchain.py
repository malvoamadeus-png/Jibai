from __future__ import annotations

from decimal import Decimal

from packages.onchain.models import OnchainWallet
from packages.onchain.okx_client import OKXWeb3Client, PORTFOLIO_ALL_BALANCES_PATH
from packages.onchain.models import FetchItemResult
from packages.onchain.service import _build_summary, flatten_balance_rows
from packages.onchain.utils import short_address, token_key


def test_short_address_keeps_prefix_and_suffix() -> None:
    assert short_address("0xa7bfa56d1fbb7809b8424b452896707be408e1bc") == "0xa7bf...e1bc"


def test_token_key_prefers_chain_and_contract() -> None:
    assert (
        token_key(chain_index="56", token_contract_address="0xABCDEF", symbol="ABC")
        == "56:0xabcdef"
    )
    assert token_key(chain_index="501", token_contract_address="", symbol="SOL", is_evm=False) == "501:native:SOL"


def test_flatten_balance_rows_filters_threshold_and_symbols() -> None:
    wallet = OnchainWallet(
        id="wallet-1",
        address="0xa7bfa56d1fbb7809b8424b452896707be408e1bc",
        admin_label="恰米",
        chain_key="bsc",
        chain_index="56",
    )
    rows = [
        {
            "chainIndex": "56",
            "tokenAssets": [
                {
                    "tokenContractAddress": "0xToken",
                    "symbol": "ALPHA",
                    "balance": "10",
                    "rawBalance": "10000000000000000000",
                    "tokenPrice": "30",
                    "isRiskToken": False,
                },
                {
                    "tokenContractAddress": "0xUSDT",
                    "symbol": "USDT",
                    "balance": "1000",
                    "rawBalance": "1000000000",
                    "tokenPrice": "1",
                    "isRiskToken": False,
                },
                {
                    "tokenContractAddress": "0xTiny",
                    "symbol": "TINY",
                    "balance": "1",
                    "rawBalance": "1000000000000000000",
                    "tokenPrice": "10",
                    "isRiskToken": False,
                },
            ],
        }
    ]

    flattened = flatten_balance_rows(
        wallet=wallet,
        response_rows=rows,
        rules={"symbol": {"USDT"}},
        min_value_usd=Decimal("200"),
    )

    by_symbol = {item.symbol: item for item in flattened}
    assert by_symbol["ALPHA"].excluded is False
    assert by_symbol["ALPHA"].holding_value_usd == Decimal("300")
    assert by_symbol["USDT"].excluded is True
    assert by_symbol["USDT"].exclusion_reason == "symbol_filter"
    assert by_symbol["TINY"].excluded is True
    assert by_symbol["TINY"].exclusion_reason == "below_threshold"


def test_okx_balance_request_filters_risk_tokens(monkeypatch) -> None:
    captured: dict[str, object] = {}
    client = OKXWeb3Client(api_key="key", secret_key="secret", passphrase="pass", request_delay_seconds=0)

    def fake_get(path: str, params: dict[str, object]) -> list[dict[str, object]]:
        captured["path"] = path
        captured["params"] = params
        return []

    monkeypatch.setattr(client, "get", fake_get)
    assert client.fetch_all_token_balances(wallet_address="0xabc", chains="56") == []
    assert captured["path"] == PORTFOLIO_ALL_BALANCES_PATH
    assert captured["params"] == {
        "address": "0xabc",
        "chains": "56",
        "excludeRiskToken": "0",
    }


def test_fetch_summary_marks_mixed_results_as_partial() -> None:
    status, summary = _build_summary(
        [
            FetchItemResult(
                wallet_id="wallet-1",
                chain_key="bsc",
                chain_index="56",
                status="success",
                token_count=10,
                visible_token_count=3,
            ),
            FetchItemResult(
                wallet_id="wallet-2",
                chain_key="ethereum",
                chain_index="1",
                status="api_error",
                token_count=0,
                visible_token_count=0,
                error_text="boom",
            ),
        ],
        visible_balances=3,
    )

    assert status == "partial"
    assert "失败 1" in summary
