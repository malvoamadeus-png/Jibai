from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .models import ChainSpec
from .okx_client import OKXAPIError, OKXWeb3Client


TOKEN_TOP_TRADER_PATH = "/api/v6/dex/market/token/top-trader"
TOKEN_HOLDER_PATH = "/api/v6/dex/market/token/holder"
MARKET_PRICE_PATH = "/api/v6/dex/market/price"
TOKEN_BASIC_INFO_PATH = "/api/v6/dex/market/token/basic-info"
TOKEN_SEARCH_PATH = "/api/v6/dex/market/token/search"

DEFAULT_GMGN_LIMIT = 20
MAX_GMGN_LIMIT = 50
MAX_TOKEN_COUNT = 50

EVM_CHAIN_CANDIDATES: tuple[ChainSpec, ...] = (
    ChainSpec("ethereum", "Ethereum", "1", True),
    ChainSpec("bsc", "BSC", "56", True),
    ChainSpec("base", "Base", "8453", True),
    ChainSpec("arbitrum", "Arbitrum", "42161", True),
    ChainSpec("polygon", "Polygon", "137", True),
    ChainSpec("optimism", "Optimism", "10", True),
    ChainSpec("avalanche", "Avalanche", "43114", True),
)
SOLANA_CHAIN = ChainSpec("solana", "Solana", "501", False)


@dataclass(frozen=True, slots=True)
class GMGNTokenResult:
    input_token: str
    token_address: str
    chain: ChainSpec
    ticker: str
    top_holders: list[dict[str, Any]]
    top_traders: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class GMGNTokenError:
    input_token: str
    message: str


@dataclass(frozen=True, slots=True)
class OKXTokenSearchCandidate:
    contract_address: str
    chain_index: str
    display_name: str
    symbol: str
    chain_name: str
    community_recognized: bool
    holder_count: float | None
    liquidity: float | None
    market_cap: float | None
    raw: dict[str, Any]


def clamp_gmgn_limit(value: Any) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = DEFAULT_GMGN_LIMIT
    return max(1, min(MAX_GMGN_LIMIT, parsed))


def normalize_tokens(tokens: Iterable[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in tokens:
        token = str(value or "").strip()
        key = token.lower()
        if not token or key in seen:
            continue
        seen.add(key)
        output.append(token)
        if len(output) >= MAX_TOKEN_COUNT:
            break
    return output


def looks_like_evm_address(value: str) -> bool:
    text = value.strip()
    return text.startswith(("0x", "0X")) and len(text) == 42


def normalize_address(value: Any, *, is_evm: bool) -> str:
    text = str(value or "").strip()
    return text.lower() if is_evm else text


def chain_candidates_for_token(token_address: str) -> tuple[ChainSpec, ...]:
    return EVM_CHAIN_CANDIDATES if looks_like_evm_address(token_address) else (SOLANA_CHAIN,)


def sanitize_ticker(value: Any) -> str:
    text = str(value or "").strip()
    return "".join(text.split()).upper() if text else ""


def short_error(exc: Exception, limit: int = 180) -> str:
    text = str(exc).strip()
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _to_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def _list_response(data: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        raise OKXAPIError(f"Unexpected {label} response: {type(data).__name__}", code="api_error")
    return [row for row in data if isinstance(row, dict)]


def _iter_candidate_dicts(data: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if not isinstance(value, dict):
            return
        contract_address = (
            value.get("tokenContractAddress")
            or value.get("contractAddress")
            or value.get("tokenAddress")
            or value.get("address")
            or value.get("ca")
        )
        if contract_address:
            found.append(value)
            return
        for child_key in ("data", "results", "items", "tokens", "hits", "rows", "list"):
            child = value.get(child_key)
            if child is not None:
                visit(child)

    visit(data)
    return found


def parse_token_search_candidates(data: Any, *, limit: int = 5) -> list[OKXTokenSearchCandidate]:
    candidates: list[OKXTokenSearchCandidate] = []
    seen: set[tuple[str, str]] = set()
    for row in _iter_candidate_dicts(data):
        contract_address = str(
            row.get("tokenContractAddress")
            or row.get("contractAddress")
            or row.get("tokenAddress")
            or row.get("address")
            or row.get("ca")
            or ""
        ).strip()
        chain_index = str(
            row.get("chainIndex")
            or row.get("chain_id")
            or row.get("chainId")
            or row.get("networkId")
            or ""
        ).strip()
        if not contract_address:
            continue
        key = (chain_index, normalize_address(contract_address, is_evm=looks_like_evm_address(contract_address)))
        if key in seen:
            continue
        seen.add(key)
        symbol = sanitize_ticker(
            row.get("symbol")
            or row.get("tokenSymbol")
            or row.get("baseTokenSymbol")
            or row.get("ticker")
        )
        display_name = str(
            row.get("tokenName")
            or row.get("displayName")
            or row.get("name")
            or row.get("baseTokenName")
            or symbol
            or contract_address
        ).strip()
        chain_name = str(
            row.get("chainName")
            or row.get("chain")
            or row.get("network")
            or row.get("chainShortName")
            or ""
        ).strip()
        community_value = row.get("communityRecognized")
        community_recognized = (
            community_value is True
            or str(community_value or "").strip().lower() in {"1", "true", "yes"}
        )
        candidates.append(
            OKXTokenSearchCandidate(
                contract_address=key[1],
                chain_index=chain_index,
                display_name=display_name,
                symbol=symbol,
                chain_name=chain_name,
                community_recognized=community_recognized,
                holder_count=_to_float(row.get("holders") or row.get("holderCount")),
                liquidity=_to_float(row.get("liquidity") or row.get("liquidityUsd")),
                market_cap=_to_float(row.get("marketCap") or row.get("marketCapUsd")),
                raw=dict(row),
            )
        )
        if len(candidates) >= max(1, int(limit)):
            break
    return candidates


def search_token_candidates(
    client: OKXWeb3Client,
    query: str,
    *,
    limit: int = 5,
) -> list[OKXTokenSearchCandidate]:
    safe_query = str(query or "").strip()
    if not safe_query:
        return []
    request_variants = (
        {"keyword": safe_query, "limit": max(1, min(int(limit), 20))},
        {"query": safe_query, "limit": max(1, min(int(limit), 20))},
        {"searchText": safe_query, "limit": max(1, min(int(limit), 20))},
    )
    last_error: Exception | None = None
    for params in request_variants:
        try:
            data = client.get(TOKEN_SEARCH_PATH, params)
            parsed = parse_token_search_candidates(data, limit=limit)
            if parsed:
                return parsed
        except Exception as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    return []


def rank_unique_wallet_rows(
    rows: Iterable[dict[str, Any]],
    *,
    is_evm: bool,
    limit: int,
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        wallet = normalize_address(row.get("holderWalletAddress"), is_evm=is_evm)
        if not wallet or wallet in seen:
            continue
        seen.add(wallet)
        item = dict(row)
        item["holderWalletAddress"] = wallet
        item["rank"] = len(ranked) + 1
        ranked.append(item)
        if len(ranked) >= limit:
            break
    return ranked


def fetch_top_traders(client: OKXWeb3Client, chain_index: str, token_address: str) -> list[dict[str, Any]]:
    return _list_response(
        client.get(
            TOKEN_TOP_TRADER_PATH,
            {"chainIndex": chain_index, "tokenContractAddress": token_address},
        ),
        "top-trader",
    )


def fetch_top_holders(client: OKXWeb3Client, chain_index: str, token_address: str) -> list[dict[str, Any]]:
    return _list_response(
        client.get(
            TOKEN_HOLDER_PATH,
            {"chainIndex": chain_index, "tokenContractAddress": token_address},
        ),
        "holder",
    )


def fetch_market_price(client: OKXWeb3Client, chain_index: str, token_address: str) -> dict[str, Any] | None:
    rows = _list_response(
        client.post_json(MARKET_PRICE_PATH, [{"chainIndex": chain_index, "tokenContractAddress": token_address}]),
        "market-price",
    )
    return rows[0] if rows else None


def fetch_token_basic_info(client: OKXWeb3Client, chain_index: str, token_address: str) -> dict[str, Any] | None:
    rows = _list_response(
        client.post_json(TOKEN_BASIC_INFO_PATH, [{"chainIndex": chain_index, "tokenContractAddress": token_address}]),
        "token/basic-info",
    )
    return rows[0] if rows else None


def extract_ticker(rows: Iterable[dict[str, Any]], price_row: dict[str, Any] | None = None) -> str:
    keys = ("symbol", "tokenSymbol", "baseTokenSymbol", "ticker", "tokenTicker", "tokenName")
    all_rows = list(rows)
    if price_row:
        all_rows.append(price_row)
    for row in all_rows:
        if not isinstance(row, dict):
            continue
        for key in keys:
            ticker = sanitize_ticker(row.get(key))
            if ticker:
                return ticker
    return ""


def fetch_ticker(
    client: OKXWeb3Client,
    chain_index: str,
    token_address: str,
    rows: Iterable[dict[str, Any]],
) -> str:
    row_list = list(rows)
    try:
        basic_info = fetch_token_basic_info(client, chain_index, token_address)
        ticker = extract_ticker([basic_info] if basic_info else [])
        if ticker:
            return ticker
    except Exception:
        pass

    try:
        price_row = fetch_market_price(client, chain_index, token_address)
    except Exception:
        price_row = None
    return extract_ticker(row_list, price_row)


def fetch_token_result(client: OKXWeb3Client, token_address: str, limit: int) -> GMGNTokenResult:
    input_token = token_address.strip()
    errors: list[str] = []

    for chain in chain_candidates_for_token(input_token):
        query_token = normalize_address(input_token, is_evm=chain.is_evm)
        try:
            top_traders = rank_unique_wallet_rows(
                fetch_top_traders(client, chain.chain_index, query_token),
                is_evm=chain.is_evm,
                limit=limit,
            )
            top_holders = rank_unique_wallet_rows(
                fetch_top_holders(client, chain.chain_index, query_token),
                is_evm=chain.is_evm,
                limit=limit,
            )
            if not top_traders and not top_holders:
                continue
            ticker = fetch_ticker(client, chain.chain_index, query_token, [*top_traders, *top_holders])
            return GMGNTokenResult(
                input_token=input_token,
                token_address=query_token,
                chain=chain,
                ticker=ticker,
                top_holders=top_holders,
                top_traders=top_traders,
            )
        except Exception as exc:
            errors.append(f"{chain.label}: {short_error(exc)}")

    if errors:
        raise OKXAPIError(" | ".join(errors), code="api_error")
    raise OKXAPIError("OKX did not return usable ranking data.", code="api_error")


def fetch_gmgn_label_results(
    client: OKXWeb3Client,
    *,
    tokens: Iterable[Any],
    limit: Any = DEFAULT_GMGN_LIMIT,
) -> tuple[list[GMGNTokenResult], list[GMGNTokenError]]:
    safe_limit = clamp_gmgn_limit(limit)
    results: list[GMGNTokenResult] = []
    errors: list[GMGNTokenError] = []

    for token in normalize_tokens(tokens):
        try:
            results.append(fetch_token_result(client, token, safe_limit))
        except Exception as exc:
            errors.append(GMGNTokenError(input_token=token, message=short_error(exc)))

    return results, errors


def token_result_to_payload(result: GMGNTokenResult) -> dict[str, Any]:
    return {
        "inputToken": result.input_token,
        "tokenAddress": result.token_address,
        "chain": {
            "key": result.chain.key,
            "label": result.chain.label,
            "chainIndex": result.chain.chain_index,
            "isEvm": result.chain.is_evm,
        },
        "ticker": result.ticker,
        "topHolders": result.top_holders,
        "topTraders": result.top_traders,
    }


def token_error_to_payload(error: GMGNTokenError) -> dict[str, str]:
    return {"inputToken": error.input_token, "message": error.message}
