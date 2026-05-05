"use client";

import { useCallback, useEffect, useState } from "react";

import { ApproveButton, DisableButton, ManualRunButton, RejectButton } from "@/components/admin-actions";
import { LoadingPanel, LoginRequired } from "@/components/page-states";
import { useAuth } from "@/lib/auth-context";
import { listAdminDashboard } from "@/lib/direct-data";
import type { AdminAccountItem, AdminJobItem, AdminRequestItem } from "@/lib/types";

const JOB_LABELS: Record<string, string> = {
  initial_backfill: "首次回溯",
  scheduled_crawl: "定时抓取",
  manual_crawl: "手动抓取",
};

const STATUS_LABELS: Record<string, string> = {
  pending: "等待中",
  running: "运行中",
  succeeded: "成功",
  failed: "失败",
};

function formatTime(value: string | null) {
  return value ? new Date(value).toLocaleString() : "-";
}

function parseLegacySummary(summary: string) {
  const result: Record<string, string> = {};
  const pattern =
    /(\w+)=([\s\S]*?)(?=\s+\w+=|$)/g;
  for (const match of summary.matchAll(pattern)) {
    result[match[1]] = match[2].trim();
  }
  return result;
}

function formatLegacyMarketSample(value?: string) {
  if (!value) return "";
  const names = Array.from(value.matchAll(/\[market ([^\]]+)\]/g))
    .map((match) => match[1])
    .filter(Boolean);
  const uniqueNames = Array.from(new Set(names)).slice(0, 3);
  return uniqueNames.length ? `（${uniqueNames.join("、")}）` : "";
}

function formatJobResult(job: AdminJobItem) {
  if (job.errorText) return job.errorText;
  if (!job.summary) return "-";
  if (!job.summary.includes("=")) return job.summary;

  const values = parseLegacySummary(job.summary);
  if (!values.accounts && !values.new_notes && !values.market_errors) return job.summary;

  const parts: string[] = [];
  const accounts = Number(values.accounts || 0);
  const newNotes = Number(values.new_notes || 0);
  const crawlErrors = Number(values.crawl_errors || 0);
  const marketPrices = Number(values.market_prices || 0);
  const marketErrors = Number(values.market_errors || 0);
  const totalErrors = Number(values.total_errors || 0);

  if (accounts) parts.push(`抓取 ${accounts} 个账号`);
  parts.push(`新增 ${newNotes} 条内容`);
  if (crawlErrors) parts.push(`${crawlErrors} 个账号抓取失败`);
  if (marketPrices) parts.push(`写入 ${marketPrices} 条行情`);
  if (marketErrors) {
    parts.push(`${marketErrors} 个股票行情暂不可用${formatLegacyMarketSample(values.market_error_sample)}`);
  }
  const nonCrawlErrors = Math.max(0, totalErrors - crawlErrors);
  if (nonCrawlErrors) parts.push(`${nonCrawlErrors} 项分析或入库异常`);
  if (!crawlErrors && !marketErrors && !totalErrors) parts.push("全部完成");
  return `${parts.join("；")}。`;
}

export default function AdminPage() {
  const { loading, profile, signIn, supabase } = useAuth();
  const [approvedCount, setApprovedCount] = useState(0);
  const [approvedAccounts, setApprovedAccounts] = useState<AdminAccountItem[]>([]);
  const [requests, setRequests] = useState<AdminRequestItem[]>([]);
  const [jobs, setJobs] = useState<AdminJobItem[]>([]);

  const reload = useCallback(async () => {
    if (!profile?.isAdmin) return;
    const dashboard = await listAdminDashboard(supabase);
    setApprovedCount(dashboard.approvedCount);
    setApprovedAccounts(dashboard.approvedAccounts);
    setRequests(dashboard.requests);
    setJobs(dashboard.jobs);
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

  const runningJobs = jobs.filter((job) => job.status === "running").length;

  return (
    <main className="page">
      <div className="section-head">
        <div>
          <h1>管理</h1>
          <p className="muted">审批账号请求。通过后会创建首次回溯任务，阿里云 worker 会定时轮询并串行执行。</p>
        </div>
        <ManualRunButton onChanged={reload} />
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
          <strong>{runningJobs}</strong>
          <span className="muted">运行中任务</span>
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
                <td className="muted">{formatTime(request.createdAt)}</td>
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

      <section className="table-panel" style={{ marginTop: 18 }}>
        <table>
          <thead>
            <tr>
              <th>已批准账号</th>
              <th>首次回溯</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {approvedAccounts.map((account) => (
              <tr key={account.id}>
                <td>
                  <a className="account-cell" href={account.profileUrl} target="_blank" rel="noreferrer">
                    <strong>@{account.username}</strong>
                    <span className="muted">{account.displayName}</span>
                  </a>
                </td>
                <td className="muted">{formatTime(account.backfillCompletedAt)}</td>
                <td>
                  <DisableButton accountId={account.id} onChanged={reload} />
                </td>
              </tr>
            ))}
            {!approvedAccounts.length ? (
              <tr>
                <td colSpan={3}>
                  <div className="empty">暂无已批准账号</div>
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
              <th>创建时间</th>
              <th>完成时间</th>
              <th>结果</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <tr key={job.id}>
                <td>{JOB_LABELS[job.kind] || job.kind}</td>
                <td>
                  <span className="status-pill">{STATUS_LABELS[job.status] || job.status}</span>
                </td>
                <td className="muted">{formatTime(job.createdAt)}</td>
                <td className="muted">{formatTime(job.finishedAt)}</td>
                <td className={job.errorText ? "field-error" : "muted"}>{formatJobResult(job)}</td>
              </tr>
            ))}
            {!jobs.length ? (
              <tr>
                <td colSpan={5}>
                  <div className="empty">暂无抓取任务</div>
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </section>
    </main>
  );
}
