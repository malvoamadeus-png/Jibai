"use client";

import Link from "next/link";
import { ExternalLink, RefreshCw, Sparkles, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import { EmptyState } from "@/components/empty-state";
import { LoadingPanel } from "@/components/page-states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page";
import { useAuth } from "@/lib/auth-context";
import { deleteStockNewsTrackingItem, deleteStockNewsTrackingStock, getStockNewsTracking } from "@/lib/direct-data";
import { formatCount, formatShanghaiDateTime } from "@/lib/utils";
import type { StockNewsTrackingItem, StockNewsTrackingResponse, StockNewsTrackingStock } from "@/lib/types";

function parsePage(value: string | null) {
  const parsed = Number.parseInt(value || "1", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

function buildTrackingUrl(page: number) {
  if (page <= 1) return "/stocks/news/tracking";
  return `/stocks/news/tracking?page=${page}`;
}

function asText(value: unknown, fallback = "") {
  return typeof value === "string" && value ? value : fallback;
}

function formatPercent(value: number | null) {
  if (value === null) return "等待";
  const formatted = new Intl.NumberFormat("zh-CN", {
    style: "percent",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
  return value > 0 ? `+${formatted}` : formatted;
}

function returnClass(value: number | null) {
  if (value === null) return "text-[color:var(--soft-ink)]";
  return value >= 0 ? "text-[color:var(--danger)]" : "text-[color:var(--success)]";
}

function statusLabel(status: string) {
  const mapping: Record<string, string> = {
    pending: "等待分析",
    analyzing: "分析中",
    succeeded: "已完成",
    failed: "分析失败",
  };
  return mapping[status] || status || "等待分析";
}

function horizonLabel(status: string, value: number | null) {
  if (status === "scored") return formatPercent(value);
  if (status === "missing_price") return "缺行情";
  return "等待";
}

function stockLabel(stock: StockNewsTrackingStock) {
  return [stock.ticker, stock.market].filter(Boolean).join(" / ") || stock.securityKey;
}

function NewsCell({ item }: { item: StockNewsTrackingItem }) {
  const snapshot = item.eventSnapshot;
  const headline = asText(snapshot.headline, item.eventKey);
  const summary = asText(snapshot.event_summary ?? snapshot.eventSummary);
  const noteUrl = asText(snapshot.note_url ?? snapshot.noteUrl);
  const author = asText(snapshot.author_nickname ?? snapshot.authorNickname) || asText(snapshot.account_name ?? snapshot.accountName);
  return (
    <div className="max-w-[360px] space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={item.status === "failed" ? "danger" : item.status === "succeeded" ? "warm" : "neutral"}>{statusLabel(item.status)}</Badge>
        {item.eventDate ? <Badge variant="neutral">{item.eventDate}</Badge> : null}
      </div>
      <div>
        <p className="text-sm font-semibold leading-6 text-[color:var(--ink)]">{headline}</p>
        {summary ? <p className="mt-1 text-xs leading-5 text-[color:var(--muted-ink)]">{summary}</p> : null}
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs text-[color:var(--soft-ink)]">
        {author ? <span>{author}</span> : null}
        {noteUrl ? (
          <Link href={noteUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[color:var(--accent-strong)] hover:underline">
            原文
            <ExternalLink className="h-3.5 w-3.5" />
          </Link>
        ) : null}
      </div>
      {item.errorText ? <p className="field-error">{item.errorText}</p> : null}
    </div>
  );
}

export function StockNewsTrackingTable() {
  const searchParams = useSearchParams();
  const { loading, profile, supabase } = useAuth();
  const [page, setPage] = useState(() => parsePage(searchParams.get("page")));
  const [data, setData] = useState<StockNewsTrackingResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [trackingLoading, setTrackingLoading] = useState(true);
  const [deletingStockId, setDeletingStockId] = useState<string | null>(null);
  const [deletingTrackingId, setDeletingTrackingId] = useState<string | null>(null);

  useEffect(() => {
    function syncFromLocation() {
      const next = new URLSearchParams(window.location.search);
      setPage(parsePage(next.get("page")));
    }
    window.addEventListener("popstate", syncFromLocation);
    return () => window.removeEventListener("popstate", syncFromLocation);
  }, []);

  const loadTracking = useCallback(
    (cancelledRef?: { cancelled: boolean }) => {
      setTrackingLoading(true);
      return getStockNewsTracking(supabase, page)
        .then((nextData) => {
          if (cancelledRef?.cancelled) return;
          setData(nextData);
          setError(null);
        })
        .catch((err) => {
          if (cancelledRef?.cancelled) return;
          setData(null);
          setError(err instanceof Error ? err.message : "新闻追踪加载失败");
        })
        .finally(() => {
          if (!cancelledRef?.cancelled) setTrackingLoading(false);
        });
    },
    [page, supabase],
  );

  useEffect(() => {
    if (loading) return;
    const cancelledRef = { cancelled: false };
    Promise.resolve().then(() => loadTracking(cancelledRef));
    return () => {
      cancelledRef.cancelled = true;
    };
  }, [loadTracking, loading]);

  function goToPage(nextPage: number) {
    setPage(nextPage);
    window.history.pushState(null, "", buildTrackingUrl(nextPage));
  }

  async function deleteStock(stock: StockNewsTrackingStock) {
    if (!profile?.isAdmin || deletingStockId || deletingTrackingId) return;
    const ok = window.confirm(`删除 ${stock.displayName} 与这条新闻的映射？`);
    if (!ok) return;
    setDeletingStockId(stock.id);
    try {
      await deleteStockNewsTrackingStock(supabase, stock.id);
      await loadTracking();
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除映射股票失败");
    } finally {
      setDeletingStockId(null);
    }
  }

  async function deleteTrackingItem(item: StockNewsTrackingItem) {
    if (!profile?.isAdmin || deletingTrackingId || deletingStockId) return;
    const headline = asText(item.eventSnapshot.headline, item.eventKey);
    const ok = window.confirm(`删除整条追踪新闻“${headline}”？这会同时删除该新闻下的全部映射股票。`);
    if (!ok) return;
    setDeletingTrackingId(item.id);
    try {
      await deleteStockNewsTrackingItem(supabase, item.id);
      await loadTracking();
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除追踪新闻失败");
    } finally {
      setDeletingTrackingId(null);
    }
  }

  if (loading) return <LoadingPanel />;

  const rows = data?.tracking.rows ?? [];
  const canGoPrev = (data?.tracking.page ?? 1) > 1;
  const canGoNext = (data?.tracking.page ?? 1) < (data?.tracking.totalPages ?? 1);

  return (
    <main className="page space-y-6">
      <PageHeader
        eyebrow="Tracked News"
        title="新闻（追踪）"
        description="把管理员选中的新闻映射到可能受益股票，并跟踪入选后的价格表现。"
        badges={
          <>
            <Badge variant="warm">AI 映射</Badge>
            <Badge variant="neutral">北京时间 08:00 / 20:00 刷新</Badge>
          </>
        }
      />

      <Card>
        <CardHeader className="gap-4 sm:flex sm:flex-row sm:items-end sm:justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 text-2xl">
              <Sparkles className="h-5 w-5" />
              追踪表
            </CardTitle>
            <CardDescription>
              当前页 {formatCount(data?.tracking.page ?? 1)} / {formatCount(data?.tracking.totalPages ?? 1)}，
              共 {formatCount(data?.tracking.total ?? 0)} 条追踪新闻。
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Button type="button" variant="secondary" disabled={!canGoPrev} onClick={() => goToPage(Math.max(1, page - 1))}>
              上一页
            </Button>
            <Button type="button" variant="secondary" disabled={!canGoNext} onClick={() => goToPage(page + 1)}>
              下一页
            </Button>
          </div>
        </CardHeader>
      </Card>

      {error ? <div className="empty field-error">{error}</div> : null}
      {trackingLoading ? (
        <div className="rounded-2xl border border-[color:var(--border)] bg-[color:var(--paper-strong)]/70 px-4 py-3 text-sm font-medium text-[color:var(--muted-ink)]">
          正在更新追踪表
        </div>
      ) : null}

      {!trackingLoading && rows.length === 0 ? (
        <EmptyState title="还没有追踪新闻" description="管理员在新闻页选择追踪后，这里会展示 AI 映射股票和涨幅。" />
      ) : null}

      {!trackingLoading && rows.length > 0 ? (
        <Card>
          <CardContent className="p-0">
            <table>
              <thead>
                <tr>
                  <th>新闻</th>
                  <th>映射股票</th>
                  <th>逻辑</th>
                  <th>3日涨幅</th>
                  <th>7日涨幅</th>
                  <th>入选后至今</th>
                  {profile?.isAdmin ? <th>操作</th> : null}
                </tr>
              </thead>
              <tbody>
                {rows.map((item) => {
                  const stocks = item.stocks.length ? item.stocks : [null];
                  return stocks.map((stock, index) => (
                    <tr key={`${item.id}-${stock?.id ?? "empty"}-${index}`}>
                      {index === 0 ? (
                        <td rowSpan={stocks.length} className="align-top">
                          <div className="space-y-3">
                            <NewsCell item={item} />
                            {profile?.isAdmin ? (
                              <Button
                                type="button"
                                variant="destructive"
                                size="sm"
                                disabled={deletingTrackingId === item.id}
                                onClick={() => deleteTrackingItem(item)}
                                title="删除整条追踪新闻"
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                                {deletingTrackingId === item.id ? "删除中" : "删除新闻"}
                              </Button>
                            ) : null}
                          </div>
                        </td>
                      ) : null}
                      {stock ? (
                        <>
                          <td>
                            <div className="account-cell">
                              <strong>{stock.displayName}</strong>
                              <span className="muted">{stockLabel(stock)}</span>
                              {stock.countryOrRegion ? <span className="muted">{stock.countryOrRegion}</span> : null}
                              {stock.benefitLayer || stock.coreLink ? (
                                <span className="muted">{[stock.benefitLayer, stock.coreLink].filter(Boolean).join(" / ")}</span>
                              ) : null}
                            </div>
                          </td>
                          <td className="max-w-[480px] text-sm leading-6 text-[color:var(--muted-ink)]">{stock.benefitLogic}</td>
                          <td className={returnClass(stock.return3d)}>{horizonLabel(stock.horizon3Status, stock.return3d)}</td>
                          <td className={returnClass(stock.return7d)}>{horizonLabel(stock.horizon7Status, stock.return7d)}</td>
                          <td>
                            <div className="account-cell">
                              <strong className={returnClass(stock.returnSinceSelected)}>{formatPercent(stock.returnSinceSelected)}</strong>
                              <span className="muted">
                                {stock.latestDate ? `截至 ${stock.latestDate}` : stock.priceStatus === "missing_price" ? "缺行情" : "等待行情"}
                              </span>
                              {stock.lastPriceCheckedAt ? (
                                <span className="inline-flex items-center gap-1 text-xs text-[color:var(--soft-ink)]">
                                  <RefreshCw className="h-3 w-3" />
                                  {formatShanghaiDateTime(stock.lastPriceCheckedAt)}
                                </span>
                              ) : null}
                            </div>
                          </td>
                          {profile?.isAdmin ? (
                            <td>
                              <Button
                                type="button"
                                variant="destructive"
                                size="sm"
                                disabled={deletingStockId === stock.id}
                                onClick={() => deleteStock(stock)}
                                title="删除这条映射股票"
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                                {deletingStockId === stock.id ? "删除中" : "删除"}
                              </Button>
                            </td>
                          ) : null}
                        </>
                      ) : (
                        <td colSpan={profile?.isAdmin ? 6 : 5} className="text-sm text-[color:var(--soft-ink)]">
                          {item.status === "failed" ? "分析失败，暂无股票映射。" : "等待 AI 分析生成股票映射。"}
                        </td>
                      )}
                    </tr>
                  ));
                })}
              </tbody>
            </table>
          </CardContent>
        </Card>
      ) : null}
    </main>
  );
}
