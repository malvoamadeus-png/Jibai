"use client";

import { Activity, AlertTriangle, CheckCircle2, ChevronDown, Gauge, RefreshCw } from "lucide-react";
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

const INDICATOR_NOTES = [
  {
    name: "breadth_weakness_score",
    title: "市场宽度恶化",
    group: "预警",
    body: "把 RSP/SPY 和 QQEW/QQQ 的 13 周相对表现转成历史分位后取反，数值越高表示等权指数越明显跑输市值加权指数。近高位回测里，该信号触发后未来 26 周平均最大回撤约 -8.0%，10%+ 回撤概率约 30.7%，高于近高位基准 21.1%。",
  },
  {
    name: "rsp_spy_13w_rel_pctl",
    title: "RSP / SPY 13 周相对分位",
    group: "预警",
    body: "计算 RSP 13 周收益减 SPY 13 周收益，再转为扩展历史分位。分位低说明等权标普跑输市值加权标普，市场上涨更依赖少数大市值股票。近高位回测里，低分位触发后未来 26 周平均最大回撤约 -7.9%，10%+ 回撤概率约 28.2%。",
  },
  {
    name: "qqew_qqq_13w_rel_pctl",
    title: "QQEW / QQQ 13 周相对分位",
    group: "预警",
    body: "计算 QQEW 13 周收益减 QQQ 13 周收益，再转为扩展历史分位。分位低说明纳指内部等权股票跑输龙头权重股，科技板块参与度变差。近高位回测里，低分位触发后未来 26 周平均最大回撤约 -7.3%，10%+ 回撤概率约 25.9%。",
  },
  {
    name: "breakage_score",
    title: "金融条件 / 信用确认",
    group: "确认",
    body: "由 NFCI 13 周变化分位、ANFCI 压力分位和 BAA10Y 信用利差分位组合而成。它不是最早的预警，更像风险从股票内部扩散到金融条件和信用市场后的确认。近高位回测里，该组合触发后未来 26 周平均最大回撤约 -8.0%，10%+ 回撤概率约 32.1%。",
  },
  {
    name: "nfci_13w_chg_pctl",
    title: "NFCI 13 周转紧分位",
    group: "确认",
    body: "NFCI 来自 Chicago Fed，经 FRED 获取。这里计算 NFCI 13 周变化，再转历史分位；分位越高，表示金融条件从宽松转紧越快。近高位回测里，高分位触发后未来 26 周平均最大回撤约 -7.6%，10%+ 回撤概率约 28.9%。",
  },
  {
    name: "anfci_pctl",
    title: "ANFCI 压力分位",
    group: "确认",
    body: "ANFCI 是调整后的 Chicago Fed 金融条件指数，经 FRED 获取。这里使用绝对水平的历史分位；分位越高，表示金融系统压力越高。近高位回测里，高分位触发后未来 26 周平均最大回撤约 -7.4%，10%+ 回撤概率约 27.7%。",
  },
  {
    name: "credit_baa10y_pctl",
    title: "BAA10Y 信用利差分位",
    group: "确认",
    body: "BAA10Y 是 Baa 公司债收益率相对 10 年期美债收益率的利差，经 FRED 获取。这里使用绝对水平历史分位；分位越高，表示信用市场要求更高风险补偿。近高位回测里，高分位触发后未来 26 周平均最大回撤约 -7.2%，10%+ 回撤概率约 30.4%。",
  },
];

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

function IndicatorGuide() {
  return (
    <details className="panel risk-guide">
      <summary>
        <span>指标说明与回测口径</span>
        <ChevronDown size={17} />
      </summary>
      <div className="risk-guide-body">
        <p className="muted">
          回测口径固定为 Nasdaq 100 距 52 周高点 10% 以内的近高位周，观察信号触发后未来 26 周最大回撤。近高位基准为平均最大回撤 -5.5%，10%+ 回撤概率 21.1%。
        </p>
        <div className="risk-guide-list">
          {INDICATOR_NOTES.map((item) => (
            <article className="risk-guide-item" key={item.name}>
              <div className="risk-guide-title">
                <span className="status-pill">{item.group}</span>
                <h3>{item.title}</h3>
              </div>
              <p className="muted">{item.body}</p>
            </article>
          ))}
        </div>
      </div>
    </details>
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

          <IndicatorGuide />
        </>
      ) : null}
    </main>
  );
}
