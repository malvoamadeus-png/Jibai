"use client";

import { useCallback, useEffect, useState } from "react";

import { AccountSubscriptionButton } from "@/components/account-actions";
import { LoadingPanel } from "@/components/page-states";
import { SignInCta } from "@/components/signin-cta";
import { SubmitAccountForm } from "@/components/submit-account-form";
import { useAuth } from "@/lib/auth-context";
import { listAccounts, listMyRequests } from "@/lib/direct-data";
import type { AccountListItem, RequestListItem } from "@/lib/types";

export default function AccountsPage() {
  const { loading, profile, signIn, supabase } = useAuth();
  const [query, setQuery] = useState("");
  const [accounts, setAccounts] = useState<AccountListItem[]>([]);
  const [requests, setRequests] = useState<RequestListItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (loading) return;
    try {
      const [nextAccounts, nextRequests] = await Promise.all([
        listAccounts(supabase, profile, query),
        profile ? listMyRequests(supabase, profile) : Promise.resolve([]),
      ]);
      setAccounts(nextAccounts);
      setRequests(nextRequests);
      setError(null);
    } catch (err) {
      setAccounts([]);
      setRequests([]);
      setError(err instanceof Error ? err.message : "账号库加载失败");
    }
  }, [loading, profile, query, supabase]);

  useEffect(() => {
    Promise.resolve().then(reload);
  }, [reload]);

  if (loading) return <LoadingPanel />;

  return (
    <main className="page">
      <div className="section-head">
        <div>
          <h1>账号库</h1>
          <p className="muted">
            已审批账号未登录也可浏览。订阅、提交新账号和查看自己的提交记录需要 Google 登录。
          </p>
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
          <button className="secondary-button" type="button" onClick={reload}>
            更新
          </button>
        </div>
        {error ? <div className="empty field-error">数据接口未就绪：{error}</div> : null}
        {profile ? <SubmitAccountForm onSubmitted={reload} /> : <SignInCta onLogin={signIn} compact />}
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

      {profile ? (
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
      ) : null}
    </main>
  );
}
