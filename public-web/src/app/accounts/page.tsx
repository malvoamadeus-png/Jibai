"use client";

import { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";

import { AccountSubscriptionButton } from "@/components/account-actions";
import { LoadingPanel } from "@/components/page-states";
import { SignInCta } from "@/components/signin-cta";
import { SubmitAccountForm } from "@/components/submit-account-form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { PageHeader, SectionCard } from "@/components/ui/page";
import { useAuth } from "@/lib/auth-context";
import { listAccounts, listMyRequests } from "@/lib/direct-data";
import type { AccountListItem, RequestListItem } from "@/lib/types";

export default function AccountsPage({
  domain = "stock",
}: {
  domain?: "stock" | "crypto";
}) {
  const { loading, profile, signIn, supabase } = useAuth();
  const [query, setQuery] = useState("");
  const [accounts, setAccounts] = useState<AccountListItem[]>([]);
  const [requests, setRequests] = useState<RequestListItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (loading) return;
    try {
      const [nextAccounts, nextRequests] = await Promise.all([
        listAccounts(supabase, profile, query, domain),
        profile ? listMyRequests(supabase, profile, domain) : Promise.resolve([]),
      ]);
      setAccounts(nextAccounts);
      setRequests(nextRequests);
      setError(null);
    } catch (err) {
      setAccounts([]);
      setRequests([]);
      setError(err instanceof Error ? err.message : "账号库加载失败");
    }
  }, [domain, loading, profile, query, supabase]);

  useEffect(() => {
    Promise.resolve().then(reload);
  }, [reload]);

  if (loading) return <LoadingPanel />;

  return (
    <main className="page">
      <PageHeader
        eyebrow={domain === "crypto" ? "Crypto Accounts" : "Account Library"}
        title={domain === "crypto" ? "加密账号库" : "账号库"}
        description="已审批账号未登录也可浏览。订阅、提交新账号和查看自己的提交记录需要 Google 登录。"
        badges={
          <>
            <Badge variant="warm">{domain === "crypto" ? "加密" : "股票"}</Badge>
            <Badge variant="neutral">{profile ? "已登录" : "公开可见"}</Badge>
          </>
        }
      />

      <SectionCard
        title="筛选与提交"
        description="快速搜索已审批账号，或提交一个新的公开 X 账号进入审核流程。"
        actions={
          <Button type="button" variant="secondary" onClick={reload}>
            <RefreshCw className="h-4 w-4" />
            更新
          </Button>
        }
      >
        <div className="filter-row">
          <Input
            aria-label="搜索账号"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索已审批账号"
          />
        </div>
        {error ? <div className="empty field-error">数据接口未就绪：{error}</div> : null}
        {profile ? <SubmitAccountForm onSubmitted={reload} domain={domain} /> : <SignInCta onLogin={signIn} compact />}
      </SectionCard>

      <section className="table-panel">
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
                  <AccountSubscriptionButton accountId={account.id} subscribed={account.subscribed} onChanged={reload} domain={domain} />
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
        <SectionCard title="我的提交" description="这里记录你发起过的账号审核请求。">
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
        </SectionCard>
      ) : null}
    </main>
  );
}
