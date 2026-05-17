from __future__ import annotations

import os
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from packages.common.postgres_database import postgres_connection
from packages.common.time_utils import SHANGHAI_TZ, now_shanghai, today_date_key

from .models import CHAIN_BY_INDEX, FetchItemResult, FetchRunResult, OnchainWallet, TokenBalance
from .okx_client import OKXAPIError, OKXWeb3Client
from .utils import chain_key_for_index, normalize_address, parse_bool, parse_decimal, short_address, token_key


DEFAULT_MIN_VALUE_USD = Decimal("200")


def _env_decimal(name: str, default: Decimal) -> Decimal:
    try:
        return Decimal(os.getenv(name, str(default)))
    except Exception:
        return default


def _min_value_usd() -> Decimal:
    return max(Decimal("0"), _env_decimal("PUBLIC_ONCHAIN_MIN_VALUE_USD", DEFAULT_MIN_VALUE_USD))


def _exclude_risk_token() -> bool:
    return os.getenv("PUBLIC_ONCHAIN_EXCLUDE_RISK_TOKEN", "true").strip().lower() not in {"0", "false", "no"}


def list_enabled_wallet_chains(conn: Connection[dict[str, Any]]) -> list[OnchainWallet]:
    rows = conn.execute(
        """
        SELECT
          w.id::text AS wallet_id,
          w.address,
          w.admin_label,
          c.chain_key,
          c.chain_index
        FROM onchain_wallets w
        JOIN onchain_wallet_chains c ON c.wallet_id = w.id
        WHERE w.status = 'approved'
          AND c.enabled
        ORDER BY coalesce(w.approved_at, w.created_at), w.address, c.chain_key
        """
    ).fetchall()
    return [
        OnchainWallet(
            id=str(row["wallet_id"]),
            address=str(row["address"]),
            admin_label=str(row["admin_label"] or ""),
            chain_key=str(row["chain_key"]),
            chain_index=str(row["chain_index"]),
        )
        for row in rows
    ]


def load_filter_rules(conn: Connection[dict[str, Any]]) -> dict[str, set[str]]:
    rows = conn.execute(
        """
        SELECT rule_type, coalesce(chain_index, '') AS chain_index,
               lower(coalesce(token_contract_address, '')) AS token_contract_address,
               upper(coalesce(symbol, '')) AS symbol
        FROM onchain_token_filter_rules
        WHERE enabled
        """
    ).fetchall()
    rules: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        rule_type = str(row["rule_type"])
        symbol = str(row["symbol"] or "").strip().upper()
        contract = str(row["token_contract_address"] or "").strip().lower()
        chain_index = str(row["chain_index"] or "").strip()
        if symbol:
            rules["symbol"].add(symbol)
        if contract:
            rules["contract"].add(f"{chain_index}:{contract}" if chain_index else contract)
        if rule_type:
            rules[f"type:{rule_type}"].add(symbol or contract)
    return rules


def _is_filtered(
    *,
    rules: dict[str, set[str]],
    chain_index: str,
    token_contract_address: str,
    symbol: str,
    is_risk_token: bool,
    holding_value_usd: Decimal,
    min_value_usd: Decimal,
) -> tuple[bool, str]:
    upper_symbol = symbol.strip().upper()
    lower_contract = token_contract_address.strip().lower()
    if holding_value_usd <= min_value_usd:
        return True, "below_threshold"
    if _exclude_risk_token() and is_risk_token:
        return True, "risk_token"
    if upper_symbol and upper_symbol in rules.get("symbol", set()):
        return True, "symbol_filter"
    if lower_contract:
        contract_rules = rules.get("contract", set())
        if lower_contract in contract_rules or f"{chain_index}:{lower_contract}" in contract_rules:
            return True, "contract_filter"
    return False, ""


def flatten_balance_rows(
    *,
    wallet: OnchainWallet,
    response_rows: list[dict[str, Any]],
    rules: dict[str, set[str]],
    min_value_usd: Decimal | None = None,
) -> list[TokenBalance]:
    flattened: list[TokenBalance] = []
    safe_min = min_value_usd if min_value_usd is not None else _min_value_usd()
    chain_spec = CHAIN_BY_INDEX.get(wallet.chain_index)
    is_evm = bool(chain_spec.is_evm if chain_spec else wallet.address.lower().startswith("0x"))

    for chain_row in response_rows:
        if not isinstance(chain_row, dict):
            continue
        parent_chain_index = str(chain_row.get("chainIndex") or wallet.chain_index or "").strip()
        token_assets = chain_row.get("tokenAssets") if "tokenAssets" in chain_row else [chain_row]
        if not isinstance(token_assets, list):
            continue
        for asset in token_assets:
            if not isinstance(asset, dict):
                continue
            chain_index = str(asset.get("chainIndex") or parent_chain_index or wallet.chain_index).strip()
            chain_key = chain_key_for_index(chain_index) or wallet.chain_key
            token_contract_address = normalize_address(asset.get("tokenContractAddress"), is_evm=is_evm)
            symbol = str(asset.get("symbol") or "").strip()
            display_name = str(asset.get("tokenName") or asset.get("name") or symbol or token_contract_address or "native").strip()
            balance = parse_decimal(asset.get("balance"))
            raw_balance = parse_decimal(asset.get("rawBalance"))
            token_price_usd = parse_decimal(asset.get("tokenPrice"))
            holding_value_usd = balance * token_price_usd
            is_risk_token = parse_bool(asset.get("isRiskToken"))
            key = token_key(
                chain_index=chain_index,
                token_contract_address=token_contract_address,
                symbol=symbol,
                is_evm=is_evm,
            )
            excluded, reason = _is_filtered(
                rules=rules,
                chain_index=chain_index,
                token_contract_address=token_contract_address,
                symbol=symbol,
                is_risk_token=is_risk_token,
                holding_value_usd=holding_value_usd,
                min_value_usd=safe_min,
            )
            flattened.append(
                TokenBalance(
                    wallet_id=wallet.id,
                    address=wallet.address,
                    chain_key=chain_key,
                    chain_index=chain_index,
                    token_key=key,
                    token_contract_address=token_contract_address,
                    symbol=symbol,
                    display_name=display_name,
                    balance=balance,
                    raw_balance=raw_balance,
                    token_price_usd=token_price_usd,
                    holding_value_usd=holding_value_usd,
                    is_native=not bool(token_contract_address),
                    is_risk_token=is_risk_token,
                    excluded=excluded,
                    exclusion_reason=reason,
                )
            )
    return flattened


def start_fetch_run(conn: Connection[dict[str, Any]], *, kind: str, run_id: str | None = None) -> str:
    if run_id:
        row = conn.execute(
            """
            UPDATE onchain_fetch_runs
            SET kind = %s,
                status = 'running',
                started_at = now(),
                finished_at = NULL,
                summary = '',
                error_text = NULL,
                updated_at = now()
            WHERE id = %s
              AND status = 'pending'
            RETURNING id::text
            """,
            (kind, run_id),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Pending onchain fetch run not found: {run_id}")
        return str(row["id"])

    row = conn.execute(
        """
        INSERT INTO onchain_fetch_runs (kind, status, started_at, metadata_json)
        VALUES (%s, 'running', now(), %s)
        RETURNING id::text
        """,
        (kind, Jsonb({"source": "backend"})),
    ).fetchone()
    if row is None:
        raise RuntimeError("Failed to create onchain fetch run.")
    return str(row["id"])


def _ensure_token(conn: Connection[dict[str, Any]], item: TokenBalance) -> str:
    row = conn.execute(
        """
        INSERT INTO onchain_tokens (
          token_key, chain_key, chain_index, token_contract_address, symbol,
          display_name, is_native, is_risk_token, filter_reason, last_seen_at, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now())
        ON CONFLICT (token_key) DO UPDATE SET
          symbol = COALESCE(NULLIF(EXCLUDED.symbol, ''), onchain_tokens.symbol),
          display_name = COALESCE(NULLIF(EXCLUDED.display_name, ''), onchain_tokens.display_name),
          is_risk_token = EXCLUDED.is_risk_token,
          filter_reason = EXCLUDED.filter_reason,
          last_seen_at = now(),
          updated_at = now()
        RETURNING id::text
        """,
        (
            item.token_key,
            item.chain_key,
            item.chain_index,
            item.token_contract_address,
            item.symbol,
            item.display_name,
            item.is_native,
            item.is_risk_token,
            item.exclusion_reason,
        ),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Failed to upsert token: {item.token_key}")
    return str(row["id"])


def insert_snapshots(
    conn: Connection[dict[str, Any]],
    *,
    run_id: str,
    balances: list[TokenBalance],
    snapshot_at: str,
    date_key: str,
) -> int:
    visible_count = 0
    for item in balances:
        token_id = _ensure_token(conn, item)
        if not item.excluded:
            visible_count += 1
        conn.execute(
            """
            INSERT INTO onchain_balance_snapshots (
              run_id, wallet_id, token_id, chain_key, chain_index, date_key, snapshot_at,
              balance, raw_balance, token_price_usd, holding_value_usd,
              is_risk_token, excluded, exclusion_reason
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                run_id,
                item.wallet_id,
                token_id,
                item.chain_key,
                item.chain_index,
                date_key,
                snapshot_at,
                item.balance,
                item.raw_balance,
                item.token_price_usd,
                item.holding_value_usd,
                item.is_risk_token,
                item.excluded,
                item.exclusion_reason,
            ),
        )
    return visible_count


def insert_run_item(conn: Connection[dict[str, Any]], *, run_id: str, result: FetchItemResult) -> None:
    conn.execute(
        """
        INSERT INTO onchain_fetch_run_items (
          run_id, wallet_id, chain_key, chain_index, status,
          token_count, visible_token_count, error_text
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, NULLIF(%s, ''))
        """,
        (
            run_id,
            result.wallet_id,
            result.chain_key,
            result.chain_index,
            result.status,
            result.token_count,
            result.visible_token_count,
            result.error_text[:1000],
        ),
    )


def finish_fetch_run(conn: Connection[dict[str, Any]], *, run_id: str, status: str, summary: str, error_text: str = "") -> None:
    conn.execute(
        """
        UPDATE onchain_fetch_runs
        SET status = %s,
            summary = %s,
            error_text = NULLIF(%s, ''),
            finished_at = now(),
            updated_at = now()
        WHERE id = %s
        """,
        (status, summary, error_text[:4000], run_id),
    )


def claim_pending_fetch_run(conn: Connection[dict[str, Any]]) -> str | None:
    row = conn.execute(
        """
        SELECT id::text AS id
        FROM public.onchain_fetch_runs
        WHERE status = 'pending'
        ORDER BY created_at ASC
        LIMIT 1
        FOR UPDATE SKIP LOCKED
        """
    ).fetchone()
    return str(row["id"]) if row else None


def rebuild_daily_views(conn: Connection[dict[str, Any]], *, days: int = 30) -> None:
    safe_days = max(1, int(days))
    start_date = (now_shanghai().date() - timedelta(days=safe_days - 1)).isoformat()
    conn.execute(
        """
        DELETE FROM onchain_daily_wallet_token_views
        WHERE date_key >= %s
        """,
        (start_date,),
    )
    conn.execute(
        """
        WITH ranked AS (
          SELECT
            s.*,
            row_number() OVER (
              PARTITION BY s.date_key, s.wallet_id, s.token_id
              ORDER BY s.snapshot_at DESC, s.created_at DESC
            ) AS rn
          FROM onchain_balance_snapshots s
          WHERE s.date_key >= %s
            AND NOT s.excluded
        ),
        current_rows AS (
          SELECT * FROM ranked WHERE rn = 1
        ),
        with_prev AS (
          SELECT
            c.*,
            lag(c.balance) OVER (
              PARTITION BY c.wallet_id, c.token_id ORDER BY c.date_key
            ) AS previous_balance,
            lag(c.holding_value_usd) OVER (
              PARTITION BY c.wallet_id, c.token_id ORDER BY c.date_key
            ) AS previous_value_usd
          FROM current_rows c
        )
        INSERT INTO onchain_daily_wallet_token_views (
          date_key, wallet_id, token_id, chain_key, chain_index, snapshot_at,
          balance, token_price_usd, holding_value_usd,
          previous_balance, previous_value_usd, balance_delta, value_usd_delta, state, updated_at
        )
        SELECT
          date_key,
          wallet_id,
          token_id,
          chain_key,
          chain_index,
          snapshot_at,
          balance,
          token_price_usd,
          holding_value_usd,
          previous_balance,
          previous_value_usd,
          CASE WHEN previous_balance IS NULL THEN NULL ELSE balance - previous_balance END,
          CASE WHEN previous_value_usd IS NULL THEN NULL ELSE holding_value_usd - previous_value_usd END,
          CASE
            WHEN previous_balance IS NULL THEN 'new'
            WHEN balance > previous_balance THEN 'increased'
            WHEN balance < previous_balance THEN 'decreased'
            ELSE 'held'
          END,
          now()
        FROM with_prev
        ON CONFLICT (date_key, wallet_id, token_id) DO UPDATE SET
          snapshot_at = EXCLUDED.snapshot_at,
          balance = EXCLUDED.balance,
          token_price_usd = EXCLUDED.token_price_usd,
          holding_value_usd = EXCLUDED.holding_value_usd,
          previous_balance = EXCLUDED.previous_balance,
          previous_value_usd = EXCLUDED.previous_value_usd,
          balance_delta = EXCLUDED.balance_delta,
          value_usd_delta = EXCLUDED.value_usd_delta,
          state = EXCLUDED.state,
          updated_at = now()
        """,
        (start_date,),
    )
    conn.execute(
        """
        DELETE FROM onchain_daily_token_views
        WHERE date_key >= %s
        """,
        (start_date,),
    )
    conn.execute(
        """
        WITH aggregate_rows AS (
          SELECT
            d.date_key,
            d.token_id,
            d.chain_key,
            d.chain_index,
            count(distinct d.wallet_id)::int AS holder_count,
            sum(d.balance) AS balance_sum,
            sum(d.holding_value_usd) AS value_usd_sum,
            count(*) FILTER (WHERE d.state = 'new')::int AS new_holder_count,
            jsonb_agg(
              jsonb_build_object(
                'walletId', w.id,
                'address', w.address,
                'addressShort', public.onchain_short_address(w.address),
                'displayName', coalesce(nullif(w.admin_label, ''), public.onchain_short_address(w.address)),
                'balance', d.balance,
                'valueUsd', d.holding_value_usd
              )
              order by d.holding_value_usd desc
            ) AS holders_json
          FROM onchain_daily_wallet_token_views d
          JOIN onchain_wallets w ON w.id = d.wallet_id
          WHERE d.date_key >= %s
          GROUP BY d.date_key, d.token_id, d.chain_key, d.chain_index
        ),
        with_prev AS (
          SELECT
            a.*,
            lag(a.holder_count) OVER (PARTITION BY a.token_id ORDER BY a.date_key) AS previous_holder_count,
            lag(a.balance_sum) OVER (PARTITION BY a.token_id ORDER BY a.date_key) AS previous_balance_sum,
            lag(a.value_usd_sum) OVER (PARTITION BY a.token_id ORDER BY a.date_key) AS previous_value_usd_sum
          FROM aggregate_rows a
        )
        INSERT INTO onchain_daily_token_views (
          date_key, token_id, chain_key, chain_index, holder_count, balance_sum, value_usd_sum,
          holder_count_delta, balance_delta, value_usd_delta,
          new_holder_count, exited_holder_count, holders_json, updated_at
        )
        SELECT
          date_key,
          token_id,
          chain_key,
          chain_index,
          holder_count,
          balance_sum,
          value_usd_sum,
          CASE WHEN previous_holder_count IS NULL THEN NULL ELSE holder_count - previous_holder_count END,
          CASE WHEN previous_balance_sum IS NULL THEN NULL ELSE balance_sum - previous_balance_sum END,
          CASE WHEN previous_value_usd_sum IS NULL THEN NULL ELSE value_usd_sum - previous_value_usd_sum END,
          new_holder_count,
          greatest(0, coalesce(previous_holder_count, holder_count) - holder_count),
          holders_json,
          now()
        FROM with_prev
        ON CONFLICT (date_key, token_id) DO UPDATE SET
          holder_count = EXCLUDED.holder_count,
          balance_sum = EXCLUDED.balance_sum,
          value_usd_sum = EXCLUDED.value_usd_sum,
          holder_count_delta = EXCLUDED.holder_count_delta,
          balance_delta = EXCLUDED.balance_delta,
          value_usd_delta = EXCLUDED.value_usd_delta,
          new_holder_count = EXCLUDED.new_holder_count,
          exited_holder_count = EXCLUDED.exited_holder_count,
          holders_json = EXCLUDED.holders_json,
          updated_at = now()
        """,
        (start_date,),
    )
    conn.execute(
        """
        UPDATE onchain_wallets w
        SET last_snapshot_at = latest.snapshot_at,
            updated_at = now()
        FROM (
          SELECT wallet_id, max(snapshot_at) AS snapshot_at
          FROM onchain_balance_snapshots
          WHERE date_key >= %s
          GROUP BY wallet_id
        ) latest
        WHERE latest.wallet_id = w.id
        """,
        (start_date,),
    )


def _status_from_error(exc: Exception) -> str:
    if isinstance(exc, OKXAPIError):
        if exc.code in {"auth_error", "rate_limited", "network_error", "api_error"}:
            return exc.code
    return "api_error"


def _build_summary(results: list[FetchItemResult], visible_balances: int) -> tuple[str, str]:
    failed = [item for item in results if item.status not in {"success", "empty"}]
    empty = [item for item in results if item.status == "empty"]
    ok = [item for item in results if item.status == "success"]
    status = "partial" if failed and (ok or empty) else "failed" if failed else "succeeded"
    parts = [
        f"链上抓取 {len(results)} 个地址链",
        f"成功 {len(ok)}",
        f"空结果 {len(empty)}",
        f"可见持仓 {visible_balances}",
    ]
    if failed:
        parts.append(f"失败 {len(failed)}")
    return status, "；".join(parts) + "。"


def fetch_onchain_once(
    *,
    kind: str = "once",
    rebuild_days: int = 30,
    run_id: str | None = None,
) -> FetchRunResult:
    snapshot_time = now_shanghai()
    snapshot_at = snapshot_time.isoformat(timespec="seconds")
    date_key = snapshot_time.astimezone(SHANGHAI_TZ).date().isoformat()

    with postgres_connection() as conn:
        run_id = start_fetch_run(conn, kind=kind, run_id=run_id)
        try:
            client = OKXWeb3Client.from_env()
        except Exception as exc:
            status = _status_from_error(exc)
            summary = "链上抓取启动失败：" + status
            finish_fetch_run(conn, run_id=run_id, status="failed", summary=summary, error_text=str(exc))
            return FetchRunResult(run_id=run_id, status="failed", summary=summary, item_results=[], visible_balances=0)

        wallets = list_enabled_wallet_chains(conn)
        rules = load_filter_rules(conn)
        if not wallets:
            summary = "链上抓取没有已审批并启用链的钱包。"
            finish_fetch_run(conn, run_id=run_id, status="succeeded", summary=summary)
            return FetchRunResult(run_id=run_id, status="succeeded", summary=summary, item_results=[], visible_balances=0)

        results: list[FetchItemResult] = []
        visible_balances = 0
        for wallet in wallets:
            try:
                response_rows = client.fetch_all_token_balances(
                    wallet_address=wallet.address,
                    chains=wallet.chain_index,
                )
                balances = flatten_balance_rows(
                    wallet=wallet,
                    response_rows=response_rows,
                    rules=rules,
                )
                visible_count = insert_snapshots(
                    conn,
                    run_id=run_id,
                    balances=balances,
                    snapshot_at=snapshot_at,
                    date_key=date_key,
                )
                visible_balances += visible_count
                result = FetchItemResult(
                    wallet_id=wallet.id,
                    chain_key=wallet.chain_key,
                    chain_index=wallet.chain_index,
                    status="success" if visible_count else "empty",
                    token_count=len(balances),
                    visible_token_count=visible_count,
                )
            except Exception as exc:
                result = FetchItemResult(
                    wallet_id=wallet.id,
                    chain_key=wallet.chain_key,
                    chain_index=wallet.chain_index,
                    status=_status_from_error(exc),
                    token_count=0,
                    visible_token_count=0,
                    error_text=str(exc),
                )
            insert_run_item(conn, run_id=run_id, result=result)
            results.append(result)

        rebuild_daily_views(conn, days=rebuild_days)
        status, summary = _build_summary(results, visible_balances)
        first_error = next((item.error_text for item in results if item.error_text), "")
        finish_fetch_run(conn, run_id=run_id, status=status, summary=summary, error_text=first_error if status == "failed" else "")
        return FetchRunResult(
            run_id=run_id,
            status=status,
            summary=summary,
            item_results=results,
            visible_balances=visible_balances,
        )


def process_pending_onchain_fetches(*, max_runs: int | None = 1) -> int:
    processed = 0
    while max_runs is None or processed < max_runs:
        with postgres_connection() as conn:
            run_id = claim_pending_fetch_run(conn)
        if not run_id:
            break
        result = fetch_onchain_once(kind="manual", run_id=run_id)
        print(f"[onchain] pending_run id={result.run_id} status={result.status} summary={result.summary}")
        processed += 1
    return processed


def rebuild_onchain_daily_once(*, days: int = 30) -> int:
    with postgres_connection() as conn:
        rebuild_daily_views(conn, days=days)
    print(f"[onchain] rebuilt_daily days={max(1, int(days))}")
    return 0


def doctor_once() -> int:
    okx_keys = all(
        bool(os.getenv(name, "").strip())
        for name in ("OKX_API_KEY", "OKX_SECRET_KEY", "OKX_PASSPHRASE")
    )
    with postgres_connection() as conn:
        wallet_row = conn.execute(
            """
            SELECT
              count(*) FILTER (WHERE status = 'approved')::int AS approved,
              count(*) FILTER (WHERE status = 'approved' AND last_snapshot_at IS NOT NULL)::int AS with_snapshot
            FROM onchain_wallets
            """
        ).fetchone()
        run_row = conn.execute(
            """
            SELECT status, created_at, finished_at, summary, error_text
            FROM onchain_fetch_runs
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()
    print(
        "[onchain] doctor "
        f"okx_keys={'set' if okx_keys else 'missing'} "
        f"approved_wallets={wallet_row['approved'] if wallet_row else 0} "
        f"wallets_with_snapshot={wallet_row['with_snapshot'] if wallet_row else 0}"
    )
    if run_row:
        print(
            "[onchain] latest_run "
            f"status={run_row['status']} "
            f"created_at={run_row['created_at']} "
            f"finished_at={run_row['finished_at']} "
            f"summary={run_row['summary'] or '-'} "
            f"error={run_row['error_text'] or '-'}"
        )
    return 0 if okx_keys else 1
