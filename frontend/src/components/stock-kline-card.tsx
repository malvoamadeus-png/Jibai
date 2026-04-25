"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn, formatCount, platformLabel, stanceLabel } from "@/lib/utils";
import type {
  EntityAuthorView,
  StockKlineCandle,
  StockKlineData,
  StockKlineMarker,
  ViewStance,
} from "@/lib/types";

const SVG_WIDTH = 1120;
const SVG_HEIGHT = 420;
const PAD_TOP = 36;
const PAD_RIGHT = 20;
const PAD_BOTTOM = 36;
const PAD_LEFT = 56;

type StockIdentity = {
  securityKey: string;
  ticker: string | null;
  market: string | null;
};

type EastMoneyPayload = {
  data?: {
    klines?: string[];
  } | null;
};

function formatPrice(value: number | null | undefined) {
  if (value === null || value === undefined) return "--";
  return new Intl.NumberFormat("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function toNumber(value: string | number | null | undefined) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function resolveAshareIdentity(identity: StockIdentity) {
  const normalizedMarket = (identity.market ?? "").trim().toUpperCase();
  const normalizedTicker = (identity.ticker ?? "").trim();

  if (normalizedTicker && /^\d{6}$/.test(normalizedTicker)) {
    if (normalizedMarket === "SSE") return { ticker: normalizedTicker, market: "SSE" as const };
    if (normalizedMarket === "SZSE") return { ticker: normalizedTicker, market: "SZSE" as const };
    if (normalizedMarket === "BJSE") return { ticker: normalizedTicker, market: "BJSE" as const };
  }

  const match = identity.securityKey.match(/^(\d{6})\.(sh|sz|bj)$/i);
  if (!match) {
    return null;
  }

  const [, ticker, suffix] = match;
  return {
    ticker,
    market:
      suffix.toLowerCase() === "sh"
        ? ("SSE" as const)
        : suffix.toLowerCase() === "sz"
          ? ("SZSE" as const)
          : ("BJSE" as const),
  };
}

function parseEastMoneyCandles(rawLines: string[] | null | undefined) {
  return (rawLines ?? [])
    .map((rawLine) => {
      const parts = String(rawLine).split(",");
      if (parts.length < 6) {
        return null;
      }

      const open = toNumber(parts[1]);
      const close = toNumber(parts[2]);
      const high = toNumber(parts[3]);
      const low = toNumber(parts[4]);
      const volume = toNumber(parts[5]);
      if (!parts[0] || open === null || close === null || high === null || low === null) {
        return null;
      }

      return {
        date: parts[0],
        open,
        high,
        low,
        close,
        volume,
      } satisfies StockKlineCandle;
    })
    .filter((item): item is StockKlineCandle => item !== null)
    .sort((left, right) => left.date.localeCompare(right.date));
}

function fetchEastMoneyCandlesInBrowser(identity: StockIdentity, days: number) {
  const resolved = resolveAshareIdentity(identity);
  if (!resolved || typeof window === "undefined" || typeof document === "undefined") {
    return Promise.resolve<StockKlineCandle[]>([]);
  }

  return new Promise<StockKlineCandle[]>((resolve, reject) => {
    const callbackName = `__eastmoneyKline_${Date.now()}_${Math.random().toString(36).slice(2)}`;
    const scopedWindow = window as unknown as Window &
      Record<string, ((payload: EastMoneyPayload) => void) | undefined>;
    const params = new URLSearchParams({
      secid: `${resolved.market === "SSE" ? "1" : "0"}.${resolved.ticker}`,
      ut: "fa5fd1943c7b386f172d6893dbfba10b",
      fields1: "f1,f2,f3,f4,f5,f6",
      fields2: "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
      klt: "101",
      fqt: "1",
      beg: "0",
      end: "20500101",
      smplmt: "1000000",
      lmt: String(Math.max(30, Math.min(days, 1000))),
    });
    const script = document.createElement("script");
    const timeoutId = window.setTimeout(() => {
      cleanup();
      reject(new Error("EastMoney JSONP timeout"));
    }, 12_000);

    function cleanup() {
      window.clearTimeout(timeoutId);
      if (script.parentNode) {
        script.parentNode.removeChild(script);
      }
      delete scopedWindow[callbackName];
    }

    scopedWindow[callbackName] = (payload: EastMoneyPayload) => {
      cleanup();
      resolve(parseEastMoneyCandles(payload.data?.klines));
    };

    script.async = true;
    script.onerror = () => {
      cleanup();
      reject(new Error("EastMoney JSONP failed"));
    };
    script.src = `https://push2his.eastmoney.com/api/qt/stock/kline/get?cb=${callbackName}&${params.toString()}`;
    (document.head || document.body || document.documentElement).appendChild(script);
  });
}

function markerFill(stance: ViewStance) {
  if (stance === "strong_bullish" || stance === "bullish") return "#2f7d56";
  if (stance === "strong_bearish" || stance === "bearish") return "#b34747";
  if (stance === "mixed") return "#b56a3b";
  return "#8c7b6a";
}

function markerBadgeVariant(stance: ViewStance) {
  if (stance === "strong_bullish" || stance === "bullish") return "positive" as const;
  if (stance === "strong_bearish" || stance === "bearish") return "danger" as const;
  if (stance === "mixed") return "warm" as const;
  return "neutral" as const;
}

function isBullish(stance: ViewStance) {
  return stance === "strong_bullish" || stance === "bullish";
}

function isBearish(stance: ViewStance) {
  return stance === "strong_bearish" || stance === "bearish";
}

function markerOffset(index: number) {
  if (index === 0) return 0;
  const distance = Math.ceil(index / 2) * 7;
  return index % 2 === 0 ? distance : -distance;
}

function summarizeViews(authorViews: EntityAuthorView[]) {
  return authorViews.reduce(
    (accumulator, view) => {
      if (isBullish(view.stance)) accumulator.bullish += 1;
      else if (isBearish(view.stance)) accumulator.bearish += 1;
      else accumulator.other += 1;
      return accumulator;
    },
    { bullish: 0, bearish: 0, other: 0 },
  );
}

function renderMarkerNodes(
  marker: StockKlineMarker,
  x: number,
  highY: number,
  lowY: number,
) {
  let bullishCount = 0;
  let bearishCount = 0;
  let otherCount = 0;

  return marker.authorViews.map((view, index) => {
    const bullish = isBullish(view.stance);
    const bearish = isBearish(view.stance);
    const stackIndex = bullish ? bullishCount++ : bearish ? bearishCount++ : otherCount++;
    const cy = bullish
      ? highY - 12 - stackIndex * 12
      : bearish
        ? lowY + 12 + stackIndex * 12
        : highY - 12 - (bullishCount + stackIndex) * 12;

    return (
      <circle
        key={`${marker.date}-${view.platform}-${view.account_name}-${index}`}
        cx={x + markerOffset(stackIndex)}
        cy={cy}
        r={4.5}
        fill={markerFill(view.stance)}
        stroke="rgba(255,250,242,0.95)"
        strokeWidth="1.2"
      >
        <title>{`${marker.date} / ${view.author_nickname || view.account_name} / ${stanceLabel(view.stance)}`}</title>
      </circle>
    );
  });
}

function buildPriceScale(candles: StockKlineCandle[]) {
  const lows = candles.map((item) => item.low);
  const highs = candles.map((item) => item.high);
  const min = Math.min(...lows);
  const max = Math.max(...highs);
  const padding = Math.max((max - min) * 0.12, max * 0.01, 1);
  return { min: min - padding, max: max + padding };
}

function ActiveDayPanel({
  candle,
  marker,
  sourceLabel,
}: {
  candle: StockKlineCandle | undefined;
  marker: StockKlineMarker | undefined;
  sourceLabel: string | null;
}) {
  if (!candle) {
    return (
      <div className="rounded-[24px] border border-dashed border-[color:var(--border-strong)] px-4 py-6 text-sm text-[color:var(--muted-ink)]">
        暂无可展示的日线数据。
      </div>
    );
  }

  const summary = summarizeViews(marker?.authorViews ?? []);

  return (
    <div className="space-y-4">
      <div className="rounded-[24px] border border-[color:var(--border)] bg-[color:var(--paper-strong)] p-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="warm">{candle.date}</Badge>
          {sourceLabel ? <Badge variant="neutral">{sourceLabel}</Badge> : null}
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <div>
            <p className="text-xs uppercase tracking-[0.14em] text-[color:var(--soft-ink)]">Open / Close</p>
            <p className="mt-1 text-lg font-semibold text-[color:var(--ink)]">
              {formatPrice(candle.open)} / {formatPrice(candle.close)}
            </p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.14em] text-[color:var(--soft-ink)]">High / Low</p>
            <p className="mt-1 text-lg font-semibold text-[color:var(--ink)]">
              {formatPrice(candle.high)} / {formatPrice(candle.low)}
            </p>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Badge variant="positive">{`看多 ${summary.bullish}`}</Badge>
          <Badge variant="danger">{`看空 ${summary.bearish}`}</Badge>
          <Badge variant="neutral">{`其他 ${summary.other}`}</Badge>
          {marker ? <Badge variant="warm">{`提及 ${formatCount(marker.mentionCount)}`}</Badge> : null}
        </div>
      </div>

      <div className="rounded-[24px] border border-[color:var(--border)] bg-[color:var(--panel)]/80 p-4">
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm font-medium text-[color:var(--ink)]">当天观点</p>
          <p className="text-xs uppercase tracking-[0.14em] text-[color:var(--soft-ink)]">
            {marker ? `${marker.authorViews.length} 位作者` : "暂无标记"}
          </p>
        </div>
        {marker && marker.authorViews.length > 0 ? (
          <div className="mt-4 space-y-3">
            {marker.authorViews.map((view) => (
              <div
                key={`${marker.date}-${view.platform}-${view.account_name}`}
                className="rounded-[20px] border border-[color:var(--border)] bg-[color:var(--paper)] px-4 py-3"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-semibold text-[color:var(--ink)]">
                    {view.author_nickname || view.account_name}
                  </p>
                  <Badge variant="neutral" className="normal-case tracking-[0.04em]">{platformLabel(view.platform)}</Badge>
                  <Badge variant={markerBadgeVariant(view.stance)}>{stanceLabel(view.stance)}</Badge>
                </div>
                <p className="mt-2 text-sm leading-6 text-[color:var(--muted-ink)]">
                  {view.logic || "当天有观点提及，但没有写出更细的逻辑说明。"}
                </p>
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-3 text-sm leading-6 text-[color:var(--muted-ink)]">
            这根日线目前没有对应的作者观点标记。
          </p>
        )}
      </div>
    </div>
  );
}

export function StockKlineCard({
  displayName,
  chart,
  identity,
}: {
  displayName: string;
  chart: StockKlineData;
  identity: StockIdentity;
}) {
  const [activeDate, setActiveDate] = useState<string | null>(
    chart.markers.at(-1)?.date ?? chart.candles.at(-1)?.date ?? null,
  );
  const [browserChartOverride, setBrowserChartOverride] = useState<{
    key: string;
    chart: StockKlineData;
  } | null>(null);
  const attemptedChartKeysRef = useRef<Set<string>>(new Set());

  const ashareIdentity = useMemo(() => resolveAshareIdentity(identity), [identity]);
  const chartKey = useMemo(
    () =>
      [
        identity.securityKey,
        chart.sourceLabel ?? "",
        chart.message ?? "",
        chart.candles.length,
        chart.candles[0]?.date ?? "",
        chart.candles.at(-1)?.date ?? "",
      ].join("|"),
    [chart, identity.securityKey],
  );
  const resolvedChart =
    browserChartOverride && browserChartOverride.key === chartKey ? browserChartOverride.chart : chart;
  const shouldRetryEastMoney =
    Boolean(ashareIdentity) &&
    resolvedChart.sourceLabel !== "东财" &&
    (resolvedChart.sourceLabel === "新浪" ||
      resolvedChart.sourceLabel === "东财 / 新浪" ||
      resolvedChart.candles.length === 0 ||
      (resolvedChart.message ?? "").includes("东财"));

  useEffect(() => {
    if (!shouldRetryEastMoney) {
      return;
    }
    if (attemptedChartKeysRef.current.has(chartKey)) {
      return;
    }

    attemptedChartKeysRef.current.add(chartKey);
    let cancelled = false;

    void fetchEastMoneyCandlesInBrowser(identity, Math.max(resolvedChart.candles.length, 180))
      .then((candles) => {
        if (cancelled || candles.length === 0) {
          return;
        }

        setBrowserChartOverride({
          key: chartKey,
          chart: {
            ...chart,
            sourceLabel: "东财",
            message: null,
            candles,
          },
        });
      })
      .catch(() => {
        // Keep the server-side fallback when browser-side EastMoney is unavailable.
      });

    return () => {
      cancelled = true;
    };
  }, [chart, chartKey, identity, resolvedChart.candles.length, shouldRetryEastMoney]);

  const bannerMessage =
    resolvedChart.candles.length > 0 &&
    resolvedChart.sourceLabel === "新浪" &&
    (resolvedChart.message ?? "").includes("东财")
      ? null
      : resolvedChart.message;
  const selectedDate =
    activeDate && resolvedChart.candles.some((item) => item.date === activeDate)
      ? activeDate
      : resolvedChart.markers.at(-1)?.date ?? resolvedChart.candles.at(-1)?.date ?? null;

  if (resolvedChart.candles.length === 0) {
    return (
      <Card className="overflow-hidden">
        <CardHeader className="bg-[linear-gradient(135deg,rgba(181,106,59,0.12),rgba(87,112,97,0.08))]">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="warm">日线 K 线</Badge>
            {resolvedChart.sourceLabel ? <Badge variant="neutral">{resolvedChart.sourceLabel}</Badge> : null}
          </div>
          <CardTitle className="text-2xl">{displayName} 暂时还没有行情图</CardTitle>
          <CardDescription>
            {bannerMessage || "当前没有拿到可绘制的日线数据，但下方按天观点时间线仍然可正常查看。"}
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  const candles = resolvedChart.candles;
  const markersByDate = new Map(resolvedChart.markers.map((item) => [item.date, item]));
  const activeCandle = candles.find((item) => item.date === selectedDate) ?? candles.at(-1);
  const activeMarker = activeCandle ? markersByDate.get(activeCandle.date) : undefined;
  const scale = buildPriceScale(candles);
  const plotWidth = SVG_WIDTH - PAD_LEFT - PAD_RIGHT;
  const plotHeight = SVG_HEIGHT - PAD_TOP - PAD_BOTTOM;
  const step = plotWidth / Math.max(candles.length, 1);
  const bodyWidth = Math.max(3, Math.min(10, step * 0.58));
  const latest = candles.at(-1);
  const previous = candles.length > 1 ? candles[candles.length - 2] : null;
  const latestChange = latest && previous ? latest.close - previous.close : null;

  const priceToY = (price: number) =>
    PAD_TOP + ((scale.max - price) / Math.max(scale.max - scale.min, 0.0001)) * plotHeight;

  return (
    <Card className="overflow-hidden">
      <CardHeader className="bg-[linear-gradient(135deg,rgba(181,106,59,0.14),rgba(87,112,97,0.1))]">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="warm">日线 K 线</Badge>
          {resolvedChart.sourceLabel ? <Badge variant="neutral">{resolvedChart.sourceLabel}</Badge> : null}
          <Badge variant="positive">观点标记</Badge>
        </div>
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-2">
            <CardTitle className="text-2xl">日线与观点标记</CardTitle>
            <CardDescription>
              每根蜡烛是一个交易日，绿色点偏多，红色点偏空，灰色点表示中性或仅提及。
            </CardDescription>
          </div>
          {latest ? (
            <div className="rounded-[22px] border border-[color:var(--border)] bg-[color:rgba(255,250,242,0.72)] px-4 py-3">
              <p className="text-xs uppercase tracking-[0.14em] text-[color:var(--soft-ink)]">Latest Close</p>
              <p className="mt-1 text-2xl font-semibold text-[color:var(--ink)]">{formatPrice(latest.close)}</p>
              <p
                className={cn(
                  "mt-1 text-sm font-medium",
                  latestChange !== null && latestChange >= 0 ? "text-[#2f7d56]" : "text-[#b34747]",
                )}
              >
                {latestChange === null ? "暂无对比" : `${latestChange >= 0 ? "+" : ""}${formatPrice(latestChange)}`}
              </p>
            </div>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="pt-6">
        {bannerMessage ? (
          <div className="mb-4 rounded-[20px] border border-[color:rgba(181,106,59,0.22)] bg-[color:rgba(181,106,59,0.09)] px-4 py-3 text-sm text-[color:var(--accent-strong)]">
            {bannerMessage}
          </div>
        ) : null}

        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
          <div className="rounded-[24px] border border-[color:var(--border)] bg-[color:var(--paper-strong)] p-3">
            <div className="overflow-x-auto">
              <svg
                viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`}
                className="min-w-[760px] w-full"
                role="img"
                aria-label={`${displayName} 日线 K 线和作者观点标记`}
              >
                {[0, 1, 2, 3, 4].map((tick) => {
                  const y = PAD_TOP + (plotHeight / 4) * tick;
                  const price = scale.max - ((scale.max - scale.min) / 4) * tick;
                  return (
                    <g key={`grid-${tick}`}>
                      <line
                        x1={PAD_LEFT}
                        y1={y}
                        x2={SVG_WIDTH - PAD_RIGHT}
                        y2={y}
                        stroke="rgba(82,60,42,0.1)"
                        strokeDasharray="4 8"
                      />
                      <text
                        x={PAD_LEFT - 10}
                        y={y + 4}
                        fontSize="11"
                        fill="rgba(107,86,70,0.85)"
                        textAnchor="end"
                      >
                        {formatPrice(price)}
                      </text>
                    </g>
                  );
                })}

                {candles.map((candle, index) => {
                  const x = PAD_LEFT + step * index + step / 2;
                  const openY = priceToY(candle.open);
                  const closeY = priceToY(candle.close);
                  const highY = priceToY(candle.high);
                  const lowY = priceToY(candle.low);
                  const marker = markersByDate.get(candle.date);
                  const rising = candle.close >= candle.open;
                  const bodyY = Math.min(openY, closeY);
                  const bodyHeight = Math.max(Math.abs(closeY - openY), 1.5);
                  const fill = rising ? "#3b7d5f" : "#b65b54";
                  const stroke = rising ? "#295845" : "#8f403c";

                  return (
                    <g
                      key={candle.date}
                      onMouseEnter={() => setActiveDate(candle.date)}
                      onClick={() => setActiveDate(candle.date)}
                      className="cursor-pointer"
                    >
                      {selectedDate === candle.date ? (
                        <rect
                          x={x - step / 2}
                          y={PAD_TOP - 10}
                          width={step}
                          height={plotHeight + 20}
                          fill="rgba(181,106,59,0.08)"
                          rx="8"
                        />
                      ) : null}
                      <line
                        x1={x}
                        y1={highY}
                        x2={x}
                        y2={lowY}
                        stroke={stroke}
                        strokeWidth="1.5"
                      />
                      <rect
                        x={x - bodyWidth / 2}
                        y={bodyY}
                        width={bodyWidth}
                        height={bodyHeight}
                        rx="1.5"
                        fill={fill}
                        stroke={stroke}
                        strokeWidth="1"
                      >
                        <title>{`${candle.date} O ${formatPrice(candle.open)} H ${formatPrice(candle.high)} L ${formatPrice(candle.low)} C ${formatPrice(candle.close)}`}</title>
                      </rect>
                      {marker ? renderMarkerNodes(marker, x, highY, lowY) : null}
                    </g>
                  );
                })}

                <text
                  x={PAD_LEFT}
                  y={SVG_HEIGHT - 8}
                  fontSize="11"
                  fill="rgba(107,86,70,0.8)"
                >
                  {candles[0]?.date}
                </text>
                <text
                  x={SVG_WIDTH - PAD_RIGHT}
                  y={SVG_HEIGHT - 8}
                  fontSize="11"
                  fill="rgba(107,86,70,0.8)"
                  textAnchor="end"
                >
                  {candles.at(-1)?.date}
                </text>
              </svg>
            </div>
          </div>

          <ActiveDayPanel candle={activeCandle} marker={activeMarker} sourceLabel={resolvedChart.sourceLabel} />
        </div>
      </CardContent>
    </Card>
  );
}
