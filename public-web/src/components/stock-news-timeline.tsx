"use client";

import Link from "next/link";
import { AlertTriangle, ExternalLink, Newspaper } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import { EmptyState } from "@/components/empty-state";
import { LoadingPanel } from "@/components/page-states";
import { SignInCta } from "@/components/signin-cta";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page";
import { useAuth } from "@/lib/auth-context";
import { getVisibleStockNewsTimeline } from "@/lib/direct-data";
import { cn, formatCount, formatShanghaiDateTime } from "@/lib/utils";
import type { StockNewsTimelineResponse } from "@/lib/types";

function parsePage(value: string | null) {
  const parsed = Number.parseInt(value || "1", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

function buildNewsUrl(page: number) {
  if (page <= 1) return "/stocks/news";
  return `/stocks/news?page=${page}`;
}

function eventTypeLabel(value: string) {
  const mapping: Record<string, string> = {
    earnings_update: "业绩更新",
    guidance_update: "指引更新",
    management_commentary: "管理层表述",
    product_update: "产品更新",
    policy_update: "政策更新",
    supply_chain_update: "供应链更新",
    supply_risk: "供应风险",
    profitability_outlook: "盈利预期",
    analyst_report: "分析师报告",
    exclusive_report: "独家报道",
    data_point: "数据播报",
    rumor: "传闻",
    other: "其他",
  };
  return mapping[value] || value || "其他";
}

function isSupplyRisk(value: string) {
  return value === "supply_risk";
}

function eventNatureLabel(value: string) {
  const mapping: Record<string, string> = {
    reported: "报道",
    announced: "公告",
    exclusive: "独家",
    quoted: "引述",
    expected: "预期",
    rumored: "传闻",
    other: "其他",
  };
  return mapping[value] || value || "报道";
}

function entityTypeLabel(value: "stock" | "theme") {
  return value === "stock" ? "股票" : "主题";
}

export function StockNewsTimeline() {
  const searchParams = useSearchParams();
  const { loading, profile, signIn, supabase } = useAuth();
  const [page, setPage] = useState(() => parsePage(searchParams.get("page")));
  const [data, setData] = useState<StockNewsTimelineResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [timelineLoading, setTimelineLoading] = useState(true);

  useEffect(() => {
    function syncFromLocation() {
      const next = new URLSearchParams(window.location.search);
      setPage(parsePage(next.get("page")));
    }
    window.addEventListener("popstate", syncFromLocation);
    return () => window.removeEventListener("popstate", syncFromLocation);
  }, []);

  useEffect(() => {
    if (loading) return;
    let cancelled = false;
    Promise.resolve().then(() => {
      if (!cancelled) setTimelineLoading(true);
    });
    getVisibleStockNewsTimeline(supabase, profile, page)
      .then((nextData) => {
        if (cancelled) return;
        setData(nextData);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setData(null);
        setError(err instanceof Error ? err.message : "新闻时间线加载失败");
      })
      .finally(() => {
        if (!cancelled) setTimelineLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [loading, page, profile, supabase]);

  function goToPage(nextPage: number) {
    setPage(nextPage);
    window.history.pushState(null, "", buildNewsUrl(nextPage));
  }

  if (loading) return <LoadingPanel />;

  const rows = data?.timeline.rows ?? [];
  const canGoPrev = (data?.timeline.page ?? 1) > 1;
  const canGoNext = (data?.timeline.page ?? 1) < (data?.timeline.totalPages ?? 1);

  return (
    <main className="page space-y-6">
      <PageHeader
        eyebrow="Stock News"
        title="新闻"
        description="按日期回看股票与主题相关的客观新闻、事件、公告、引述和非行情类数据播报。这里不混入作者观点，也不推导买卖方向。"
        badges={
          <>
            <Badge variant="warm">股票板块</Badge>
            <Badge variant="danger">供应风险优先</Badge>
            <Badge variant="neutral">{profile ? "完整模式" : "公开预览"}</Badge>
          </>
        }
      />

      {!profile ? <SignInCta onLogin={signIn} compact /> : null}

      <Card>
        <CardHeader className="gap-4 sm:flex sm:flex-row sm:items-end sm:justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 text-2xl">
              <Newspaper className="h-5 w-5" />
              按日期查看新闻流
            </CardTitle>
            <CardDescription>
              当前页 {formatCount(data?.timeline.page ?? 1)} / {formatCount(data?.timeline.totalPages ?? 1)}，
              共 {formatCount(data?.timeline.total ?? 0)} 个日期分组。
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
      {timelineLoading ? (
        <div className="rounded-2xl border border-[color:var(--border)] bg-[color:var(--paper-strong)]/70 px-4 py-3 text-sm font-medium text-[color:var(--muted-ink)]">
          正在更新新闻时间线
        </div>
      ) : null}

      {!timelineLoading && rows.length === 0 ? (
        <EmptyState title="还没有可见新闻记录" description="完成重分析和物化后，这里会按日期展示新闻事件时间线。" />
      ) : null}

      {!timelineLoading && rows.length > 0 ? (
        <div className="space-y-4">
          {rows.map((day) => (
            <Card key={day.date}>
              <CardHeader className="gap-3 border-b border-[color:var(--border)] bg-[color:var(--paper-strong)]/60">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <CardTitle className="text-2xl">{day.date}</CardTitle>
                    <CardDescription>当天共有 {formatCount(day.eventCount)} 条新闻事件</CardDescription>
                  </div>
                  <Badge variant="neutral">更新于 {formatShanghaiDateTime(day.updatedAt)}</Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-4 pt-6">
                {day.events.map((event, index) => (
                  <article
                    key={`${day.date}-${event.noteId}-${index}`}
                    className={cn(
                      "space-y-2 border-b border-[color:var(--border)]/70 py-3 last:border-b-0 last:pb-0 first:pt-0",
                      isSupplyRisk(event.eventType) &&
                        "rounded-lg border border-[color:rgba(212,67,67,0.28)] bg-[color:rgba(212,67,67,0.06)] px-3 py-3 last:border-b first:pt-3",
                    )}
                  >
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-[color:var(--soft-ink)] sm:text-sm">
                      {isSupplyRisk(event.eventType) ? <AlertTriangle className="h-4 w-4 text-[color:var(--danger)]" /> : null}
                      <span>{formatShanghaiDateTime(event.publishTime)}</span>
                      <span>{event.authorNickname || event.accountName}</span>
                      {event.noteUrl ? (
                        <Link href={event.noteUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[color:var(--accent-strong)] hover:underline">
                          查看原文
                          <ExternalLink className="h-3.5 w-3.5" />
                        </Link>
                      ) : null}
                      <Badge variant={isSupplyRisk(event.eventType) ? "danger" : "neutral"}>{eventTypeLabel(event.eventType)}</Badge>
                      <Badge variant="warm">{eventNatureLabel(event.eventNature)}</Badge>
                      {event.linkedEntities.map((entity) => (
                        <Badge key={`${event.noteId}-${entity.entityType}-${entity.entityKey}`} variant="neutral">
                          {entityTypeLabel(entity.entityType)} · {entity.entityName}
                        </Badge>
                      ))}
                    </div>
                    <p className="text-sm leading-6 text-[color:var(--muted-ink)] sm:text-[15px]">
                      <span className="font-semibold text-[color:var(--ink)]">{event.headline}</span>
                      {event.eventSummary ? <span className="ml-2">{event.eventSummary}</span> : null}
                    </p>
                  </article>
                ))}
              </CardContent>
            </Card>
          ))}
        </div>
      ) : null}
    </main>
  );
}
