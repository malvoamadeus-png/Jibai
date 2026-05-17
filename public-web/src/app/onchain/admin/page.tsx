"use client";

import { useCallback, useEffect, useState } from "react";

import {
  OnchainApproveButton,
  OnchainManualFetchButton,
  OnchainRejectButton,
  OnchainWalletSaveButton,
} from "@/components/onchain-admin-actions";
import { ChainFilter, formatTime, runStatusLabel } from "@/components/onchain-shared";
import { LoadingPanel, LoginRequired } from "@/components/page-states";
import { useAuth } from "@/lib/auth-context";
import { listOnchainAdminDashboard } from "@/lib/direct-data";
import type { OnchainAdminDashboard, OnchainAdminWalletItem } from "@/lib/types";

function WalletAdminRow({ wallet, onChanged }: { wallet: OnchainAdminWalletItem; onChanged: () => void }) {
  const [adminLabel, setAdminLabel] = useState(wallet.adminLabel);
  const [chainKeys, setChainKeys] = useState<string[]>(() => wallet.enabledChains.map((chain) => chain.key));
  const [status, setStatus] = useState(wallet.status || "approved");

  return (
    <tr>
      <td>
        <div className="account-cell">
          <strong>{wallet.adminLabel || wallet.addressShort}</strong>
          <span className="muted address-text">{wallet.addressShort}</span>
        </div>
      </td>
      <td>
        <input value={adminLabel} onChange={(event) => setAdminLabel(event.target.value)} placeholder="全站备注" />
      </td>
      <td>
        <ChainFilter value={chainKeys} onChange={setChainKeys} />
      </td>
      <td>
        <select value={status} onChange={(event) => setStatus(event.target.value)}>
          <option value="approved">已启用</option>
          <option value="disabled">已停用</option>
          <option value="pending">待审批</option>
          <option value="rejected">已拒绝</option>
        </select>
      </td>
      <td className="muted">{formatTime(wallet.lastSnapshotAt)}</td>
      <td>
        <OnchainWalletSaveButton
          adminLabel={adminLabel}
          chainKeys={chainKeys}
          status={status}
          walletId={wallet.id}
          onChanged={onChanged}
        />
      </td>
    </tr>
  );
}

export default function OnchainAdminPage() {
  const { loading, profile, signIn, supabase } = useAuth();
  const [dashboard, setDashboard] = useState<OnchainAdminDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!profile?.isAdmin) return;
    const next = await listOnchainAdminDashboard(supabase);
    setDashboard(next);
    setError(null);
  }, [profile, supabase]);

  useEffect(() => {
    Promise.resolve()
      .then(reload)
      .catch((err) => setError(err instanceof Error ? err.message : "链上管理加载失败"));
  }, [reload]);

  if (loading) return <LoadingPanel />;
  if (!profile) return <LoginRequired onLogin={signIn} />;
  if (!profile.isAdmin) {
    return (
      <main className="page">
        <div className="empty">你没有管理员权限。</div>
      </main>
    );
  }

  const runningRuns = dashboard?.runs.filter((run) => run.status === "running").length ?? 0;

  return (
    <main className="page">
      <div className="section-head">
        <div>
          <h1>链上管理</h1>
          <p className="muted">审批地址、配置抓取链、维护全站备注，并查看 OKX 抓取运行状态。</p>
        </div>
        <OnchainManualFetchButton onChanged={reload} />
      </div>

      {error ? <div className="empty field-error">数据接口未就绪：{error}</div> : null}

      <section className="metric-row">
        <div className="metric">
          <strong>{dashboard?.approvedCount ?? 0}</strong>
          <span className="muted">已启用地址</span>
        </div>
        <div className="metric">
          <strong>{dashboard?.pendingCount ?? 0}</strong>
          <span className="muted">待审批申请</span>
        </div>
        <div className="metric">
          <strong>{runningRuns}</strong>
          <span className="muted">运行中抓取</span>
        </div>
      </section>

      <section className="table-panel" style={{ marginTop: 18 }}>
        <table>
          <thead>
            <tr>
              <th>申请地址</th>
              <th>提交人</th>
              <th>时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {(dashboard?.requests || []).map((request) => (
              <tr key={request.id}>
                <td>
                  <div className="account-cell">
                    <strong className="address-text">{request.normalizedAddress}</strong>
                    <span className="muted">{request.rawInput}</span>
                  </div>
                </td>
                <td>{request.requesterEmail}</td>
                <td className="muted">{formatTime(request.createdAt)}</td>
                <td>
                  <OnchainApproveButton requestId={request.id} onChanged={reload} />
                  <OnchainRejectButton requestId={request.id} onChanged={reload} />
                </td>
              </tr>
            ))}
            {!dashboard?.requests.length ? (
              <tr>
                <td colSpan={4}>
                  <div className="empty">暂无待审批地址</div>
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </section>

      <section className="table-panel" style={{ marginTop: 18 }}>
        <table>
          <thead>
            <tr>
              <th>地址</th>
              <th>全站备注</th>
              <th>启用链</th>
              <th>状态</th>
              <th>最近快照</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {(dashboard?.wallets || []).map((wallet) => (
              <WalletAdminRow key={wallet.id} wallet={wallet} onChanged={reload} />
            ))}
            {!dashboard?.wallets.length ? (
              <tr>
                <td colSpan={6}>
                  <div className="empty">暂无链上地址</div>
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </section>

      <section className="table-panel" style={{ marginTop: 18 }}>
        <table>
          <thead>
            <tr>
              <th>抓取</th>
              <th>状态</th>
              <th>创建时间</th>
              <th>完成时间</th>
              <th>结果</th>
            </tr>
          </thead>
          <tbody>
            {(dashboard?.runs || []).map((run) => (
              <tr key={run.id}>
                <td>{run.kind}</td>
                <td>
                  <span className="status-pill">{runStatusLabel(run.status)}</span>
                </td>
                <td className="muted">{formatTime(run.createdAt)}</td>
                <td className="muted">{formatTime(run.finishedAt)}</td>
                <td className={run.errorText ? "field-error" : "muted"}>{run.errorText || run.summary || "-"}</td>
              </tr>
            ))}
            {!dashboard?.runs.length ? (
              <tr>
                <td colSpan={5}>
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
