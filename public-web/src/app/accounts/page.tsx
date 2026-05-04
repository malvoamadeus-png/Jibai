"use client";

import { useCallback, useEffect, useState } from "react";

import { AccountSubscriptionButton } from "@/components/account-actions";
import { LoadingPanel, LoginRequired } from "@/components/page-states";
import { SubmitAccountForm } from "@/components/submit-account-form";
import { useAuth } from "@/lib/auth-context";
import { listAccounts, listMyRequests } from "@/lib/direct-data";
import type { AccountListItem, RequestListItem } from "@/lib/types";

export default function AccountsPage() {
  const { loading, profile, signIn, supabase } = useAuth();
  const [query, setQuery] = useState("");
  const [accounts, setAccounts] = useState<AccountListItem[]>([]);
  const [requests, setRequests] = useState<RequestListItem[]>([]);

  const reload = useCallback(async () => {
    if (!profile) return;
    const [nextAccounts, nextRequests] = await Promise.all([
      listAccounts(supabase, profile, query),
      listMyRequests(supabase, profile),
    ]);
    setAccounts(nextAccounts);
    setRequests(nextRequests);
  }, [profile, query, supabase]);

  useEffect(() => {
    Promise.resolve().then(reload).catch(console.error);
  }, [reload]);

  if (loading) return <LoadingPanel />;
  if (!profile) return <LoginRequired onLogin={signIn} />;

  return (
    <main className="page">
      <div className="section-head">
        <div>
          <h1>账号库</h1>
          <p className="muted">已审批账号可直接订阅，新账号会进入管理员审批。当前版本不再自动抓取新内容。</p>
        </div>
      </div>

      <section className="panel">
        <div className="filter-row" style={{ marginBottom: 12 }}>
          <input
            aria-label="搜索账号"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索已审批账号"
          />
        </div>
        <SubmitAccountForm onSubmitted={reload} />
      </section>

      <section className="table-panel" style={{ marginTop: 18 }}>
        <table>
          <thead>
            <tr>
              <th>账号</th>
              <th>历史</th>
              <th>订阅</th>
            </tr>
          </thead>
          <tbody>
            {accounts.map((account) => (
              <tr key={account.id}>
                <td>
                  <a className="account-cell" href={account.profileUrl} target="_blank" rel="noreferrer">
                    <strong>@{account.username}</strong>
                    <span className="muted">{account.displayName}</span>
                  </a>
                </td>
                <td>
                  <span className="status-pill">{account.backfillCompletedAt ? "已有导入" : "等待导入"}</span>
                </td>
                <td>
                  <AccountSubscriptionButton accountId={account.id} subscribed={account.subscribed} onChanged={reload} />
                </td>
              </tr>
            ))}
            {!accounts.length ? (
              <tr>
                <td colSpan={3}>
                  <div className="empty">暂无已审批账号</div>
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </section>

      <section className="panel" style={{ marginTop: 18 }}>
        <h2>我的提交</h2>
        {requests.length ? (
          <table>
            <thead>
              <tr>
                <th>账号</th>
                <th>状态</th>
                <th>时间</th>
              </tr>
            </thead>
            <tbody>
              {requests.map((request) => (
                <tr key={request.id}>
                  <td>@{request.normalizedUsername}</td>
                  <td>
                    <span className="status-pill">{request.status}</span>
                  </td>
                  <td className="muted">{new Date(request.createdAt).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="empty">暂无提交</div>
        )}
      </section>
    </main>
  );
}
