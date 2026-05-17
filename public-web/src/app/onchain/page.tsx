"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ChainBadge, formatTime, formatUsd, runStatusLabel } from "@/components/onchain-shared";
import { LoadingPanel } from "@/components/page-states";
import { useAuth } from "@/lib/auth-context";
import { getOnchainOverview } from "@/lib/direct-data";
import type { OnchainOverviewData } from "@/lib/types";

function asText(value: unknown, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function asNumber(value: unknown) {
  const num = Number(value);
  return Number.isFinite(num) ? num : 0;
}

function TokenCell({ token }: { token: Record<string, unknown> }) {
  return (
    <div className="account-cell">
      <strong>{asText(token.display_name) || asText(token.symbol) || asText(token.token_key)}</strong>
      <span className="muted">
        <ChainBadge chain={asText(token.chain_key)} /> {asText(token.symbol)}
      </span>
    </div>
  );
}

export default function OnchainHomePage() {
  const { loading, supabase } = useAuth();
  const [data, setData] = useState<OnchainOverviewData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (loading) return;
    getOnchainOverview(supabase)
      .then((next) => {
        setData(next);
        setError(null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "链上总览加载失败"));
  }, [loading, supabase]);

  if (loading) return <LoadingPanel />;

  return (
    <main className="page">
      <div className="section-head">
        <div>
          <h1>链上埋伏</h1>
          <p className="muted">追踪已审批地址在多条链上的非稳定、非主流资产持仓，按代币和地址观察增持变化。</p>
        </div>
        <Link className="secondary-button" href="/onchain/tokens">
          按代币查看
        </Link>
      </div>

      {error ? <div className="empty field-error">数据接口未就绪：{error}</div> : null}

      <section className="metric-row">
        <div className="metric">
          <span className="muted">最新日期</span>
          <strong>{data?.latestDate || "-"}</strong>
        </div>
        <div className="metric">
          <span className="muted">可见地址</span>
          <strong>{data?.walletCount ?? 0}</strong>
        </div>
        <div className="metric">
          <span className="muted">可见代币</span>
          <strong>{data?.tokenCount ?? 0}</strong>
        </div>
      </section>

      <div className="dashboard-grid" style={{ marginTop: 22 }}>
        <section className="table-panel">
          <table>
            <thead>
              <tr>
                <th>今日新买入</th>
                <th>地址数</th>
                <th>金额</th>
              </tr>
            </thead>
            <tbody>
              {(data?.newTokens || []).map((token) => (
                <tr key={`new-${asText(token.token_key)}`}>
                  <td>
                    <TokenCell token={token} />
                  </td>
                  <td>{asNumber(token.new_wallet_count)}</td>
                  <td>{formatUsd(asNumber(token.value_usd_sum))}</td>
                </tr>
              ))}
              {!data?.newTokens?.length ? (
                <tr>
                  <td colSpan={3}>
                    <div className="empty">暂无今日新增持仓</div>
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </section>

        <section className="table-panel">
          <table>
            <thead>
              <tr>
                <th>增持榜</th>
                <th>地址数</th>
                <th>数量变化</th>
              </tr>
            </thead>
            <tbody>
              {(data?.increasedTokens || []).map((token) => (
                <tr key={`inc-${asText(token.token_key)}`}>
                  <td>
                    <TokenCell token={token} />
                  </td>
                  <td>{asNumber(token.increased_wallet_count)}</td>
                  <td className="delta-up">{asNumber(token.balance_delta_sum).toLocaleString()}</td>
                </tr>
              ))}
              {!data?.increasedTokens?.length ? (
                <tr>
                  <td colSpan={3}>
                    <div className="empty">暂无今日增持记录</div>
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </section>
      </div>

      <div className="dashboard-grid" style={{ marginTop: 22 }}>
        <section className="table-panel">
          <table>
            <thead>
              <tr>
                <th>共识持仓</th>
                <th>持有人</th>
                <th>金额</th>
              </tr>
            </thead>
            <tbody>
              {(data?.topTokens || []).map((token) => (
                <tr key={asText(token.token_key)}>
                  <td>
                    <TokenCell token={token} />
                  </td>
                  <td>{asNumber(token.holder_count)}</td>
                  <td>{formatUsd(asNumber(token.value_usd_sum))}</td>
                </tr>
              ))}
              {!data?.topTokens?.length ? (
                <tr>
                  <td colSpan={3}>
                    <div className="empty">暂无链上持仓数据</div>
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </section>

        <section className="table-panel">
          <table>
            <thead>
              <tr>
                <th>地址活跃度</th>
                <th>代币</th>
                <th>金额</th>
              </tr>
            </thead>
            <tbody>
              {(data?.activeWallets || []).map((wallet) => (
                <tr key={asText(wallet.id)}>
                  <td>
                    <Link href={`/onchain/wallets?wallet=${asText(wallet.id)}`} className="account-cell">
                      <strong>{asText(wallet.display_name)}</strong>
                      <span className="muted">{asText(wallet.address_short)}</span>
                    </Link>
                  </td>
                  <td>{asNumber(wallet.token_count)}</td>
                  <td>{formatUsd(asNumber(wallet.value_usd_sum))}</td>
                </tr>
              ))}
              {!data?.activeWallets?.length ? (
                <tr>
                  <td colSpan={3}>
                    <div className="empty">暂无地址快照</div>
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </section>
      </div>

      <section className="table-panel" style={{ marginTop: 22 }}>
        <table>
          <thead>
            <tr>
              <th>最近抓取</th>
              <th>状态</th>
              <th>完成时间</th>
              <th>结果</th>
            </tr>
          </thead>
          <tbody>
            {(data?.recentRuns || []).map((run) => (
              <tr key={run.id}>
                <td>{run.kind}</td>
                <td>
                  <span className="status-pill">{runStatusLabel(run.status)}</span>
                </td>
                <td className="muted">{formatTime(run.finishedAt || run.createdAt)}</td>
                <td className={run.errorText ? "field-error" : "muted"}>{run.errorText || run.summary || "-"}</td>
              </tr>
            ))}
            {!data?.recentRuns?.length ? (
              <tr>
                <td colSpan={4}>
                  <div className="empty">暂无抓取记录</div>
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </section>
    </main>
  );
}
