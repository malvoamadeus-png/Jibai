"use client";

import { useCallback, useEffect, useState } from "react";

import {
  AddCryptoBlockedTermButton,
  ApproveButton,
  DisableButton,
  ManualRunButton,
  RejectButton,
  RemoveCryptoBlockedTermButton,
  ToggleDomainPipelineButton,
} from "@/components/admin-actions";
import { LoadingPanel, LoginRequired } from "@/components/page-states";
import { useAuth } from "@/lib/auth-context";
import { listAdminDashboard, listCryptoAdminControls } from "@/lib/direct-data";
import type {
  AdminAccountItem,
  AdminJobItem,
  AdminRequestItem,
  CryptoAdminBlockedTermItem,
  CryptoAdminDeletedAssetItem,
  DomainRuntimeControl,
} from "@/lib/types";

const JOB_LABELS: Record<string, string> = {
  initial_backfill: "首次回填",
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
  const pattern = /(\w+)=([\s\S]*?)(?=\s+\w+=|$)/g;
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

export default function AdminPage({ domain = "stock" }: { domain?: "stock" | "crypto" }) {
  const { loading, profile, signIn, supabase } = useAuth();
  const [approvedCount, setApprovedCount] = useState(0);
  const [approvedAccounts, setApprovedAccounts] = useState<AdminAccountItem[]>([]);
  const [requests, setRequests] = useState<AdminRequestItem[]>([]);
  const [jobs, setJobs] = useState<AdminJobItem[]>([]);
  const [blockedTerms, setBlockedTerms] = useState<CryptoAdminBlockedTermItem[]>([]);
  const [deletedAssets, setDeletedAssets] = useState<CryptoAdminDeletedAssetItem[]>([]);
  const [runtimeControl, setRuntimeControl] = useState<DomainRuntimeControl>({
    domain: "crypto",
    pipelineEnabled: true,
    updatedAt: null,
  });
  const [newBlockedTerm, setNewBlockedTerm] = useState("base");

  const reload = useCallback(async () => {
    if (!profile?.isAdmin) return;
    const [dashboard, cryptoControls] = await Promise.all([
      listAdminDashboard(supabase, domain),
      domain === "crypto" ? listCryptoAdminControls(supabase) : Promise.resolve(null),
    ]);
    setApprovedCount(dashboard.approvedCount);
    setApprovedAccounts(dashboard.approvedAccounts);
    setRequests(dashboard.requests);
    setJobs(dashboard.jobs);
    setRuntimeControl(cryptoControls?.runtimeControl ?? { domain: "crypto", pipelineEnabled: true, updatedAt: null });
    setBlockedTerms(cryptoControls?.blockedTerms ?? []);
    setDeletedAssets(cryptoControls?.deletedAssets ?? []);
  }, [domain, profile, supabase]);

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
  const cryptoPipelineEnabled = runtimeControl.pipelineEnabled;

  return (
    <main className="page">
      <div className="section-head">
        <div>
          <h1>管理</h1>
          <p className="muted">审批账号请求。通过后会创建首次回填任务，worker 会定时轮询并串行执行。</p>
        </div>
        <div style={{ display: "grid", gap: 8, justifyItems: "end" }}>
          <ManualRunButton onChanged={reload} domain={domain} disabled={domain === "crypto" && !cryptoPipelineEnabled} />
          {domain === "crypto" && !cryptoPipelineEnabled ? (
            <span className="muted" style={{ fontSize: 12 }}>
              加密板块已关闭，暂不允许手动抓取。
            </span>
          ) : null}
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
          <strong>{runningJobs}</strong>
          <span className="muted">运行中任务</span>
        </div>
      </section>

      {domain === "crypto" ? (
        <>
          <section className="table-panel" style={{ marginTop: 18 }}>
            <div className="section-head" style={{ marginBottom: 12 }}>
              <div>
                <h2>运行开关</h2>
                <p className="muted">关闭后会停掉加密板块的新定时任务、手动任务和待执行任务，并跳过资产简报生成。</p>
              </div>
              <ToggleDomainPipelineButton domain="crypto" enabled={cryptoPipelineEnabled} onChanged={reload} />
            </div>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                gap: 12,
                flexWrap: "wrap",
                alignItems: "center",
              }}
            >
              <div>
                <strong>{cryptoPipelineEnabled ? "运行中" : "已关闭"}</strong>
                <p className="muted" style={{ marginTop: 6 }}>
                  {cryptoPipelineEnabled ? "新的加密采集和分析任务会继续执行。" : "已有公开数据继续可见，但后端不会继续更新。"}
                </p>
              </div>
              <span className="muted">最近更新：{formatTime(runtimeControl.updatedAt)}</span>
            </div>
          </section>

          <section className="table-panel" style={{ marginTop: 18 }}>
            <div className="section-head" style={{ marginBottom: 12 }}>
              <div>
                <h2>屏蔽词</h2>
                <p className="muted">命中屏蔽词的标的会直接跳过摘要生成，并从 crypto 可见标的结果里隐藏。</p>
              </div>
              <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
                <input
                  value={newBlockedTerm}
                  onChange={(event) => setNewBlockedTerm(event.target.value)}
                  placeholder="输入屏蔽词"
                  className="input"
                  style={{ minWidth: 180 }}
                />
                <AddCryptoBlockedTermButton term={newBlockedTerm} onChanged={reload} />
              </div>
            </div>
            <table>
              <thead>
                <tr>
                  <th>词</th>
                  <th>更新时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {blockedTerms.map((item) => (
                  <tr key={item.term}>
                    <td>{item.term}</td>
                    <td className="muted">{formatTime(item.updatedAt)}</td>
                    <td>
                      <RemoveCryptoBlockedTermButton term={item.term} onChanged={reload} />
                    </td>
                  </tr>
                ))}
                {!blockedTerms.length ? (
                  <tr>
                    <td colSpan={3}>
                      <div className="empty">暂无屏蔽词</div>
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </section>

          <section className="table-panel" style={{ marginTop: 18 }}>
            <div className="section-head" style={{ marginBottom: 12 }}>
              <div>
                <h2>已删除标的</h2>
                <p className="muted">管理员删除后，该标的会从列表、详情和一览表中隐藏。</p>
              </div>
            </div>
            <table>
              <thead>
                <tr>
                  <th>标的</th>
                  <th>原因</th>
                  <th>更新时间</th>
                </tr>
              </thead>
              <tbody>
                {deletedAssets.map((item) => (
                  <tr key={item.assetKey}>
                    <td>
                      <strong>{item.displayName}</strong>
                      <div className="muted">{item.assetKey}</div>
                    </td>
                    <td>{item.reason || "-"}</td>
                    <td className="muted">{formatTime(item.updatedAt)}</td>
                  </tr>
                ))}
                {!deletedAssets.length ? (
                  <tr>
                    <td colSpan={3}>
                      <div className="empty">暂无已删除标的</div>
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </section>
        </>
      ) : null}

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
              <th>首次回填</th>
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
                  <DisableButton accountId={account.id} onChanged={reload} domain={domain} />
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
