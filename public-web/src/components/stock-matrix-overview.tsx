"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, ArrowRight, ExternalLink, RotateCcw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { LoadingPanel } from "@/components/page-states";
import { SignInCta } from "@/components/signin-cta";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/lib/auth-context";
import { getVisibleStockMatrix } from "@/lib/direct-data";
import type { StockMatrixCell, StockMatrixData, StockMatrixStock, StockMatrixView } from "@/lib/types";
import { cn, formatCount, viewSignalLabel } from "@/lib/utils";

function isDateKey(value: string | null) {
  return Boolean(value && /^\d{4}-\d{2}-\d{2}$/.test(value));
}

function cellKey(securityKey: string, accountName: string) {
  return `${securityKey}::${accountName}`;
}

function buildCellMap(cells: StockMatrixCell[]) {
  const map = new Map<string, StockMatrixCell>();
  for (const cell of cells) {
    map.set(cellKey(cell.securityKey, cell.accountName), cell);
  }
  return map;
}

function stockLabel(stock: StockMatrixStock) {
  return [stock.ticker, stock.market].filter(Boolean).join(" / ") || stock.securityKey;
}

function ViewTooltip({
  stock,
  view,
}: {
  stock: StockMatrixStock;
  view: StockMatrixView;
}) {
  return (
    <span className="pointer-events-auto absolute left-1/2 top-5 z-30 hidden w-[min(360px,calc(100vw-48px))] -translate-x-1/2 rounded-2xl border border-[color:var(--border-strong)] bg-[color:var(--paper)] p-4 text-left shadow-[0_18px_50px_rgba(44,33,22,0.18)] group-hover:block group-focus-within:block">
      <span className="mb-2 flex flex-wrap items-center gap-2">
        <Badge variant={view.direction === "positive" ? "positive" : "danger"} className="normal-case">
          {view.date}
        </Badge>
        <Badge variant="neutral" className="normal-case">
          {stock.displayName}
        </Badge>
      </span>
      <span className="block text-sm font-semibold text-[color:var(--ink)]">
        {view.author_nickname || view.account_name} · {viewSignalLabel(view)}
      </span>
      <span className="mt-2 block text-xs leading-6 text-[color:var(--muted-ink)]">
        {view.logic || "暂无逻辑说明"}
      </span>
      {view.evidence.length ? (
        <span className="mt-2 block text-xs leading-6 text-[color:var(--soft-ink)]">
          证据：{view.evidence.join("；")}
        </span>
      ) : null}
      {view.note_urls.length ? (
        <span className="mt-3 flex flex-wrap gap-1.5">
          {view.note_urls.map((url, index) => (
            <span
              key={`${url}-${index}`}
              className="pointer-events-auto inline-flex items-center gap-1 rounded-full border border-[color:var(--border-strong)] px-2 py-1 text-[11px] text-[color:var(--muted-ink)] hover:border-[color:var(--accent)] hover:text-[color:var(--accent-strong)]"
            >
              来源 {index + 1}
              <ExternalLink className="h-3 w-3" />
            </span>
          ))}
        </span>
      ) : null}
    </span>
  );
}

function OpinionDot({
  stock,
  view,
}: {
  stock: StockMatrixStock;
  view: StockMatrixView;
}) {
  const positive = view.direction === "positive";
  return (
    <span className="group relative inline-flex h-5 w-5 items-center justify-center">
      <button
        type="button"
        className="inline-flex h-5 w-5 items-center justify-center rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--ring)]"
        aria-label={`${stock.displayName} ${view.author_nickname || view.account_name} ${view.date} ${positive ? "正向" : "负向"}`}
      >
        <span
          className={cn(
            "h-3 w-3 rounded-full border shadow-[0_1px_4px_rgba(44,33,22,0.18)]",
            positive
              ? "border-[color:rgba(65,122,90,0.42)] bg-[#2f8b57]"
              : "border-[color:rgba(138,61,61,0.42)] bg-[#c4483f]",
          )}
        />
      </button>
      <ViewTooltip stock={stock} view={view} />
    </span>
  );
}

export function StockMatrixOverview() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { loading, profile, signIn, supabase } = useAuth();
  const endParam = searchParams.get("end");
  const endDate = isDateKey(endParam) ? endParam : null;
  const [data, setData] = useState<StockMatrixData | null>(null);
  const [matrixLoading, setMatrixLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (loading) return;
    let cancelled = false;
    Promise.resolve().then(() => {
      if (!cancelled) setMatrixLoading(true);
    });
    getVisibleStockMatrix(supabase, endDate)
      .then((nextData) => {
        if (cancelled) return;
        setData(nextData);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "一览表加载失败");
        setData(null);
      })
      .finally(() => {
        if (!cancelled) setMatrixLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [endDate, loading, supabase]);

  const cellMap = useMemo(() => buildCellMap(data?.cells ?? []), [data]);
  const totalViews = useMemo(
    () => (data?.cells ?? []).reduce((sum, cell) => sum + cell.views.length, 0),
    [data],
  );

  function navigate(nextEndDate: string | null) {
    const next = new URLSearchParams(searchParams);
    if (nextEndDate) next.set("end", nextEndDate);
    else next.delete("end");
    router.push(next.toString() ? `/stocks/overview?${next.toString()}` : "/stocks/overview");
  }

  if (loading) return <LoadingPanel />;

  return (
    <main className="page space-y-6 lg:flex lg:h-[calc(100vh-40px)] lg:flex-col lg:overflow-hidden lg:pb-0">
      <Card className="lg:shrink-0">
        <CardHeader className="gap-4 lg:py-5">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="warm">按股票（一览表）</Badge>
            {!profile ? <Badge variant="neutral">公开预览 · 范围受限</Badge> : null}
          </div>
          <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
            <div>
              <CardTitle className="text-3xl">股票 × 作者观点一览</CardTitle>
              <CardDescription>
                纵向为股票，横向为作者；每个红绿点代表过去 7 天内的一条有效观点。
              </CardDescription>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                variant="secondary"
                disabled={!data?.previousEndDate}
                onClick={() => navigate(data?.previousEndDate ?? null)}
              >
                <ArrowLeft className="h-4 w-4" />
                上一周
              </Button>
              <Button
                type="button"
                variant="secondary"
                disabled={!data?.nextEndDate}
                onClick={() => navigate(data?.nextEndDate ?? null)}
              >
                下一周
                <ArrowRight className="h-4 w-4" />
              </Button>
              <Button type="button" variant="secondary" onClick={() => navigate(null)}>
                <RotateCcw className="h-4 w-4" />
                回到最新
              </Button>
            </div>
          </div>
        </CardHeader>
      </Card>

      {!profile ? <SignInCta onLogin={signIn} compact /> : null}

      <div className="grid gap-4 lg:min-h-0 lg:flex-1 lg:grid-rows-[auto_minmax(0,1fr)]">
        <div className="grid gap-3 md:grid-cols-4">
          <div className="rounded-2xl border border-[color:var(--border)] bg-[color:var(--paper)] px-4 py-3">
            <p className="text-xs text-[color:var(--soft-ink)]">窗口</p>
            <p className="mt-1 text-sm font-semibold">{data?.startDate && data.endDate ? `${data.startDate} 至 ${data.endDate}` : "暂无"}</p>
          </div>
          <div className="rounded-2xl border border-[color:var(--border)] bg-[color:var(--paper)] px-4 py-3">
            <p className="text-xs text-[color:var(--soft-ink)]">股票</p>
            <p className="mt-1 text-sm font-semibold">{formatCount(data?.stocks.length ?? 0)}</p>
          </div>
          <div className="rounded-2xl border border-[color:var(--border)] bg-[color:var(--paper)] px-4 py-3">
            <p className="text-xs text-[color:var(--soft-ink)]">作者</p>
            <p className="mt-1 text-sm font-semibold">{formatCount(data?.authors.length ?? 0)}</p>
          </div>
          <div className="rounded-2xl border border-[color:var(--border)] bg-[color:var(--paper)] px-4 py-3">
            <p className="text-xs text-[color:var(--soft-ink)]">观点点位</p>
            <p className="mt-1 text-sm font-semibold">{formatCount(totalViews)}</p>
          </div>
        </div>

        <Card className="min-h-[420px] overflow-hidden">
          <CardContent className="h-full p-0">
            {error ? <div className="m-4 empty field-error">{error}</div> : null}
            {matrixLoading ? <div className="m-4 empty">一览表加载中</div> : null}
            {!matrixLoading && data && data.stocks.length && data.authors.length ? (
              <div className="h-full overflow-auto overscroll-contain">
                <table className="min-w-max border-separate border-spacing-0">
                  <thead>
                    <tr>
                      <th className="sticky left-0 top-0 z-30 min-w-[220px] border-b border-r border-[color:var(--border)] bg-[color:var(--paper-strong)] px-4 py-3">
                        股票
                      </th>
                      {data.authors.map((author) => (
                        <th
                          key={author.accountName}
                          className="sticky top-0 z-20 min-w-[148px] max-w-[148px] border-b border-r border-[color:var(--border)] bg-[color:var(--paper-strong)] px-3 py-3 align-bottom"
                        >
                          <Link
                            href={`/feed?q=${encodeURIComponent(author.accountName)}`}
                            className="block truncate text-[12px] font-semibold normal-case tracking-normal text-[color:var(--ink)] underline-offset-4 hover:text-[color:var(--accent-strong)] hover:underline"
                            title={author.authorNickname || author.accountName}
                          >
                            {author.authorNickname || author.accountName}
                          </Link>
                          <span className="mt-1 block truncate text-[11px] font-normal normal-case tracking-normal text-[color:var(--soft-ink)]">
                            @{author.accountName} · {formatCount(author.mentionCount)}
                          </span>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.stocks.map((stock) => (
                      <tr key={stock.securityKey}>
                        <th className="sticky left-0 z-10 min-w-[220px] border-b border-r border-[color:var(--border)] bg-[color:var(--paper)] px-4 py-3 text-left align-top">
                          <Link
                            href={`/stocks?stock=${encodeURIComponent(stock.securityKey)}`}
                            className="block text-sm font-semibold normal-case tracking-normal text-[color:var(--ink)] underline-offset-4 hover:text-[color:var(--accent-strong)] hover:underline"
                          >
                            {stock.displayName}
                          </Link>
                          <span className="mt-1 block text-xs font-normal normal-case tracking-normal text-[color:var(--muted-ink)]">
                            {stockLabel(stock)} · {formatCount(stock.mentionCount)}
                          </span>
                        </th>
                        {data.authors.map((author) => {
                          const cell = cellMap.get(cellKey(stock.securityKey, author.accountName));
                          return (
                            <td
                              key={`${stock.securityKey}-${author.accountName}`}
                              className="min-w-[148px] max-w-[148px] border-b border-r border-[color:var(--border)] bg-[color:var(--panel)]/70 px-3 py-3 align-top"
                            >
                              {cell?.views.length ? (
                                <div className="flex flex-wrap gap-1.5">
                                  {cell.views.map((view, index) => (
                                    <OpinionDot
                                      key={`${stock.securityKey}-${author.accountName}-${view.date}-${index}`}
                                      stock={stock}
                                      view={view}
                                    />
                                  ))}
                                </div>
                              ) : (
                                <span className="block h-5 text-xs text-[color:var(--soft-ink)]">-</span>
                              )}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
            {!matrixLoading && data && (!data.stocks.length || !data.authors.length) ? (
              <div className="m-4 empty">{profile ? "这个窗口没有有效股票观点" : "暂无公开预览数据"}</div>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
