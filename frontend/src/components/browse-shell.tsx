"use client";

import type { FormEvent, ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
} from "lucide-react";

import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type {
  AuthorListItem,
  PagedResult,
  StockListItem,
  ThemeListItem,
} from "@/lib/types";
import { cn, formatCount, formatDate, parsePositiveInt, platformLabel } from "@/lib/utils";

type BrowseResource = "authors" | "stocks" | "themes";

type BrowseShellProps = {
  resource: BrowseResource;
  children: ReactNode;
};

type BrowseItem = {
  key: string;
  title: string;
  subtitle: string;
  eyebrow?: string;
  status?: string | null;
  updatedAt?: string | null;
  metrics: Array<{
    label: string;
    value: string;
  }>;
};

type BrowseConfig = {
  basePath: string;
  apiPath: string;
  title: string;
  description: string;
  emptyTitle: string;
  emptyDescription: string;
  searchPlaceholder: string;
  secondarySearchPlaceholder?: string;
};

type SearchParamReader = {
  get(name: string): string | null;
};

const BROWSE_CONFIG: Record<BrowseResource, BrowseConfig> = {
  authors: {
    basePath: "/authors",
    apiPath: "/api/local/authors",
    title: "按人看观点时间线",
    description: "左侧筛人，右侧直接切换这位作者的观点时间线。",
    emptyTitle: "暂无作者时间线",
    emptyDescription: "先完成一次抓取和分析，这里才会出现可切换的作者清单。",
    searchPlaceholder: "搜索账号名或显示名",
    secondarySearchPlaceholder: "平台，如 x / xiaohongshu",
  },
  stocks: {
    basePath: "/stocks",
    apiPath: "/api/local/stocks",
    title: "按股票看观点时间线",
    description: "左侧快速切换标的，右侧查看价格与观点时间线。",
    emptyTitle: "暂无股票时间线",
    emptyDescription: "先完成一次抓取和分析，这里才会出现股票时间线。",
    searchPlaceholder: "搜索股票名、ticker 或别名",
  },
  themes: {
    basePath: "/themes",
    apiPath: "/api/local/themes",
    title: "按 Theme 看观点时间线",
    description: "左侧快速切换主题，右侧查看同一主题下的观点变化。",
    emptyTitle: "暂无 Theme 时间线",
    emptyDescription: "先完成一次抓取和分析，这里才会出现 Theme 时间线。",
    searchPlaceholder: "搜索 Theme 名称",
  },
};

function normalizeListParams(resource: BrowseResource, searchParams: SearchParamReader) {
  return {
    q: searchParams.get("q") ?? "",
    platform: resource === "authors" ? searchParams.get("platform") ?? "" : "",
    listPage: parsePositiveInt(searchParams.get("listPage") ?? undefined, 1, 1, 9999),
  };
}

function buildListSearch(params: { q: string; platform?: string; listPage: number }) {
  const next = new URLSearchParams();
  const q = params.q.trim();
  const platform = params.platform?.trim() ?? "";

  if (q) next.set("q", q);
  if (platform) next.set("platform", platform);
  if (params.listPage > 1) next.set("listPage", String(params.listPage));

  return next.toString();
}

function resolveActiveKey(pathname: string, basePath: string) {
  if (!pathname.startsWith(`${basePath}/`)) {
    return null;
  }

  const segment = pathname.slice(basePath.length + 1).split("/")[0];
  return segment ? decodeURIComponent(segment) : null;
}

function mapRowsToItems(
  resource: BrowseResource,
  rows: Array<AuthorListItem | StockListItem | ThemeListItem>,
) {
  if (resource === "authors") {
    return (rows as AuthorListItem[]).map(
      (row): BrowseItem => ({
        key: row.accountKey,
        title: row.authorNickname || row.accountName,
        subtitle: row.accountName,
        eyebrow: platformLabel(row.platform),
        status: row.latestStatus,
        updatedAt: row.updatedAt,
        metrics: [
          { label: "最近日期", value: formatDate(row.latestDate) },
          { label: "记录天数", value: formatCount(row.totalDays) },
          { label: "累计内容", value: formatCount(row.totalNotes) },
        ],
      }),
    );
  }

  if (resource === "stocks") {
    return (rows as StockListItem[]).map(
      (row): BrowseItem => ({
        key: row.securityKey,
        title: row.displayName,
        subtitle:
          [row.ticker, row.market].filter(Boolean).join(" / ") || row.securityKey,
        updatedAt: row.updatedAt,
        metrics: [
          { label: "最近日期", value: formatDate(row.latestDate) },
          { label: "提及天数", value: formatCount(row.mentionDays) },
          { label: "累计提及", value: formatCount(row.totalMentions) },
        ],
      }),
    );
  }

  return (rows as ThemeListItem[]).map(
    (row): BrowseItem => ({
      key: row.themeKey,
      title: row.displayName,
      subtitle: row.themeKey,
      updatedAt: row.updatedAt,
      metrics: [
        { label: "最近日期", value: formatDate(row.latestDate) },
        { label: "提及天数", value: formatCount(row.mentionDays) },
        { label: "累计提及", value: formatCount(row.totalMentions) },
      ],
    }),
  );
}

function BrowseListCard({
  item,
  href,
  active,
  resource,
  onNavigate,
}: {
  item: BrowseItem;
  href: string;
  active: boolean;
  resource: BrowseResource;
  onNavigate: () => void;
}) {
  return (
    <Link
      href={href}
      onClick={onNavigate}
      className={cn(
        "block rounded-[24px] border p-4 transition",
        active
          ? "border-[color:var(--accent)] bg-[color:rgba(181,106,59,0.12)] shadow-[0_14px_32px_rgba(44,33,22,0.08)]"
          : "border-[color:var(--border)] bg-[color:var(--paper)] hover:border-[color:var(--accent)] hover:bg-[color:var(--paper-strong)]",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-1.5">
          {resource === "authors" ? (
            <div className="flex flex-wrap items-center gap-2">
              {item.eyebrow ? (
                <Badge variant="neutral" className="tracking-[0.06em] normal-case">
                  {item.eyebrow}
                </Badge>
              ) : null}
              <StatusBadge status={item.status ?? null} />
            </div>
          ) : null}

          <p className="truncate text-base font-semibold text-[color:var(--ink)]">{item.title}</p>
          <p className="truncate text-sm text-[color:var(--muted-ink)]">{item.subtitle}</p>
        </div>

        {item.updatedAt ? (
          <span className="shrink-0 text-[11px] text-[color:var(--soft-ink)]">
            {formatDate(item.updatedAt)}
          </span>
        ) : null}
      </div>

      <div className="mt-4 grid grid-cols-3 gap-2">
        {item.metrics.map((metric) => (
          <div key={`${item.key}-${metric.label}`} className="rounded-2xl bg-[color:var(--panel)]/65 px-3 py-2">
            <p className="text-[11px] text-[color:var(--soft-ink)]">{metric.label}</p>
            <p className="mt-1 text-sm font-semibold text-[color:var(--ink)]">{metric.value}</p>
          </div>
        ))}
      </div>
    </Link>
  );
}

function LoadingList() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 4 }).map((_, index) => (
        <div
          key={`loading-${index}`}
          className="rounded-[24px] border border-[color:var(--border)] bg-[color:var(--paper)] p-4"
        >
          <div className="h-4 w-24 rounded-full bg-[color:var(--panel)]/80" />
          <div className="mt-3 h-5 w-3/4 rounded-full bg-[color:var(--panel)]/80" />
          <div className="mt-2 h-4 w-1/2 rounded-full bg-[color:var(--panel)]/70" />
          <div className="mt-4 grid grid-cols-3 gap-2">
            {Array.from({ length: 3 }).map((__, metricIndex) => (
              <div
                key={`loading-${index}-${metricIndex}`}
                className="h-[54px] rounded-2xl bg-[color:var(--panel)]/70"
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export function BrowseShell({ resource, children }: BrowseShellProps) {
  const config = BROWSE_CONFIG[resource];
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const currentParams = useMemo(() => normalizeListParams(resource, searchParams), [resource, searchParams]);
  const activeKey = useMemo(
    () => resolveActiveKey(pathname, config.basePath),
    [config.basePath, pathname],
  );

  const [data, setData] = useState<PagedResult<AuthorListItem | StockListItem | ThemeListItem> | null>(
    null,
  );
  const [loadedKey, setLoadedKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const requestKey = useMemo(
    () => `${resource}:${currentParams.q}:${currentParams.platform}:${currentParams.listPage}`,
    [currentParams.listPage, currentParams.platform, currentParams.q, resource],
  );

  useEffect(() => {
    const controller = new AbortController();
    const requestParams = new URLSearchParams({
      page: String(currentParams.listPage),
      pageSize: "20",
    });

    if (currentParams.q) requestParams.set("q", currentParams.q);
    if (resource === "authors" && currentParams.platform) {
      requestParams.set("platform", currentParams.platform);
    }

    void fetch(`${config.apiPath}?${requestParams.toString()}`, {
      cache: "no-store",
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error("列表加载失败");
        }
        return (await response.json()) as PagedResult<AuthorListItem | StockListItem | ThemeListItem>;
      })
      .then((payload) => {
        setData(payload);
        setError(null);
        setLoadedKey(requestKey);
      })
      .catch((fetchError) => {
        if (controller.signal.aborted) {
          return;
        }
        setError(fetchError instanceof Error ? fetchError.message : "列表加载失败");
        setData(null);
        setLoadedKey(requestKey);
      });

    return () => controller.abort();
  }, [
    config.apiPath,
    currentParams.listPage,
    currentParams.platform,
    currentParams.q,
    requestKey,
    resource,
  ]);

  const loading = loadedKey !== requestKey;

  function pushListParams(nextParams: { q: string; platform?: string; listPage: number }) {
    const queryString = buildListSearch(nextParams);
    router.push(queryString ? `${pathname}?${queryString}` : pathname);
  }

  function handleSearchSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);

    pushListParams({
      q: String(formData.get("q") ?? ""),
      platform: resource === "authors" ? String(formData.get("platform") ?? "") : "",
      listPage: 1,
    });
  }

  const listQueryString = useMemo(
    () =>
      buildListSearch({
        q: currentParams.q,
        platform: currentParams.platform,
        listPage: currentParams.listPage,
      }),
    [currentParams.listPage, currentParams.platform, currentParams.q],
  );

  const items = useMemo(
    () => mapRowsToItems(resource, data?.rows ?? []),
    [data?.rows, resource],
  );

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-3xl">{config.title}</CardTitle>
          <CardDescription>{config.description}</CardDescription>
        </CardHeader>
      </Card>

      <div className="space-y-4 lg:hidden">
        <Button type="button" variant="secondary" onClick={() => setPanelOpen((current) => !current)}>
          {panelOpen ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeftOpen className="h-4 w-4" />}
          {panelOpen ? "收起切换清单" : "展开切换清单"}
        </Button>
      </div>

      <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)] xl:grid-cols-[336px_minmax(0,1fr)]">
        <aside className={cn("min-w-0", panelOpen ? "block" : "hidden lg:block")}>
          <Card className="overflow-hidden lg:sticky lg:top-4">
            <CardHeader className="space-y-4 border-b border-[color:var(--border)] bg-[color:var(--paper-strong)]/60">
              <div className="space-y-2">
                <CardTitle className="text-xl">快速切换</CardTitle>
                <CardDescription>筛选后直接切换，不需要回退到一级列表。</CardDescription>
              </div>

              <form
                key={`filters-${resource}-${currentParams.q}-${currentParams.platform}`}
                className="space-y-3"
                onSubmit={handleSearchSubmit}
              >
                <div className={cn("grid gap-3", resource === "authors" ? "sm:grid-cols-2 lg:grid-cols-1" : "")}>
                  <Input
                    name="q"
                    defaultValue={currentParams.q}
                    placeholder={config.searchPlaceholder}
                  />
                  {resource === "authors" && config.secondarySearchPlaceholder ? (
                    <Input
                      name="platform"
                      defaultValue={currentParams.platform}
                      placeholder={config.secondarySearchPlaceholder}
                    />
                  ) : null}
                </div>
                <Button type="submit" className="w-full">
                  <Search className="h-4 w-4" />
                  更新清单
                </Button>
              </form>
            </CardHeader>

            <CardContent className="space-y-4 p-4">
              {loading ? <LoadingList /> : null}

              {!loading && error ? (
                <div className="rounded-[22px] border border-[color:rgba(138,61,61,0.24)] bg-[color:rgba(138,61,61,0.08)] px-4 py-3 text-sm text-[#7d2a2a]">
                  {error}
                </div>
              ) : null}

              {!loading && !error && items.length === 0 ? (
                <div className="rounded-[24px] border border-dashed border-[color:var(--border-strong)] px-4 py-5 text-sm text-[color:var(--muted-ink)]">
                  <p className="font-medium text-[color:var(--ink)]">{config.emptyTitle}</p>
                  <p className="mt-2 leading-6">{config.emptyDescription}</p>
                </div>
              ) : null}

              {!loading && !error && items.length > 0 ? (
                <>
                  <div className="space-y-3">
                    {items.map((item) => (
                      <BrowseListCard
                        key={item.key}
                        item={item}
                        resource={resource}
                        active={item.key === activeKey}
                        href={`${config.basePath}/${encodeURIComponent(item.key)}${listQueryString ? `?${listQueryString}` : ""}`}
                        onNavigate={() => setPanelOpen(false)}
                      />
                    ))}
                  </div>

                  <div className="flex items-center justify-between gap-3 rounded-[22px] border border-[color:var(--border)] bg-[color:var(--panel)]/55 px-3 py-3">
                    <p className="text-sm text-[color:var(--muted-ink)]">
                      第 {data?.page ?? 1} / {data?.totalPages ?? 1} 页
                    </p>
                    <div className="flex items-center gap-2">
                      <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        disabled={!data || data.page <= 1}
                        onClick={() =>
                          pushListParams({
                            q: currentParams.q,
                            platform: currentParams.platform,
                            listPage: Math.max(1, (data?.page ?? 1) - 1),
                          })
                        }
                      >
                        <ChevronLeft className="h-4 w-4" />
                        上一页
                      </Button>
                      <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        disabled={!data || data.page >= data.totalPages}
                        onClick={() =>
                          pushListParams({
                            q: currentParams.q,
                            platform: currentParams.platform,
                            listPage: Math.min(data?.totalPages ?? 1, (data?.page ?? 1) + 1),
                          })
                        }
                      >
                        下一页
                        <ChevronRight className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </>
              ) : null}
            </CardContent>
          </Card>
        </aside>

        <div className="min-w-0">{children}</div>
      </div>
    </div>
  );
}
