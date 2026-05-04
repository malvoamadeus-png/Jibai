import { redirect } from "next/navigation";

import { AccountSubscriptionButton } from "@/components/account-actions";
import { SubmitAccountForm } from "@/components/submit-account-form";
import { getCurrentProfile } from "@/lib/auth";
import { listAccounts, listMyRequests } from "@/lib/data";

export const dynamic = "force-dynamic";

export default async function AccountsPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const profile = await getCurrentProfile();
  if (!profile) redirect("/");
  const params = await searchParams;
  const [accounts, requests] = await Promise.all([
    listAccounts(profile, params.q || ""),
    listMyRequests(profile),
  ]);

  return (
    <main className="page">
      <div className="section-head">
        <div>
          <h1>账号库</h1>
          <p className="muted">已审批账号可直接订阅，新账号会进入管理员审批。</p>
        </div>
      </div>

      <section className="panel">
        <SubmitAccountForm />
      </section>

      <section className="table-panel" style={{ marginTop: 18 }}>
        <table>
          <thead>
            <tr>
              <th>账号</th>
              <th>回溯</th>
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
                  <span className="status-pill">{account.backfillCompletedAt ? "已完成" : "排队中"}</span>
                </td>
                <td>
                  <AccountSubscriptionButton accountId={account.id} subscribed={account.subscribed} />
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
