"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ArrowDown, ArrowUp, CalendarDays, Hash, PanelLeftClose, PanelLeftOpen, Search } from "lucide-react";

import { InsightListCard } from "@/components/insight-list-card";
import { LoadingPanel } from "@/components/page-states";
import { SignInCta } from "@/components/signin-cta";
import { StockDayCard } from "@/components/stock-day-card";
import { StockKlineCard } from "@/components/stock-kline-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth-context";
import { getVisibleEntityTimeline, listEntities } from "@/lib/direct-data";
import type { EntityDetailData, EntityListItem, EntitySortKey, StockKlineData } from "@/lib/types";

function parsePage(value: string | null) {
  const parsed = Number.parseInt(value || "1", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

const SORT_OPTIONS: Array<{
  key: EntitySortKey;
  label: string;
  icon: "date" | "count";
  direction: "desc" | "asc";
}> = [
  { key: "date_desc", label: "最近日期", icon: "date", direction: "desc" },
  { key: "date_asc", label: "最近日期", icon: "date", direction: "asc" },
  { key: "count_desc", label: "累计提及", icon: "count", direction: "desc" },
  { key: "count_asc", label: "累计提及", icon: "count", direction: "asc" },
];

function parseSort(value: string | null): EntitySortKey {
  return SORT_OPTIONS.some((item) => item.key === value) ? (value as EntitySortKey) : "date_desc";
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
  domain = "stock",
}: {
  type: "stock" | "crypto";
  domain?: "stock" | "crypto";
}) {
  const searchParams = useSearchParams();
  const { loading, profile, signIn, supabase, authAvailable } = useAuth();
  const isCrypto = domain === "crypto" || type === "crypto";
  const paramName = isCrypto ? "asset" : "stock";
  const [query, setQuery] = useState(searchParams.get("q") || "");
  const [listQuery, setListQuery] = useState(searchParams.get("q") || "");
  const [selectedKey, setSelectedKey] = useState(searchParams.get(paramName) || "");
  const [page, setPage] = useState(() => parsePage(searchParams.get("page")));
  const [sort, setSort] = useState<EntitySortKey>(() => parseSort(searchParams.get("sort")));
  const [items, setItems] = useState<EntityListItem[]>([]);
  const [detail, setDetail] = useState<EntityDetailData | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const activeSort = SORT_OPTIONS.find((item) => item.key === sort) || SORT_OPTIONS[0];
  const activeKey = useMemo(() => {
    if (selectedKey && items.some((item) => item.key === selectedKey)) return selectedKey;
    return items[0]?.key || "";
  }, [items, selectedKey]);
  const basePath = isCrypto ? "/crypto/assets" : "/stocks";
  const title = isCrypto ? "按标的（详情）" : "按股票（详情）";
  const description = isCrypto ? "左侧快速切换项目或资产，右侧查看按日作者信号、原文标识、逻辑和来源。" : "左侧快速切换股票，右侧查看日线标记和按日作者观点。";
  const adminView = Boolean(profile?.isAdmin);
  const listScopeLabel = adminView ? "管理员全量视图" : profile ? "按你的订阅过滤" : "公开轻量预览";
  const emptyListHint = adminView
    ? isCrypto
      ? "管理员视图下暂时还没有可见标的观点数据。"
      : "管理员视图下暂时还没有可见股票观点数据。"
    : profile
      ? isCrypto
        ? "当前账号的订阅范围内还没有可见标的观点数据。通常是因为还没订阅任何账号，或已订阅账号暂时没有有效观点。"
        : "当前账号的订阅范围内还没有可见股票观点数据。通常是因为还没订阅任何账号，或已订阅账号暂时没有有效观点。"
      : "暂无公开预览数据";
  const cryptoIdentifierBadges = useMemo(() => {
    if (!isCrypto || !detail) return [];
    const badges: string[] = [];
    if (detail.normalizedStatus && detail.normalizedStatus !== "canonical") badges.push("临时归一");
    if (detail.identifierType) badges.push(`主标识 · ${detail.identifierType}`);
    return badges;
  }, [detail, isCrypto]);

  useEffect(() => {
    if (loading) return;
    let cancelled = false;
    Promise.resolve().then(() => {
      if (!cancelled) setListLoading(true);
    });
    listEntities(supabase, type, profile, listQuery, 100, sort)
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
  }, [listQuery, loading, profile, sort, supabase, type]);

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

  useEffect(() => {
    function syncFromLocation() {
      const next = new URLSearchParams(window.location.search);
      setQuery(next.get("q") || "");
      setListQuery(next.get("q") || "");
      setSelectedKey(next.get(paramName) || "");
      setPage(parsePage(next.get("page")));
      setSort(parseSort(next.get("sort")));
    }

    window.addEventListener("popstate", syncFromLocation);
    return () => window.removeEventListener("popstate", syncFromLocation);
  }, [paramName]);

  function buildEntityUrl(nextQuery: string, key: string, nextPage: number, nextSort: EntitySortKey) {
    const next = new URLSearchParams();
    if (nextQuery) next.set("q", nextQuery);
    if (key) next.set(paramName, key);
    if (nextPage > 1) next.set("page", String(nextPage));
    if (nextSort !== "date_desc") next.set("sort", nextSort);
    const params = next.toString();
    return params ? `${basePath}?${params}` : basePath;
  }

  function selectItem(key: string) {
    setSelectedKey(key);
    setPage(1);
    window.history.pushState(null, "", buildEntityUrl(listQuery, key, 1, sort));
    setPanelOpen(false);
  }

  function selectSort(nextSort: EntitySortKey) {
    setSort(nextSort);
    setPage(1);
    window.history.pushState(null, "", buildEntityUrl(listQuery, selectedKey, 1, nextSort));
  }

  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextQuery = query.trim();
    setListQuery(nextQuery);
    setSelectedKey("");
    setPage(1);
    window.history.pushState(null, "", buildEntityUrl(nextQuery, "", 1, sort));
  }

  if (loading) return <LoadingPanel />;

  return (
    <main className="page space-y-6 lg:flex lg:h-[calc(100vh-40px)] lg:flex-col lg:overflow-hidden lg:pb-0">
      <Card className="lg:shrink-0">
        <CardHeader className="lg:py-5">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="warm">{title}</Badge>
            {!profile ? <Badge variant="neutral">公开预览 · 仅 1 条</Badge> : null}
          </div>
          <CardTitle className="text-3xl">{title}</CardTitle>
          <CardDescription>{description}</CardDescription>
        </CardHeader>
      </Card>

      {!profile ? <SignInCta onLogin={signIn} compact authAvailable={authAvailable} /> : null}

      <div className="lg:hidden">
        <Button type="button" variant="secondary" onClick={() => setPanelOpen((current) => !current)}>
          {panelOpen ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeftOpen className="h-4 w-4" />}
          {panelOpen ? "收起切换列表" : "展开切换列表"}
        </Button>
      </div>

      <div className="grid gap-6 lg:min-h-0 lg:flex-1 lg:grid-cols-[320px_minmax(0,1fr)] xl:grid-cols-[336px_minmax(0,1fr)]">
        <aside className={panelOpen ? "block lg:min-h-0" : "hidden lg:block lg:min-h-0"}>
          <Card className="h-full overflow-hidden lg:flex lg:flex-col">
            <CardHeader className="shrink-0 space-y-4 border-b border-[color:var(--border)] bg-[color:var(--paper-strong)]/60">
              <div>
                <CardTitle className="text-xl">快速切换</CardTitle>
                <CardDescription>{listScopeLabel}</CardDescription>
              </div>
              <form className="space-y-3" onSubmit={search}>
                <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={isCrypto ? "搜索标的" : "搜索股票"} />
                <Button type="submit" className="w-full">
                  <Search className="h-4 w-4" />
                  更新列表
                </Button>
              </form>
              <div className="grid grid-cols-2 gap-2">
                {SORT_OPTIONS.map((option) => {
                  const SortIcon = option.icon === "date" ? CalendarDays : Hash;
                  const DirectionIcon = option.direction === "desc" ? ArrowDown : ArrowUp;
                  return (
                    <Button
                      key={option.key}
                      type="button"
                      variant={option.key === activeSort.key ? "primary" : "secondary"}
                      className="min-w-0 justify-center px-2 text-xs"
                      aria-pressed={option.key === activeSort.key}
                      title={`${option.label}${option.direction === "desc" ? "倒序" : "正序"}`}
                      onClick={() => selectSort(option.key)}
                    >
                      <SortIcon className="h-3.5 w-3.5" />
                      <span className="truncate">{option.label}</span>
                      <DirectionIcon className="h-3.5 w-3.5" />
                    </Button>
                  );
                })}
              </div>
            </CardHeader>
            <CardContent className="min-h-0 space-y-3 overflow-y-auto overscroll-contain p-4 lg:flex-1">
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
                <div className="empty space-y-2">
                  <div>{emptyListHint}</div>
                  {profile && !adminView ? (
                    <div className="text-sm text-[color:var(--muted-ink)]">
                      去
                      {" "}
                      <Link
                        href={isCrypto ? "/crypto/accounts" : "/accounts"}
                        className="underline underline-offset-4 hover:text-[color:var(--accent-strong)]"
                      >
                        账号库
                      </Link>
                      {" "}
                      订阅后，这里才会显示详情时间线。
                    </div>
                  ) : null}
                </div>
              ) : null}
            </CardContent>
          </Card>
        </aside>

        <section className="min-w-0 space-y-4 lg:min-h-0 lg:overflow-y-auto lg:overscroll-contain lg:pr-1">
          {error ? <div className="empty field-error">{error}</div> : null}
          {detailLoading ? <div className="empty">时间线加载中</div> : null}
          {!detailLoading && detail ? (
            <>
              <Card>
                <CardHeader className="gap-4">
                  <div className="flex flex-wrap items-center gap-2">
                    {detail.ticker ? <Badge variant="warm">{detail.ticker}</Badge> : null}
                    {detail.market ? <Badge variant="neutral">{detail.market}</Badge> : null}
                    {cryptoIdentifierBadges.map((badge) => (
                      <Badge key={badge} variant="neutral">
                        {badge}
                      </Badge>
                    ))}
                    <Badge variant="neutral">{detail.key}</Badge>
                  </div>
                  <CardTitle className="text-3xl">{detail.displayName}</CardTitle>
                  {isCrypto && detail.rawIdentifiers?.length ? (
                    <CardDescription>原始标识：{detail.rawIdentifiers.join(" · ")}</CardDescription>
                  ) : null}
                </CardHeader>
              </Card>

              {!isCrypto && profile ? (
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
                  {detail.timeline.rows.map((day) => (
                    <StockDayCard key={`${detail.key}-${day.date}`} day={day} domain={isCrypto ? "crypto" : "stock"} />
                  ))}
                </div>
              ) : (
                <div className="empty">暂无时间线记录</div>
              )}
            </>
          ) : null}
          {!profile && detail ? <SignInCta onLogin={signIn} authAvailable={authAvailable} /> : null}
        </section>
      </div>
    </main>
  );
}
