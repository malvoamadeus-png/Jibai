"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { PanelLeftClose, PanelLeftOpen, Search } from "lucide-react";

import { InsightListCard } from "@/components/insight-list-card";
import { LoadingPanel } from "@/components/page-states";
import { SignInCta } from "@/components/signin-cta";
import { StockDayCard } from "@/components/stock-day-card";
import { StockKlineCard } from "@/components/stock-kline-card";
import { ThemeDayCard } from "@/components/theme-day-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth-context";
import { getVisibleEntityTimeline, listEntities } from "@/lib/direct-data";
import type { EntityDetailData, EntityListItem, StockKlineData } from "@/lib/types";

function parsePage(value: string | null) {
  const parsed = Number.parseInt(value || "1", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

function buildChart(detail: EntityDetailData): StockKlineData {
  const fallbackMarkers = detail.timeline.rows
    .map((day) => ({
      date: day.date,
      mentionCount: day.mentionCount,
      authorViews: day.authorViews,
    }))
    .sort((left, right) => left.date.localeCompare(right.date));

  if (detail.chart) {
    return {
      ...detail.chart,
      markers: detail.chart.markers.length ? detail.chart.markers : fallbackMarkers,
    };
  }

  return {
    sourceLabel: null,
    message: "Market data is temporarily unavailable; the viewpoint timeline is still shown.",
    candles: [],
    markers: fallbackMarkers,
  };
}

export function EntityBrowser({
  type,
}: {
  type: "stock" | "theme";
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { loading, profile, signIn, supabase } = useAuth();
  const [query, setQuery] = useState(searchParams.get("q") || "");
  const [items, setItems] = useState<EntityListItem[]>([]);
  const [detail, setDetail] = useState<EntityDetailData | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const page = parsePage(searchParams.get("page"));
  const paramName = type === "stock" ? "stock" : "theme";
  const requestedKey = searchParams.get(paramName);
  const activeKey = useMemo(() => {
    if (requestedKey && items.some((item) => item.key === requestedKey)) return requestedKey;
    return items[0]?.key || "";
  }, [items, requestedKey]);
  const title = type === "stock" ? "按股票看观点时间线" : "按 Theme 看观点时间线";
  const description =
    type === "stock"
      ? "左侧快速切换股票，右侧查看日线标记和按日作者观点。"
      : "左侧快速切换 Theme，右侧查看同一主题下的按日作者观点。";

  useEffect(() => {
    if (loading) return;
    let cancelled = false;
    Promise.resolve().then(() => {
      if (!cancelled) setListLoading(true);
    });
    listEntities(supabase, type, profile, searchParams.get("q") || "")
      .then((rows) => {
        if (cancelled) return;
        setItems(rows);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "列表加载失败");
        setItems([]);
      })
      .finally(() => {
        if (!cancelled) setListLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [loading, profile, searchParams, supabase, type]);

  useEffect(() => {
    if (loading || !activeKey) {
      let cancelled = false;
      Promise.resolve().then(() => {
        if (!cancelled) setDetail(null);
      });
      return () => {
        cancelled = true;
      };
    }
    let cancelled = false;
    Promise.resolve().then(() => {
      if (!cancelled) setDetailLoading(true);
    });
    getVisibleEntityTimeline(supabase, profile, type, activeKey, page)
      .then((nextDetail) => {
        if (cancelled) return;
        setDetail(nextDetail);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "时间线加载失败");
        setDetail(null);
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeKey, loading, page, profile, supabase, type]);

  function selectItem(key: string) {
    const next = new URLSearchParams(searchParams);
    next.set(paramName, key);
    next.delete("page");
    router.push(`/${type === "stock" ? "stocks" : "themes"}?${next.toString()}`);
    setPanelOpen(false);
  }

  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const next = new URLSearchParams(searchParams);
    if (query.trim()) next.set("q", query.trim());
    else next.delete("q");
    next.delete(paramName);
    next.delete("page");
    const path = type === "stock" ? "/stocks" : "/themes";
    router.push(next.toString() ? `${path}?${next.toString()}` : path);
  }

  if (loading) return <LoadingPanel />;

  return (
    <main className="page space-y-6">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="warm">{type === "stock" ? "按股票" : "按 Theme"}</Badge>
            {!profile ? <Badge variant="neutral">公开预览 · 仅 1 条</Badge> : null}
          </div>
          <CardTitle className="text-3xl">{title}</CardTitle>
          <CardDescription>{description}</CardDescription>
        </CardHeader>
      </Card>

      {!profile ? <SignInCta onLogin={signIn} compact /> : null}

      <div className="lg:hidden">
        <Button type="button" variant="secondary" onClick={() => setPanelOpen((current) => !current)}>
          {panelOpen ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeftOpen className="h-4 w-4" />}
          {panelOpen ? "收起切换列表" : "展开切换列表"}
        </Button>
      </div>

      <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)] xl:grid-cols-[336px_minmax(0,1fr)]">
        <aside className={panelOpen ? "block" : "hidden lg:block"}>
          <Card className="overflow-hidden lg:sticky lg:top-4">
            <CardHeader className="space-y-4 border-b border-[color:var(--border)] bg-[color:var(--paper-strong)]/60">
              <div>
                <CardTitle className="text-xl">快速切换</CardTitle>
                <CardDescription>{profile ? "按你的订阅过滤" : "公开轻量预览"}</CardDescription>
              </div>
              <form className="space-y-3" onSubmit={search}>
                <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={type === "stock" ? "搜索股票" : "搜索 Theme"} />
                <Button type="submit" className="w-full">
                  <Search className="h-4 w-4" />
                  更新列表
                </Button>
              </form>
            </CardHeader>
            <CardContent className="space-y-3 p-4">
              {listLoading ? <div className="empty">列表加载中</div> : null}
              {!listLoading && items.map((item) => (
                <InsightListCard
                  key={item.key}
                  type="entity"
                  item={item}
                  active={item.key === activeKey}
                  onSelect={() => selectItem(item.key)}
                />
              ))}
              {!listLoading && items.length === 0 ? (
                <div className="empty">{profile ? "暂无订阅范围内的数据" : "暂无公开预览数据"}</div>
              ) : null}
            </CardContent>
          </Card>
        </aside>

        <section className="min-w-0 space-y-4">
          {error ? <div className="empty field-error">{error}</div> : null}
          {detailLoading ? <div className="empty">时间线加载中</div> : null}
          {!detailLoading && detail ? (
            <>
              <Card>
                <CardHeader className="gap-4">
                  <div className="flex flex-wrap items-center gap-2">
                    {detail.ticker ? <Badge variant="warm">{detail.ticker}</Badge> : null}
                    {detail.market ? <Badge variant="neutral">{detail.market}</Badge> : null}
                    <Badge variant="neutral">{detail.key}</Badge>
                  </div>
                  <CardTitle className="text-3xl">{detail.displayName}</CardTitle>
                </CardHeader>
              </Card>

              {type === "stock" && profile ? (
                <StockKlineCard
                  displayName={detail.displayName}
                  chart={buildChart(detail)}
                  identity={{
                    securityKey: detail.key,
                    ticker: detail.ticker,
                    market: detail.market,
                  }}
                />
              ) : null}

              {detail.timeline.rows.length ? (
                <div className="space-y-4">
                  {detail.timeline.rows.map((day) =>
                    type === "stock" ? (
                      <StockDayCard key={`${detail.key}-${day.date}`} day={day} />
                    ) : (
                      <ThemeDayCard key={`${detail.key}-${day.date}`} day={day} />
                    ),
                  )}
                </div>
              ) : (
                <div className="empty">暂无时间线记录</div>
              )}
            </>
          ) : null}
          {!profile && detail ? <SignInCta onLogin={signIn} /> : null}
        </section>
      </div>
    </main>
  );
}
