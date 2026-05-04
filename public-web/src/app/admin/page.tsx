"use client";

import { useCallback, useEffect, useState } from "react";

import { ApproveButton, RejectButton } from "@/components/admin-actions";
import { LoadingPanel, LoginRequired } from "@/components/page-states";
import { useAuth } from "@/lib/auth-context";
import { listAdminDashboard } from "@/lib/direct-data";
import type { AdminRequestItem } from "@/lib/types";

export default function AdminPage() {
  const { loading, profile, signIn, supabase } = useAuth();
  const [approvedCount, setApprovedCount] = useState(0);
  const [requests, setRequests] = useState<AdminRequestItem[]>([]);

  const reload = useCallback(async () => {
    if (!profile?.isAdmin) return;
    const dashboard = await listAdminDashboard(supabase);
    setApprovedCount(dashboard.approvedCount);
    setRequests(dashboard.requests);
  }, [profile, supabase]);

  useEffect(() => {
    Promise.resolve().then(reload).catch(console.error);
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

  return (
    <main className="page">
      <div className="section-head">
        <div>
          <h1>管理</h1>
          <p className="muted">审批账号请求。当前版本已经关闭 Linux worker，不再提供手动抓取按钮。</p>
        </div>
      </div>

      <section className="metric-row">
        <div className="metric">
          <strong>{approvedCount}/100</strong>
          <span className="muted">已批准账号</span>
        </div>
        <div className="metric">
          <strong>{requests.length}</strong>
          <span className="muted">待审批</span>
        </div>
        <div className="metric">
          <strong>关闭</strong>
          <span className="muted">自动抓取</span>
        </div>
      </section>

      <section className="table-panel" style={{ marginTop: 18 }}>
        <table>
          <thead>
            <tr>
              <th>账号</th>
              <th>提交人</th>
              <th>时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {requests.map((request) => (
              <tr key={request.id}>
                <td>
                  <a className="account-cell" href={request.account.profileUrl} target="_blank" rel="noreferrer">
                    <strong>@{request.account.username}</strong>
                    <span className="muted">{request.rawInput}</span>
                  </a>
                </td>
                <td>{request.requesterEmail}</td>
                <td className="muted">{new Date(request.createdAt).toLocaleString()}</td>
                <td>
                  <ApproveButton requestId={request.id} onChanged={reload} />
                  <RejectButton requestId={request.id} onChanged={reload} />
                </td>
              </tr>
            ))}
            {!requests.length ? (
              <tr>
                <td colSpan={4}>
                  <div className="empty">暂无待审批账号</div>
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </section>
    </main>
  );
}
