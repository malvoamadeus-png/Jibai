"use client";

import type * as React from "react";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import {
  ChainBadge,
  ChainFilter,
  chainSummary,
  formatTime,
  formatTokenAmount,
  formatUsd,
  runStatusLabel,
} from "@/components/onchain-shared";
import { LoadingPanel } from "@/components/page-states";
import { SignInCta } from "@/components/signin-cta";
import { useAuth } from "@/lib/auth-context";
import {
  getOnchainWalletMatrix,
  listMyOnchainWalletRequests,
  listOnchainWallets,
  setOnchainWalletNote,
  setOnchainWalletSubscription,
  submitOnchainWallet,
} from "@/lib/direct-data";
import type { OnchainRequestItem, OnchainWalletListItem, OnchainWalletMatrixData } from "@/lib/types";

type DisplayMode = "balance" | "value";

function OnchainWalletsPageContent() {
  const searchParams = useSearchParams();
  const walletParam = searchParams.get("wallet") || "";
  const { loading, profile, signIn, supabase } = useAuth();
  const [query, setQuery] = useState("");
  const [wallets, setWallets] = useState<OnchainWalletListItem[]>([]);
  const [requests, setRequests] = useState<OnchainRequestItem[]>([]);
  const [activeWalletId, setActiveWalletId] = useState(walletParam);
  const [matrix, setMatrix] = useState<OnchainWalletMatrixData | null>(null);
  const [mode, setMode] = useState<DisplayMode>("balance");
  const [chainFilter, setChainFilter] = useState<string[]>([]);
  const [newAddress, setNewAddress] = useState("");
  const [noteDraft, setNoteDraft] = useState("");
  const [error, setError] = useState<string | null>(null);

  const reloadWallets = useCallback(async () => {
    if (loading) return;
    const [nextWallets, nextRequests] = await Promise.all([
      listOnchainWallets(supabase, query),
      listMyOnchainWalletRequests(supabase, profile),
    ]);
    setWallets(nextWallets);
    setRequests(nextRequests);
    if (walletParam && nextWallets.some((wallet) => wallet.id === walletParam)) {
      setActiveWalletId(walletParam);
    } else if (!activeWalletId && nextWallets.length) {
      setActiveWalletId(nextWallets[0].id);
    }
  }, [activeWalletId, loading, profile, query, supabase, walletParam]);

  useEffect(() => {
    Promise.resolve()
      .then(reloadWallets)
      .catch((err) => setError(err instanceof Error ? err.message : "地址库加载失败"));
  }, [reloadWallets]);

  useEffect(() => {
    if (!activeWalletId || loading) return;
    getOnchainWalletMatrix(supabase, activeWalletId, null, chainFilter)
      .then((next) => {
        setMatrix(next);
        setNoteDraft(next.meta?.userNote || "");
        setError(null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "地址矩阵加载失败"));
  }, [activeWalletId, chainFilter, loading, supabase]);

  const cellMap = useMemo(() => {
    const map = new Map<string, OnchainWalletMatrixData["cells"][number]>();
    for (const cell of matrix?.cells || []) {
      map.set(`${cell.tokenId}:${cell.date}`, cell);
    }
    return map;
  }, [matrix]);

  if (loading) return <LoadingPanel />;

  async function handleSubmitWallet(event: React.FormEvent) {
    event.preventDefault();
    if (!newAddress.trim()) return;
    await submitOnchainWallet(supabase, newAddress.trim(), []);
    setNewAddress("");
    await reloadWallets();
  }

  async function saveNote() {
    if (!activeWalletId) return;
    await setOnchainWalletNote(supabase, activeWalletId, noteDraft);
    await reloadWallets();
    const next = await getOnchainWalletMatrix(supabase, activeWalletId, null, chainFilter);
    setMatrix(next);
  }

  return (
    <main className="page">
      <div className="section-head">
        <div>
          <h1>链上地址库</h1>
          <p className="muted">订阅已审批地址，维护自己的私有备注，并按地址查看持仓矩阵。</p>
        </div>
      </div>

      {error ? <div className="empty field-error">数据接口未就绪：{error}</div> : null}

      <section className="panel">
        <div className="filter-row">
          <input aria-label="搜索地址" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索备注或地址" />
          <button className="secondary-button" type="button" onClick={reloadWallets}>
            更新
          </button>
        </div>
        {profile ? (
          <form className="submit-row" style={{ marginTop: 14 }} onSubmit={handleSubmitWallet}>
            <input value={newAddress} onChange={(event) => setNewAddress(event.target.value)} placeholder="提交链上地址" />
            <button className="primary-button" type="submit">
              提交地址
            </button>
          </form>
        ) : (
          <div style={{ marginTop: 14 }}>
            <SignInCta onLogin={signIn} compact />
          </div>
        )}
      </section>

      <div className="dashboard-grid" style={{ marginTop: 18 }}>
        <section className="table-panel">
          <table>
            <thead>
              <tr>
                <th>地址</th>
                <th>链</th>
                <th>快照</th>
                <th>订阅</th>
              </tr>
            </thead>
            <tbody>
              {wallets.map((wallet) => (
                <tr key={wallet.id}>
                  <td>
                    <button className="link-button account-cell" type="button" onClick={() => setActiveWalletId(wallet.id)}>
                      <strong>{wallet.displayName}</strong>
                      <span className="muted">{wallet.addressShort}</span>
                    </button>
                  </td>
                  <td>{chainSummary(wallet.enabledChains)}</td>
                  <td className="muted">{formatTime(wallet.lastSnapshotAt)}</td>
                  <td>
                    {profile ? (
                      <button
                        className="secondary-button"
                        type="button"
                        onClick={async () => {
                          await setOnchainWalletSubscription(supabase, wallet.id, !wallet.subscribed);
                          await reloadWallets();
                        }}
                      >
                        {wallet.subscribed ? "取消订阅" : "订阅"}
                      </button>
                    ) : (
                      <button className="secondary-button" type="button" onClick={signIn}>
                        登录订阅
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {!wallets.length ? (
                <tr>
                  <td colSpan={4}>
                    <div className="empty">暂无已审批地址</div>
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </section>

        <section className="panel">
          <h2>{matrix?.meta?.displayName || "地址详情"}</h2>
          <p className="muted">{matrix?.meta?.addressShort || "选择一个地址查看持仓矩阵。"}</p>
          {profile && matrix?.meta ? (
            <div className="submit-row" style={{ marginTop: 12 }}>
              <input value={noteDraft} onChange={(event) => setNoteDraft(event.target.value)} placeholder="我的私有备注" />
              <button className="secondary-button" type="button" onClick={saveNote}>
                保存备注
              </button>
            </div>
          ) : null}
          <div className="filter-row" style={{ marginTop: 16 }}>
            <button className={mode === "balance" ? "primary-button" : "secondary-button"} type="button" onClick={() => setMode("balance")}>
              数量
            </button>
            <button className={mode === "value" ? "primary-button" : "secondary-button"} type="button" onClick={() => setMode("value")}>
              金额
            </button>
            <ChainFilter value={chainFilter} onChange={setChainFilter} />
          </div>
        </section>
      </div>

      <section className="table-panel onchain-matrix" style={{ marginTop: 18 }}>
        <table>
          <thead>
            <tr>
              <th>Token</th>
              {(matrix?.dates || []).map((date) => (
                <th key={date}>{date.slice(5)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(matrix?.tokens || []).map((token) => (
              <tr key={token.tokenId}>
                <td>
                  <div className="account-cell">
                    <strong>{token.displayName || token.symbol || token.tokenKey}</strong>
                    <span className="muted">
                      <ChainBadge chain={token.chainKey} /> {token.symbol}
                    </span>
                  </div>
                </td>
                {(matrix?.dates || []).map((date) => {
                  const cell = cellMap.get(`${token.tokenId}:${date}`);
                  const delta = mode === "balance" ? cell?.balanceDelta : cell?.valueUsdDelta;
                  return (
                    <td key={date} className={delta && delta > 0 ? "delta-up" : delta && delta < 0 ? "delta-down" : ""}>
                      {cell ? (mode === "balance" ? formatTokenAmount(cell.balance) : formatUsd(cell.valueUsd)) : "-"}
                      {cell?.state === "new" ? <span className="status-pill" style={{ marginLeft: 8 }}>{runStatusLabel("new")}</span> : null}
                    </td>
                  );
                })}
              </tr>
            ))}
            {!matrix?.tokens?.length ? (
              <tr>
                <td colSpan={(matrix?.dates.length || 0) + 1}>
                  <div className="empty">暂无地址持仓快照</div>
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </section>

      {profile ? (
        <section className="panel" style={{ marginTop: 18 }}>
          <h2>我的提交</h2>
          {requests.length ? (
            <table>
              <tbody>
                {requests.map((request) => (
                  <tr key={request.id}>
                    <td>{request.normalizedAddress}</td>
                    <td>
                      <span className="status-pill">{runStatusLabel(request.status)}</span>
                    </td>
                    <td className="muted">{formatTime(request.createdAt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="empty">暂无提交</div>
          )}
        </section>
      ) : null}
    </main>
  );
}

export default function OnchainWalletsPage() {
  return (
    <Suspense fallback={<LoadingPanel />}>
      <OnchainWalletsPageContent />
    </Suspense>
  );
}
