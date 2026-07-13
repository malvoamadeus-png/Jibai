"use client";

import { Activity, AlertTriangle, ChevronDown, Gauge, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { LoadingPanel } from "@/components/page-states";
import { useAuth } from "@/lib/auth-context";
import { getMarketTopRisk } from "@/lib/direct-data";
import type { MarketTopRiskData, MarketTopRiskSignal } from "@/lib/types";

type MarketTopRiskMarketState = {
  label: string;
  priceSymbol: string;
  structureScore: number | null;
  structureConfirmed: boolean;
  priceWeaknessScore: number | null;
  priceConfirmed: boolean;
  state: string;
  latestDate: string;
};

const SIGNAL_LABELS: Record<string, string> = {
  rsp_spy_weakness_score: "RSP / SPY 13 周弱化",
  qqew_qqq_weakness_score: "QQEW / QQQ 13 周弱化",
  soxx_qqq_weakness_score: "SOXX / QQQ 13 周弱化",
  xly_xlp_weakness_score: "XLY / XLP 13 周弱化",
  iwm_spy_weakness_score: "IWM / SPY 13 周弱化",
  china_star100_star50_weakness_score: "科创100 / 科创50 实验弱化",
  china_chinext_100_50_weakness_score: "创业板 / 创业板50 实验弱化",
  us_price_weakness_score: "SOXX 价格转弱",
  china_price_weakness_score: "588200.SH 价格转弱",
};

const LEVEL_TEXT = {
  low: "低位",
  watch: "观察",
  elevated: "升温",
  high: "高风险",
} as const;

const STATE_TEXT: Record<string, string> = {
  healthy_rally: "健康上涨",
  crowded_rally: "拥挤上涨",
  ordinary_pullback: "普通回撤",
  top_risk: "顶部风险",
  breakdown_confirmed: "破位确认",
};

const INDICATOR_NOTES = [
  {
    name: "structure",
    title: "结构脆弱",
    group: "日更",
    body: "用 13 周滚动相对表现分位观察宽度变窄、主线退潮和风险偏好转弱。报告每天按最新收盘价重算，状态切换要求最近 3 个交易日至少 2 天满足阈值。",
  },
  {
    name: "price",
    title: "价格转弱",
    group: "日更",
    body: "用 20 日高点回撤、跌破 20 日均线、跌破 50 日均线、20 日均线斜率转负四个条件计算价格转弱分数。结构先脆弱、价格随后转弱，才进入顶部风险。",
  },
  {
    name: "china_experiment",
    title: "中国内部宽度实验",
    group: "实验",
    body: "中国侧用科创100ETF/科创50ETF、创业板ETF/创业板50ETF观察更宽的一侧是否跑输更窄核心。它不是严格等权口径，先用于观察和复盘，不单独作为买卖判断。",
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

function formatDate(value: string | null | undefined, options?: Intl.DateTimeFormatOptions) {
  if (!value) return "-";
  const normalized = /^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T00:00:00Z` : value.replace(" ", "T");
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    ...options,
  }).format(date);
}

function daysSinceDate(value: string | null | undefined) {
  if (!value) return null;
  const date = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return null;
  const today = new Date();
  const todayUtc = Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate());
  const dateUtc = Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate());
  return Math.floor((todayUtc - dateUtc) / 86_400_000);
}

function readRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function readString(value: unknown, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function readNumber(value: unknown) {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function readMarketStates(metrics: Record<string, unknown>): MarketTopRiskMarketState[] {
  return Object.entries(readRecord(metrics.markets)).map(([key, value]) => {
    const item = readRecord(value);
    return {
      label: readString(item.label, key),
      priceSymbol: readString(item.price_symbol ?? item.priceSymbol),
      structureScore: readNumber(item.structure_score ?? item.structureScore),
      structureConfirmed: Boolean(item.structure_confirmed ?? item.structureConfirmed),
      priceWeaknessScore: readNumber(item.price_weakness_score ?? item.priceWeaknessScore),
      priceConfirmed: Boolean(item.price_confirmed ?? item.priceConfirmed),
      state: readString(item.state, "healthy_rally"),
      latestDate: readString(item.latest_date ?? item.latestDate),
    };
  });
}

function isHistoryTick(index: number, length: number) {
  if (length <= 1) return true;
  const last = length - 1;
  const tickIndexes = new Set([0, Math.round(last * 0.25), Math.round(last * 0.5), Math.round(last * 0.75), last]);
  return tickIndexes.has(index);
}

function clampScore(value: number | null) {
  if (value === null || !Number.isFinite(value)) return null;
  return Math.max(0, Math.min(1, value));
}

function buildHistoryPath(
  points: MarketTopRiskData["history"],
  getValue: (point: MarketTopRiskData["history"][number]) => number | null,
  chart: { left: number; top: number; width: number; height: number },
) {
  let started = false;
  return points
    .map((point, index) => {
      const value = clampScore(getValue(point));
      if (value === null) return null;
      const x = chart.left + (points.length === 1 ? chart.width : (index / (points.length - 1)) * chart.width);
      const y = chart.top + (1 - value) * chart.height;
      const command = started ? "L" : "M";
      started = true;
      return `${command} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .filter(Boolean)
    .join(" ");
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

function MarketStateRow({ market }: { market: MarketTopRiskMarketState }) {
  return (
    <tr>
      <td>
        <strong>{market.label}</strong>
        <div className="muted">{market.priceSymbol}</div>
      </td>
      <td>
        <span className={market.structureConfirmed ? "status-pill risk-pill-active" : "status-pill"}>
          {market.structureConfirmed ? "确认" : "未确认"}
        </span>
        <div className="muted">{formatScore(market.structureScore)}</div>
      </td>
      <td>
        <span className={market.priceConfirmed ? "status-pill risk-pill-active" : "status-pill"}>
          {market.priceConfirmed ? "确认" : "未确认"}
        </span>
        <div className="muted">{formatScore(market.priceWeaknessScore)}</div>
      </td>
      <td>
        <span className={`risk-level risk-level-${market.state === "top_risk" || market.state === "breakdown_confirmed" ? "high" : "watch"}`}>
          {STATE_TEXT[market.state] || market.state}
        </span>
      </td>
      <td className="muted">{formatDate(market.latestDate, { year: "numeric" })}</td>
    </tr>
  );
}

function RiskHistoryChart({ history }: { history: MarketTopRiskData["history"] }) {
  const points = history.slice(-80);
  if (!points.length) return <div className="empty">暂无历史风险分数</div>;

  const first = points[0];
  const latest = points.at(-1);
  const chart = { left: 46, top: 20, width: 828, height: 268 };
  const xAxisY = chart.top + chart.height;
  const series = [
    {
      key: "risk",
      label: "总风险",
      color: "#e24a3b",
      value: latest?.riskScore ?? null,
      path: buildHistoryPath(points, (point) => point.riskScore, chart),
    },
    {
      key: "structure",
      label: "结构脆弱",
      color: "#2367c9",
      value: latest?.breadthWeaknessScore ?? null,
      path: buildHistoryPath(points, (point) => point.breadthWeaknessScore, chart),
    },
    {
      key: "price",
      label: "价格转弱",
      color: "#8a5a11",
      value: latest?.breakageScore ?? null,
      path: buildHistoryPath(points, (point) => point.breakageScore, chart),
    },
  ];
  const yTicks = [
    { value: 1, label: "1.0" },
    { value: 0.7, label: "0.7" },
    { value: 0.5, label: "0.5" },
    { value: 0, label: "0" },
  ];

  return (
    <div className="risk-history-shell">
      <div className="risk-history-summary">
        <span>日度分数历史，纵轴 0-1</span>
        <span>
          {formatDate(first.week, { year: "numeric" })} 至 {formatDate(latest?.week, { year: "numeric" })}
        </span>
      </div>
      <div className="risk-history-legend">
        {series.map((item) => (
          <span className="risk-history-legend-item" key={item.key}>
            <i style={{ background: item.color }} />
            {item.label}
            <strong>{formatScore(item.value)}</strong>
          </span>
        ))}
      </div>
      <div className="risk-history-chart">
        <svg className="risk-history-svg" viewBox="0 0 920 340" role="img" aria-label="总风险、结构脆弱和价格转弱的历史分数">
          <rect x={chart.left} y={chart.top} width={chart.width} height={chart.height} rx="8" />
          {yTicks.map((tick) => {
            const y = chart.top + (1 - tick.value) * chart.height;
            return (
              <g key={tick.label}>
                <line x1={chart.left} x2={chart.left + chart.width} y1={y} y2={y} />
                <text x={chart.left - 12} y={y + 4} textAnchor="end">
                  {tick.label}
                </text>
                {tick.value === 0.7 ? (
                  <text className="risk-history-threshold" x={chart.left + chart.width - 8} y={y - 6} textAnchor="end">
                    高风险阈值
                  </text>
                ) : null}
              </g>
            );
          })}
          {points.map((point, index) => {
            if (!isHistoryTick(index, points.length)) return null;
            const x = chart.left + (points.length === 1 ? chart.width : (index / (points.length - 1)) * chart.width);
            return (
              <g key={point.week}>
                <line className="risk-history-xgrid" x1={x} x2={x} y1={chart.top} y2={xAxisY} />
                <text x={x} y={xAxisY + 28} textAnchor={index === 0 ? "start" : index === points.length - 1 ? "end" : "middle"}>
                  {formatDate(point.week)}
                </text>
              </g>
            );
          })}
          <line className="risk-history-axis-line" x1={chart.left} x2={chart.left + chart.width} y1={xAxisY} y2={xAxisY} />
          {series.map((item) => (
            <path key={item.key} d={item.path} stroke={item.color} />
          ))}
        </svg>
      </div>
      <p className="risk-history-note">
        总风险包含“结构脆弱”和“价格转弱”。价格已经确认时，分数会在下跌过程中继续升高；它表示当前风险状态，不等同于单独的提前预警。
      </p>
    </div>
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
  const marketStates = useMemo(() => readMarketStates(latest?.metrics ?? {}), [latest]);
  const overallState = readString(latest?.metrics?.overall_state, "healthy_rally");
  const history = data?.history ?? [];
  const latestWeekAgeDays = daysSinceDate(latest?.week);
  const latestIsStale = latestWeekAgeDays !== null && latestWeekAgeDays > 5;

  if (loading) return <LoadingPanel />;

  return (
    <main className="page">
      <div className="section-head">
        <div>
          <h1>顶部风险</h1>
          <p className="muted">每日检查结构脆弱和价格转弱：先拥挤，后转弱，才进入顶部风险。这里展示风险状态，不给买卖指令。</p>
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
          {latestIsStale ? (
            <div className="risk-data-warning">
              <AlertTriangle size={18} />
              <span>
                最新快照停在 {latest.week}，距今约 {latestWeekAgeDays} 天；请检查顶部风险同步任务或上游数据源。
              </span>
            </div>
          ) : null}

          <section className="risk-grid">
            <div className="panel risk-main-panel">
              <div className="risk-title-row">
                <div>
                  <p className="eyebrow">MARKET TOP RISK</p>
                  <h2>{STATE_TEXT[overallState] || LEVEL_TEXT[latest.riskLevel]}</h2>
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
                  <span className="muted">结构脆弱</span>
                </div>
                <div className="metric">
                  <AlertTriangle size={18} />
                  <strong>{formatScore(latest.breakageScore)}</strong>
                  <span className="muted">价格转弱</span>
                </div>
              </div>
            </div>

            <div className="panel">
              <h2>状态矩阵</h2>
              <div className="table-panel risk-table-wrap risk-state-table">
                <table>
                  <thead>
                    <tr>
                      <th>市场</th>
                      <th>结构</th>
                      <th>价格</th>
                      <th>状态</th>
                      <th>日期</th>
                    </tr>
                  </thead>
                  <tbody>
                    {marketStates.map((market) => (
                      <MarketStateRow key={market.priceSymbol || market.label} market={market} />
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="risk-meta">
                <span>日期：{latest.week}</span>
                <span>写入：{formatDate(latest.updatedAt, { year: "numeric", hour: "2-digit", minute: "2-digit" })}</span>
                <span>NDX：{formatNumber(latest.nasdaq100)}</span>
                <span>距 52 周高点：{formatPct(latest.ndxDdFrom52wHigh)}</span>
              </div>
            </div>
          </section>

          <section className="panel" style={{ marginTop: 18 }}>
            <div className="section-head risk-section-head">
              <div>
                <h2>核心指标</h2>
                <p className="muted">结构指标每日按 13 周滚动相对表现重算；价格指标每日按最新收盘价重算。</p>
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
                <p className="muted">总风险由结构脆弱和价格转弱组成。图中拆开显示两类贡献，便于区分“提前变差”和“下跌后确认”。</p>
              </div>
            </div>
            <RiskHistoryChart history={history} />
          </section>

          <IndicatorGuide />
        </>
      ) : null}
    </main>
  );
}
