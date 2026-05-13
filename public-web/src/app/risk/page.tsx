"use client";

import { Activity, AlertTriangle, CheckCircle2, Gauge, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { LoadingPanel } from "@/components/page-states";
import { useAuth } from "@/lib/auth-context";
import { getMarketTopRisk } from "@/lib/direct-data";
import type { MarketTopRiskData, MarketTopRiskSignal } from "@/lib/types";

const SIGNAL_LABELS: Record<string, string> = {
  breadth_weakness_score: "市场宽度恶化",
  rsp_spy_13w_rel_pctl: "RSP / SPY 13 周相对分位",
  qqew_qqq_13w_rel_pctl: "QQEW / QQQ 13 周相对分位",
  breakage_score: "金融条件 / 信用确认",
  nfci_13w_chg_pctl: "NFCI 13 周转紧分位",
  anfci_pctl: "ANFCI 压力分位",
  credit_baa10y_pctl: "BAA10Y 信用利差分位",
};

const LEVEL_TEXT = {
  low: "低位",
  watch: "观察",
  elevated: "升温",
  high: "高风险",
} as const;

function formatPct(value: number | null, digits = 1) {
  if (value === null || !Number.isFinite(value)) return "-";
  return `${(value * 100).toFixed(digits)}%`;
}

function formatScore(value: number | null) {
  if (value === null || !Number.isFinite(value)) return "-";
  return value.toFixed(3);
}

function formatNumber(value: number | null) {
  if (value === null || !Number.isFinite(value)) return "-";
  return value.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

function RiskBar({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(100, value * 100));
  return (
    <div className="risk-bar" aria-label={`风险分数 ${formatPct(value)}`}>
      <span style={{ width: `${pct}%` }} />
    </div>
  );
}

function SignalRow({ name, signal }: { name: string; signal: MarketTopRiskSignal }) {
  return (
    <tr>
      <td>{SIGNAL_LABELS[name] || name}</td>
      <td>
        <span className={signal.active ? "status-pill risk-pill-active" : "status-pill"}>
          {signal.active ? "触发" : "未触发"}
        </span>
      </td>
      <td>{formatScore(signal.value)}</td>
      <td className="muted">{signal.module}</td>
    </tr>
  );
}

export default function RiskPage() {
  const { loading, supabase } = useAuth();
  const [data, setData] = useState<MarketTopRiskData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      setData(await getMarketTopRisk(supabase, 80));
      setError(null);
    } catch (err) {
      setData(null);
      setError(err instanceof Error ? err.message : "顶部风险数据加载失败");
    } finally {
      setRefreshing(false);
    }
  }, [supabase]);

  useEffect(() => {
    if (loading) return;
    Promise.resolve().then(load);
  }, [load, loading]);

  const latest = data?.latest ?? null;
  const activeSignals = useMemo(
    () => Object.entries(latest?.signals ?? {}).filter(([, signal]) => signal.active),
    [latest],
  );
  const history = data?.history ?? [];

  if (loading) return <LoadingPanel />;

  return (
    <main className="page">
      <div className="section-head">
        <div>
          <h1>顶部风险</h1>
          <p className="muted">用市场宽度恶化做预警，用金融条件和信用压力做确认。这里展示风险状态，不给买卖指令。</p>
        </div>
        <button className="secondary-button" type="button" disabled={refreshing} onClick={load}>
          <RefreshCw size={16} />
          更新
        </button>
      </div>

      {error ? <div className="empty field-error">数据接口未就绪：{error}</div> : null}
      {!latest ? <div className="empty">暂无顶部风险快照</div> : null}

      {latest ? (
        <>
          <section className="risk-grid">
            <div className="panel risk-main-panel">
              <div className="risk-title-row">
                <div>
                  <p className="eyebrow">US MARKET TOP RISK</p>
                  <h2>{LEVEL_TEXT[latest.riskLevel]}</h2>
                </div>
                <span className={`risk-level risk-level-${latest.riskLevel}`}>{LEVEL_TEXT[latest.riskLevel]}</span>
              </div>
              <RiskBar value={latest.riskScore} />
              <div className="metric-row risk-metric-row">
                <div className="metric">
                  <Gauge size={18} />
                  <strong>{formatScore(latest.riskScore)}</strong>
                  <span className="muted">风险分数</span>
                </div>
                <div className="metric">
                  <Activity size={18} />
                  <strong>{formatScore(latest.breadthWeaknessScore)}</strong>
                  <span className="muted">宽度预警</span>
                </div>
                <div className="metric">
                  <AlertTriangle size={18} />
                  <strong>{formatScore(latest.breakageScore)}</strong>
                  <span className="muted">破裂确认</span>
                </div>
              </div>
            </div>

            <div className="panel">
              <h2>当前状态</h2>
              <div className="risk-state-list">
                <div className="risk-state-item">
                  {latest.warningActive ? <AlertTriangle size={18} /> : <CheckCircle2 size={18} />}
                  <div>
                    <strong>{latest.warningActive ? "宽度预警已触发" : "宽度预警未触发"}</strong>
                    <p className="muted">等权指数相对市值加权指数的表现。</p>
                  </div>
                </div>
                <div className="risk-state-item">
                  {latest.confirmationActive ? <AlertTriangle size={18} /> : <CheckCircle2 size={18} />}
                  <div>
                    <strong>{latest.confirmationActive ? "确认信号已触发" : "确认信号未触发"}</strong>
                    <p className="muted">金融条件转紧或信用利差压力。</p>
                  </div>
                </div>
              </div>
              <div className="risk-meta">
                <span>周度：{latest.week}</span>
                <span>NDX：{formatNumber(latest.nasdaq100)}</span>
                <span>距 52 周高点：{formatPct(latest.ndxDdFrom52wHigh)}</span>
              </div>
            </div>
          </section>

          <section className="panel" style={{ marginTop: 18 }}>
            <div className="section-head risk-section-head">
              <div>
                <h2>核心指标</h2>
                <p className="muted">只保留近高位回测里更强的一组信号。</p>
              </div>
              <span className="status-pill">{activeSignals.length} 个触发</span>
            </div>
            <div className="table-panel risk-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>指标</th>
                    <th>状态</th>
                    <th>分位 / 分数</th>
                    <th>模块</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(latest.signals).map(([name, signal]) => (
                    <SignalRow key={name} name={name} signal={signal} />
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="panel" style={{ marginTop: 18 }}>
            <div className="section-head risk-section-head">
              <div>
                <h2>最近历史</h2>
                <p className="muted">近高位基准：未来 26 周平均最大回撤 {formatPct(data?.baseline.nearHighFwd26wAvgDrawdown ?? null)}，10%+ 回撤概率 {formatPct(data?.baseline.nearHighFwd26wDd10Probability ?? null)}。</p>
              </div>
            </div>
            <div className="risk-history">
              {history.slice(-40).map((point) => (
                <div
                  className={`risk-history-bar risk-history-${point.riskLevel}`}
                  key={point.week}
                  title={`${point.week} ${formatScore(point.riskScore)}`}
                >
                  <span style={{ height: `${Math.max(4, Math.min(100, point.riskScore * 100))}%` }} />
                </div>
              ))}
            </div>
          </section>
        </>
      ) : null}
    </main>
  );
}
