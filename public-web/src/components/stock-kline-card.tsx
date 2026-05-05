"use client";

import type * as React from "react";
import { useMemo, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn, formatCount, viewSignalLabel, viewSignalVariant } from "@/lib/utils";
import type {
  EntityAuthorView,
  StockKlineCandle,
  StockKlineData,
  StockKlineMarker,
} from "@/lib/types";

const SVG_WIDTH = 1120;
const SVG_HEIGHT = 420;
const PAD_TOP = 36;
const PAD_RIGHT = 20;
const PAD_BOTTOM = 36;
const PAD_LEFT = 56;
const MIN_VISIBLE_CANDLES = 20;
const DEFAULT_VISIBLE_CANDLES = 180;

type StockIdentity = {
  securityKey: string;
  ticker: string | null;
  market: string | null;
};

type ViewportState = {
  start: number;
  visibleCount: number;
};

type ViewportOverride = {
  key: string;
  state: ViewportState;
};

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function formatPrice(value: number | null | undefined) {
  if (value === null || value === undefined) return "--";
  return new Intl.NumberFormat("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function markerFill(view: EntityAuthorView) {
  if (viewSignalVariant(view) === "positive") return "#2f7d56";
  if (viewSignalVariant(view) === "danger") return "#b34747";
  if (viewSignalVariant(view) === "warm") return "#b56a3b";
  return "#8c7b6a";
}

function isBullish(view: EntityAuthorView) {
  return viewSignalVariant(view) === "positive";
}

function isBearish(view: EntityAuthorView) {
  return viewSignalVariant(view) === "danger";
}

function markerOffset(index: number) {
  if (index === 0) return 0;
  const distance = Math.ceil(index / 2) * 7;
  return index % 2 === 0 ? distance : -distance;
}

function summarizeViews(authorViews: EntityAuthorView[]) {
  return authorViews.reduce(
    (accumulator, view) => {
      if (isBullish(view)) accumulator.bullish += 1;
      else if (isBearish(view)) accumulator.bearish += 1;
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
  plotBottomY: number,
) {
  let bullishCount = 0;
  let bearishCount = 0;
  let flagCount = 0;

  return marker.authorViews.map((view, index) => {
    const bullish = isBullish(view);
    const bearish = isBearish(view);
    const stackIndex = bullish ? bullishCount++ : bearish ? bearishCount++ : flagCount++;
    const offsetX = markerOffset(stackIndex);
    const cx = x + offsetX;
    const fill = markerFill(view);
    const stroke = "rgba(255,250,242,0.96)";

    if (bullish) {
      const tipY = lowY + 10 + stackIndex * 18;
      return (
        <g key={`${marker.date}-${view.platform}-${view.account_name}-${index}`}>
          <line x1={cx} y1={tipY + 12} x2={cx} y2={tipY + 4} stroke={fill} strokeWidth="2.2" />
          <path
            d={`M ${cx} ${tipY} L ${cx - 6} ${tipY + 7} H ${cx - 2.2} V ${tipY + 13} H ${cx + 2.2} V ${tipY + 7} H ${cx + 6} Z`}
            fill={fill}
            stroke={stroke}
            strokeWidth="1.4"
            strokeLinejoin="round"
          />
          <title>{`${marker.date} / ${view.account_name || view.author_nickname} / ${viewSignalLabel(view)}`}</title>
        </g>
      );
    }

    if (bearish) {
      const tipY = highY - 10 - stackIndex * 18;
      return (
        <g key={`${marker.date}-${view.platform}-${view.account_name}-${index}`}>
          <line x1={cx} y1={tipY - 12} x2={cx} y2={tipY - 4} stroke={fill} strokeWidth="2.2" />
          <path
            d={`M ${cx} ${tipY} L ${cx - 6} ${tipY - 7} H ${cx - 2.2} V ${tipY - 13} H ${cx + 2.2} V ${tipY - 7} H ${cx + 6} Z`}
            fill={fill}
            stroke={stroke}
            strokeWidth="1.4"
            strokeLinejoin="round"
          />
          <title>{`${marker.date} / ${view.account_name || view.author_nickname} / ${viewSignalLabel(view)}`}</title>
        </g>
      );
    }

    const stemBottomY = plotBottomY - 8 - stackIndex * 18;
    const stemTopY = stemBottomY - 16;
    const flagTopY = stemTopY + 1.5;

    return (
      <g key={`${marker.date}-${view.platform}-${view.account_name}-${index}`}>
        <line x1={cx} y1={stemBottomY} x2={cx} y2={stemTopY} stroke={fill} strokeWidth="2.1" />
        <path
          d={`M ${cx + 1} ${flagTopY} L ${cx + 10} ${flagTopY + 3.8} L ${cx + 1} ${flagTopY + 8.2} Z`}
          fill={fill}
          stroke={stroke}
          strokeWidth="1.3"
          strokeLinejoin="round"
        />
        <title>{`${marker.date} / ${view.account_name || view.author_nickname} / ${viewSignalLabel(view)}`}</title>
      </g>
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

function buildDefaultViewport(totalCandles: number): ViewportState {
  if (totalCandles <= 0) {
    return { start: 0, visibleCount: 0 };
  }
  const visibleCount = Math.min(totalCandles, DEFAULT_VISIBLE_CANDLES);
  return {
    start: Math.max(0, totalCandles - visibleCount),
    visibleCount,
  };
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
                    {view.account_name || view.author_nickname}
                  </p>
                  <Badge variant={viewSignalVariant(view)}>{viewSignalLabel(view)}</Badge>
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
  const [viewportOverride, setViewportOverride] = useState<ViewportOverride | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const dragStateRef = useRef<{
    pointerId: number;
    clientX: number;
    start: number;
  } | null>(null);
  const [isDragging, setIsDragging] = useState(false);

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
  const resolvedChart = chart;
  const bannerMessage = resolvedChart.message;

  const candles = resolvedChart.candles;
  const totalCandles = candles.length;
  const viewport =
    viewportOverride && viewportOverride.key === chartKey
      ? viewportOverride.state
      : buildDefaultViewport(totalCandles);
  const minVisibleCount =
    totalCandles <= 0 ? 0 : Math.min(totalCandles, MIN_VISIBLE_CANDLES);
  const visibleCount =
    totalCandles <= 0
      ? 0
      : clamp(
          viewport.visibleCount || Math.min(totalCandles, DEFAULT_VISIBLE_CANDLES),
          minVisibleCount,
          totalCandles,
        );
  const maxWindowStart = Math.max(0, totalCandles - visibleCount);
  const windowStart = clamp(viewport.start, 0, maxWindowStart);
  const visibleCandles = candles.slice(windowStart, windowStart + visibleCount);
  const markersByDate = new Map(resolvedChart.markers.map((item) => [item.date, item]));
  const selectedDate =
    activeDate && candles.some((item) => item.date === activeDate)
      ? activeDate
      : resolvedChart.markers.at(-1)?.date ?? candles.at(-1)?.date ?? null;
  const activeCandle = selectedDate ? candles.find((item) => item.date === selectedDate) : candles.at(-1);
  const activeMarker = activeCandle ? markersByDate.get(activeCandle.date) : undefined;

  if (totalCandles === 0) {
    return (
      <Card className="overflow-hidden">
        <CardHeader className="bg-[linear-gradient(135deg,rgba(181,106,59,0.12),rgba(87,112,97,0.08))]">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="warm">日线 K 线</Badge>
            {resolvedChart.sourceLabel ? <Badge variant="neutral">{resolvedChart.sourceLabel}</Badge> : null}
          </div>
          <CardTitle className="text-2xl">{displayName} 暂时还没有行情图</CardTitle>
          <CardDescription>
            {bannerMessage || "当前没有拿到可绘制的日线数据，但下方按天观点时间线仍然可以正常查看。"}
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  const scale = buildPriceScale(visibleCandles);
  const plotWidth = SVG_WIDTH - PAD_LEFT - PAD_RIGHT;
  const plotHeight = SVG_HEIGHT - PAD_TOP - PAD_BOTTOM;
  const step = plotWidth / Math.max(visibleCandles.length, 1);
  const bodyWidth = Math.max(3, Math.min(10, step * 0.58));
  const latest = candles.at(-1);
  const previous = candles.length > 1 ? candles[candles.length - 2] : null;
  const latestChange = latest && previous ? latest.close - previous.close : null;
  const canPan = totalCandles > visibleCount;
  const priceToY = (price: number) =>
    PAD_TOP + ((scale.max - price) / Math.max(scale.max - scale.min, 0.0001)) * plotHeight;

  function moveWindow(nextStart: number) {
    setViewportOverride({
      key: chartKey,
      state: {
        start: clamp(nextStart, 0, Math.max(0, totalCandles - visibleCount)),
        visibleCount,
      },
    });
  }

  function updateViewport(nextStart: number, nextVisibleCount: number) {
    const clampedVisibleCount = clamp(nextVisibleCount, minVisibleCount, totalCandles);
    setViewportOverride({
      key: chartKey,
      state: {
        start: clamp(nextStart, 0, Math.max(0, totalCandles - clampedVisibleCount)),
        visibleCount: clampedVisibleCount,
      },
    });
  }

  function resolveCandleIndexFromClientX(clientX: number) {
    const svg = svgRef.current;
    if (!svg || visibleCandles.length === 0) {
      return null;
    }
    const rect = svg.getBoundingClientRect();
    if (rect.width <= 0) {
      return null;
    }
    const viewboxX = ((clientX - rect.left) / rect.width) * SVG_WIDTH;
    const plotX = clamp(viewboxX - PAD_LEFT, 0, plotWidth);
    const rawIndex = Math.round((plotX - step / 2) / Math.max(step, 0.0001));
    return clamp(rawIndex, 0, visibleCandles.length - 1);
  }

  function selectDateFromClientX(clientX: number) {
    const candleIndex = resolveCandleIndexFromClientX(clientX);
    if (candleIndex === null) {
      return;
    }
    const date = visibleCandles[candleIndex]?.date;
    if (date) {
      setActiveDate(date);
    }
  }

  function setVisibleWindow(nextVisibleCount: number) {
    const clampedVisibleCount = clamp(nextVisibleCount, minVisibleCount, totalCandles);
    updateViewport(Math.max(0, totalCandles - clampedVisibleCount), clampedVisibleCount);
  }

  function zoomVisibleWindow(nextVisibleCount: number, anchorIndex: number) {
    const clampedVisibleCount = clamp(nextVisibleCount, minVisibleCount, totalCandles);
    const anchorRatio =
      visibleCount <= 1 ? 1 : clamp((anchorIndex - windowStart) / (visibleCount - 1), 0, 1);
    const nextStart = Math.round(anchorIndex - anchorRatio * Math.max(clampedVisibleCount - 1, 0));
    updateViewport(nextStart, clampedVisibleCount);
  }

  function handlePointerDown(event: React.PointerEvent<HTMLDivElement>) {
    selectDateFromClientX(event.clientX);
    if (!canPan) {
      return;
    }
    dragStateRef.current = {
      pointerId: event.pointerId,
      clientX: event.clientX,
      start: windowStart,
    };
    setIsDragging(true);
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function handlePointerMove(event: React.PointerEvent<HTMLDivElement>) {
    selectDateFromClientX(event.clientX);
    const dragState = dragStateRef.current;
    if (!dragState || dragState.pointerId !== event.pointerId) {
      return;
    }
    const candlesPerPixel = visibleCount / plotWidth;
    const deltaX = event.clientX - dragState.clientX;
    const nextStart = Math.round(dragState.start - deltaX * candlesPerPixel);
    moveWindow(nextStart);
  }

  function stopDragging(event?: React.PointerEvent<HTMLDivElement>) {
    if (event && dragStateRef.current?.pointerId === event.pointerId) {
      try {
        event.currentTarget.releasePointerCapture(event.pointerId);
      } catch {
        // Ignore release errors when the pointer is already gone.
      }
    }
    dragStateRef.current = null;
    setIsDragging(false);
  }

  function handleWheel(event: React.WheelEvent<HTMLDivElement>) {
    if (event.deltaY === 0 || totalCandles === 0) {
      return;
    }

    let nextVisibleCount = Math.round(visibleCount * (event.deltaY > 0 ? 1.12 : 0.88));
    if (nextVisibleCount === visibleCount) {
      nextVisibleCount += event.deltaY > 0 ? 1 : -1;
    }
    nextVisibleCount = clamp(nextVisibleCount, minVisibleCount, totalCandles);
    if (nextVisibleCount === visibleCount) {
      return;
    }

    event.preventDefault();
    selectDateFromClientX(event.clientX);
    const anchorOffset = resolveCandleIndexFromClientX(event.clientX) ?? (visibleCandles.length - 1);
    zoomVisibleWindow(nextVisibleCount, windowStart + anchorOffset);
  }

  const rangePresets = [
    { label: "1M", value: 22 },
    { label: "3M", value: 66 },
    { label: "6M", value: 132 },
    { label: "1Y", value: 252 },
    { label: "全部", value: totalCandles },
  ];

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
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-[20px] border border-[color:var(--border)] bg-[color:var(--paper)] px-4 py-3">
              <p className="text-sm font-medium text-[color:var(--ink)]">时间窗口</p>
              <div className="flex flex-wrap items-center gap-2">
                {rangePresets.map((preset) => {
                  const presetValue = clamp(preset.value, minVisibleCount, totalCandles);
                  const active = visibleCount === presetValue;
                  return (
                    <Button
                      key={preset.label}
                      type="button"
                      size="sm"
                      variant={active ? "primary" : "secondary"}
                      onClick={() => setVisibleWindow(presetValue)}
                    >
                      {preset.label}
                    </Button>
                  );
                })}
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  disabled={visibleCount <= minVisibleCount}
                  onClick={() => setVisibleWindow(Math.max(minVisibleCount, Math.round(visibleCount * 0.7)))}
                >
                  放大
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  disabled={visibleCount >= totalCandles}
                  onClick={() => setVisibleWindow(Math.min(totalCandles, Math.round(visibleCount * 1.35)))}
                >
                  缩小
                </Button>
              </div>
            </div>

            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 px-1 text-xs text-[color:var(--soft-ink)]">
              <span>{`${visibleCandles[0]?.date} -> ${visibleCandles.at(-1)?.date}`}</span>
              <span>{selectedDate ?? visibleCandles.at(-1)?.date}</span>
            </div>

            <div className="mt-3 overflow-x-auto">
              <div
                className={cn(
                  "select-none rounded-[18px]",
                  canPan ? (isDragging ? "cursor-grabbing" : "cursor-grab") : "cursor-default",
                )}
                onPointerDown={handlePointerDown}
                onPointerMove={handlePointerMove}
                onPointerUp={stopDragging}
                onPointerCancel={stopDragging}
                onWheel={handleWheel}
                onPointerLeave={(event) => {
                  if (dragStateRef.current?.pointerId === event.pointerId) {
                    stopDragging(event);
                  }
                }}
                style={{ touchAction: "pan-y" }}
              >
                <svg
                  ref={svgRef}
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

                  {visibleCandles.map((candle, index) => {
                    const x = PAD_LEFT + step * index + step / 2;
                    const openY = priceToY(candle.open);
                    const closeY = priceToY(candle.close);
                    const highY = priceToY(candle.high);
                    const lowY = priceToY(candle.low);
                    const marker = markersByDate.get(candle.date);
                    const rising = candle.close >= candle.open;
                    const bodyY = Math.min(openY, closeY);
                    const bodyHeight = Math.max(Math.abs(closeY - openY), 1.5);
                    const fill = rising ? "#3b7d5f" : "rgba(255,250,242,0.98)";
                    const stroke = rising ? "#295845" : "#8f403c";

                    return (
                      <g
                        key={candle.date}
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
                          strokeWidth={rising ? "1" : "1.8"}
                        >
                          <title>{`${candle.date} O ${formatPrice(candle.open)} H ${formatPrice(candle.high)} L ${formatPrice(candle.low)} C ${formatPrice(candle.close)}`}</title>
                        </rect>
                        {marker ? renderMarkerNodes(marker, x, highY, lowY, PAD_TOP + plotHeight) : null}
                      </g>
                    );
                  })}

                  <text x={PAD_LEFT} y={SVG_HEIGHT - 8} fontSize="11" fill="rgba(107,86,70,0.8)">
                    {visibleCandles[0]?.date}
                  </text>
                  <text
                    x={SVG_WIDTH - PAD_RIGHT}
                    y={SVG_HEIGHT - 8}
                    fontSize="11"
                    fill="rgba(107,86,70,0.8)"
                    textAnchor="end"
                  >
                    {visibleCandles.at(-1)?.date}
                  </text>
                </svg>
              </div>
            </div>

            {canPan ? (
              <div className="mt-4 rounded-[20px] border border-[color:var(--border)] bg-[color:var(--paper)] px-4 py-3">
                <input
                  type="range"
                  min={0}
                  max={maxWindowStart}
                  step={1}
                  value={windowStart}
                  onChange={(event) => moveWindow(Number(event.target.value))}
                  className="w-full accent-[color:var(--accent)]"
                  aria-label="调整 K 线时间窗口"
                />
                <div className="mt-2 flex items-center justify-between gap-3 text-xs text-[color:var(--soft-ink)]">
                  <span>{candles[0]?.date}</span>
                  <span>{candles.at(-1)?.date}</span>
                </div>
              </div>
            ) : null}
          </div>

          <ActiveDayPanel candle={activeCandle} marker={activeMarker} sourceLabel={resolvedChart.sourceLabel} />
        </div>
      </CardContent>
    </Card>
  );
}
