import { redirect } from "next/navigation";

import { ApproveButton, ManualRunButton, RejectButton } from "@/components/admin-actions";
import { getCurrentProfile } from "@/lib/auth";
import { listAdminDashboard } from "@/lib/data";

export const dynamic = "force-dynamic";

export default async function AdminPage() {
  const profile = await getCurrentProfile();
  if (!profile) redirect("/");
  if (!profile.isAdmin) redirect("/");
  const dashboard = await listAdminDashboard();

  return (
    <main className="page">
      <div className="section-head">
        <div>
          <h1>管理</h1>
          <p className="muted">审批账号、查看抓取队列和运行状态。</p>
        </div>
        <ManualRunButton />
      </div>

      <section className="metric-row">
        <div className="metric">
          <strong>{dashboard.approvedCount}/100</strong>
          <span className="muted">已批准账号</span>
        </div>
        <div className="metric">
          <strong>{dashboard.requests.length}</strong>
          <span className="muted">待审批</span>
        </div>
        <div className="metric">
          <strong>{dashboard.jobs.filter((job) => job.status === "running").length}</strong>
          <span className="muted">运行中</span>
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
            {dashboard.requests.map((request) => (
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
                  <ApproveButton requestId={request.id} />
                  <RejectButton requestId={request.id} />
                </td>
              </tr>
            ))}
            {!dashboard.requests.length ? (
              <tr>
                <td colSpan={4}>
                  <div className="empty">暂无待审批账号</div>
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
              <th>任务</th>
              <th>状态</th>
              <th>结果</th>
              <th>时间</th>
            </tr>
          </thead>
          <tbody>
            {dashboard.jobs.map((job) => (
              <tr key={job.id}>
                <td>{job.kind}</td>
                <td>
                  <span className="status-pill">{job.status}</span>
                </td>
                <td>{job.errorText || job.summary || "-"}</td>
                <td className="muted">{new Date(job.createdAt).toLocaleString()}</td>
              </tr>
            ))}
            {!dashboard.jobs.length ? (
              <tr>
                <td colSpan={4}>
                  <div className="empty">暂无任务</div>
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </section>
    </main>
  );
}
