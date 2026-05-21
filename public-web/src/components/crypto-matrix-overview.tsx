"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, ArrowRight, ExternalLink, RotateCcw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { DeleteCryptoAssetButton } from "@/components/admin-actions";
import { LoadingPanel } from "@/components/page-states";
import { SignInCta } from "@/components/signin-cta";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/lib/auth-context";
import { getVisibleCryptoMatrix } from "@/lib/direct-data";
import type {
  CryptoMatrixAsset,
  CryptoMatrixCell,
  CryptoMatrixData,
  CryptoMatrixGranularity,
  CryptoMatrixView,
  StockMatrixAuthor,
} from "@/lib/types";
import { cn, formatCount, viewSignalLabel } from "@/lib/utils";

function isDateKey(value: string | null) {
  return Boolean(value && /^\d{4}-\d{2}-\d{2}$/.test(value));
}

function cellKey(assetKey: string, accountName: string) {
  return `${assetKey}::${accountName}`;
}

function buildCellMap(cells: CryptoMatrixCell[]) {
  const map = new Map<string, CryptoMatrixCell>();
  for (const cell of cells) {
    map.set(cellKey(cell.assetKey, cell.accountName), cell);
  }
  return map;
}

function assetLabel(asset: CryptoMatrixAsset) {
  return [asset.ticker, asset.market].filter(Boolean).join(" / ") || asset.assetKey;
}

function assetSummary(asset: CryptoMatrixAsset) {
  return asset.summary.trim() || "暂无说明";
}

function readGranularity(value: string | null): CryptoMatrixGranularity {
  return value === "day" ? "day" : "week";
}

function formatWindowLabel(startDate: string | null, endDate: string | null) {
  if (!startDate || !endDate) return "暂无";
  return startDate === endDate ? startDate : `${startDate} 至 ${endDate}`;
}

function trimEmptyMatrix(data: CryptoMatrixData | null): {
  authors: StockMatrixAuthor[];
  assets: CryptoMatrixAsset[];
  cells: CryptoMatrixCell[];
} | null {
  if (!data) return null;
  const cells = data.cells.filter((cell) => cell.views.length > 0);
  const visibleAuthors = new Set(cells.map((cell) => cell.accountName));
  const visibleAssets = new Set(cells.map((cell) => cell.assetKey));
  return {
    authors: data.authors.filter((author) => visibleAuthors.has(author.accountName)),
    assets: data.assets.filter((asset) => visibleAssets.has(asset.assetKey)),
    cells,
  };
}

function dotClass(view: CryptoMatrixView) {
  if (view.direction === "positive") return "border-[color:rgba(65,122,90,0.42)] bg-[#2f8b57]";
  if (view.direction === "negative") return "border-[color:rgba(138,61,61,0.42)] bg-[#c4483f]";
  return "border-[color:rgba(92,92,92,0.34)] bg-[#8a8a84]";
}

function cryptoViewMetaBadges(view: CryptoMatrixView) {
  const metadata = view.metadata || {};
  const badges: string[] = [];
  if (view.normalized_status && view.normalized_status !== "canonical") badges.push("临时归一");
  if (typeof metadata.resolver_strategy === "string" && metadata.resolver_strategy) {
    badges.push(`归并 · ${metadata.resolver_strategy}`);
  }
  if (typeof metadata.match_confidence === "string" && metadata.match_confidence) {
    badges.push(`置信 · ${metadata.match_confidence}`);
  }
  return badges;
}

function ViewTooltip({ asset, view }: { asset: CryptoMatrixAsset; view: CryptoMatrixView }) {
  const badges = cryptoViewMetaBadges(view);
  return (
    <span className="pointer-events-auto absolute left-1/2 top-5 z-30 hidden w-[min(360px,calc(100vw-48px))] -translate-x-1/2 rounded-2xl border border-[color:var(--border-strong)] bg-[color:var(--paper)] p-4 text-left shadow-[0_18px_50px_rgba(44,33,22,0.18)] group-hover:block group-focus-within:block">
      <span className="mb-2 flex flex-wrap items-center gap-2">
        <Badge
          variant={view.direction === "positive" ? "positive" : view.direction === "negative" ? "danger" : "neutral"}
          className="normal-case"
        >
          {view.date}
        </Badge>
        <Badge variant="neutral" className="normal-case">
          {asset.displayName}
        </Badge>
        {badges.map((badge) => (
          <Badge key={badge} variant="neutral" className="normal-case">
            {badge}
          </Badge>
        ))}
      </span>
      <span className="block text-sm font-semibold text-[color:var(--ink)]">
        {view.author_nickname || view.account_name} · {viewSignalLabel(view)}
      </span>
      <span className="mt-2 block text-xs leading-6 text-[color:var(--muted-ink)]">
        {view.logic || "暂无逻辑说明"}
      </span>
      {view.raw_identifiers?.length ? (
        <span className="mt-2 block text-xs leading-6 text-[color:var(--soft-ink)]">
          标识：{view.raw_identifiers.join(" · ")}
        </span>
      ) : null}
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
              className="inline-flex items-center gap-1 rounded-full border border-[color:var(--border-strong)] px-2 py-1 text-[11px] text-[color:var(--muted-ink)]"
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

function SignalDot({ asset, view }: { asset: CryptoMatrixAsset; view: CryptoMatrixView }) {
  return (
    <span className="group relative inline-flex h-5 w-5 items-center justify-center">
      <button
        type="button"
        className="inline-flex h-5 w-5 items-center justify-center rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--ring)]"
        aria-label={`${asset.displayName} ${view.author_nickname || view.account_name} ${view.date} ${view.direction}`}
      >
        <span className={cn("h-3 w-3 rounded-full border shadow-[0_1px_4px_rgba(44,33,22,0.18)]", dotClass(view))} />
      </button>
      <ViewTooltip asset={asset} view={view} />
    </span>
  );
}

export function CryptoMatrixOverview() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { loading, profile, signIn, supabase } = useAuth();
  const endParam = searchParams.get("end");
  const endDate = isDateKey(endParam) ? endParam : null;
  const granularity = readGranularity(searchParams.get("granularity"));
  const [data, setData] = useState<CryptoMatrixData | null>(null);
  const [matrixLoading, setMatrixLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (loading) return;
    let cancelled = false;
    Promise.resolve().then(() => {
      if (!cancelled) setMatrixLoading(true);
    });
    getVisibleCryptoMatrix(supabase, endDate, granularity)
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
  }, [endDate, granularity, loading, supabase]);

  const matrix = useMemo(() => trimEmptyMatrix(data), [data]);
  const cellMap = useMemo(() => buildCellMap(matrix?.cells ?? []), [matrix]);
  const totalViews = useMemo(
    () => (matrix?.cells ?? []).reduce((sum, cell) => sum + cell.views.length, 0),
    [matrix],
  );
  const windowLabel = useMemo(() => formatWindowLabel(data?.startDate ?? null, data?.endDate ?? null), [data]);
  const windowModeLabel = granularity === "day" ? "按日" : "按周";
  const previousLabel = granularity === "day" ? "上一日" : "上一周";
  const nextLabel = granularity === "day" ? "下一日" : "下一周";
  const emptyLabel = granularity === "day" ? "这个日期没有 crypto 标的信号" : "这个周窗口没有 crypto 标的信号";

  function navigate(nextEndDate: string | null, nextGranularity: CryptoMatrixGranularity = granularity) {
    const next = new URLSearchParams(searchParams);
    if (nextEndDate) next.set("end", nextEndDate);
    else next.delete("end");
    if (nextGranularity === "day") next.set("granularity", "day");
    else next.delete("granularity");
    router.push(next.toString() ? `/crypto/assets/overview?${next.toString()}` : "/crypto/assets/overview");
  }

  if (loading) return <LoadingPanel />;

  return (
    <main className="page space-y-6 lg:flex lg:h-[calc(100vh-40px)] lg:flex-col lg:overflow-hidden lg:pb-0">
      <Card className="lg:shrink-0">
        <CardHeader className="gap-4 lg:py-5">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="warm">按标的（一览表）</Badge>
            {!profile ? <Badge variant="neutral">公开预览 · 范围受限</Badge> : null}
          </div>
          <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
            <div>
              <CardTitle className="text-3xl">标的 × 作者信号一览</CardTitle>
              <CardDescription>
                纵向为标的，横向为作者；每个圆点代表当前{windowModeLabel}窗口内的一条 crypto 信号。
              </CardDescription>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="inline-flex items-center gap-1 rounded-full border border-[color:var(--border-strong)] bg-[color:var(--paper)] p-1">
                <Button
                  type="button"
                  size="sm"
                  variant={granularity === "week" ? "secondary" : "ghost"}
                  className="min-w-[64px]"
                  onClick={() => navigate(endDate, "week")}
                >
                  按周
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant={granularity === "day" ? "secondary" : "ghost"}
                  className="min-w-[64px]"
                  onClick={() => navigate(endDate, "day")}
                >
                  按日
                </Button>
              </div>
              <Button
                type="button"
                variant="secondary"
                disabled={!data?.previousEndDate}
                onClick={() => navigate(data?.previousEndDate ?? null)}
              >
                <ArrowLeft className="h-4 w-4" />
                {previousLabel}
              </Button>
              <Button
                type="button"
                variant="secondary"
                disabled={!data?.nextEndDate}
                onClick={() => navigate(data?.nextEndDate ?? null)}
              >
                {nextLabel}
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
            <p className="mt-1 text-sm font-semibold">{windowLabel}</p>
          </div>
          <div className="rounded-2xl border border-[color:var(--border)] bg-[color:var(--paper)] px-4 py-3">
            <p className="text-xs text-[color:var(--soft-ink)]">标的</p>
            <p className="mt-1 text-sm font-semibold">{formatCount(matrix?.assets.length ?? 0)}</p>
          </div>
          <div className="rounded-2xl border border-[color:var(--border)] bg-[color:var(--paper)] px-4 py-3">
            <p className="text-xs text-[color:var(--soft-ink)]">作者</p>
            <p className="mt-1 text-sm font-semibold">{formatCount(matrix?.authors.length ?? 0)}</p>
          </div>
          <div className="rounded-2xl border border-[color:var(--border)] bg-[color:var(--paper)] px-4 py-3">
            <p className="text-xs text-[color:var(--soft-ink)]">信号点位</p>
            <p className="mt-1 text-sm font-semibold">{formatCount(totalViews)}</p>
          </div>
        </div>

        <Card className="min-h-[420px] overflow-hidden">
          <CardContent className="h-full p-0">
            {error ? <div className="m-4 empty field-error">{error}</div> : null}
            {matrixLoading ? <div className="m-4 empty">一览表加载中</div> : null}
            {!matrixLoading && matrix && matrix.assets.length && matrix.authors.length ? (
              <div className="h-full overflow-auto overscroll-contain">
                <table className="min-w-max border-separate border-spacing-0">
                  <thead>
                    <tr>
                      <th className="sticky left-0 top-0 z-30 min-w-[220px] border-b border-r border-[color:var(--border)] bg-[color:var(--paper-strong)] px-4 py-3">
                        标的
                      </th>
                      <th className="sticky left-[220px] top-0 z-30 min-w-[320px] max-w-[320px] border-b border-r border-[color:var(--border)] bg-[color:var(--paper-strong)] px-4 py-3 text-left">
                        说明
                      </th>
                      {profile?.isAdmin ? (
                        <th className="sticky left-[540px] top-0 z-30 min-w-[128px] max-w-[128px] border-b border-r border-[color:var(--border)] bg-[color:var(--paper-strong)] px-4 py-3 text-left">
                          管理
                        </th>
                      ) : null}
                      {matrix.authors.map((author) => (
                        <th
                          key={author.accountName}
                          className="sticky top-0 z-20 min-w-[148px] max-w-[148px] border-b border-r border-[color:var(--border)] bg-[color:var(--paper-strong)] px-3 py-3 align-bottom"
                        >
                          <Link
                            href={`/crypto/feed?q=${encodeURIComponent(author.accountName)}`}
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
                    {matrix.assets.map((asset) => (
                      <tr key={asset.assetKey}>
                        <th className="sticky left-0 z-10 min-w-[220px] border-b border-r border-[color:var(--border)] bg-[color:var(--paper)] px-4 py-3 text-left align-top">
                          <Link
                            href={`/crypto/assets?asset=${encodeURIComponent(asset.assetKey)}`}
                            className="block text-sm font-semibold normal-case tracking-normal text-[color:var(--ink)] underline-offset-4 hover:text-[color:var(--accent-strong)] hover:underline"
                          >
                            {asset.displayName}
                          </Link>
                          <span className="mt-1 block text-xs font-normal normal-case tracking-normal text-[color:var(--muted-ink)]">
                            {assetLabel(asset)} · {formatCount(asset.mentionCount)}
                          </span>
                        </th>
                        <td className="sticky left-[220px] z-10 min-w-[320px] max-w-[320px] border-b border-r border-[color:var(--border)] bg-[color:var(--paper)] px-4 py-3 align-top">
                          <p className="text-sm leading-6 text-[color:var(--muted-ink)]">{assetSummary(asset)}</p>
                        </td>
                        {profile?.isAdmin ? (
                          <td className="sticky left-[540px] z-10 min-w-[128px] max-w-[128px] border-b border-r border-[color:var(--border)] bg-[color:var(--paper)] px-4 py-3 align-top">
                            <DeleteCryptoAssetButton
                              assetKey={asset.assetKey}
                              reason="deleted_from_overview"
                              label="删除"
                              onChanged={() => {
                                setData((current) =>
                                  current
                                    ? {
                                        ...current,
                                        assets: current.assets.filter((item) => item.assetKey !== asset.assetKey),
                                        cells: current.cells.filter((item) => item.assetKey !== asset.assetKey),
                                      }
                                    : current,
                                );
                              }}
                            />
                          </td>
                        ) : null}
                        {matrix.authors.map((author) => {
                          const cell = cellMap.get(cellKey(asset.assetKey, author.accountName));
                          return (
                            <td
                              key={`${asset.assetKey}-${author.accountName}`}
                              className="min-w-[148px] max-w-[148px] border-b border-r border-[color:var(--border)] bg-[color:var(--panel)]/70 px-3 py-3 align-top"
                            >
                              {cell?.views.length ? (
                                <div className="flex flex-wrap gap-1.5">
                                  {cell.views.map((view, index) => (
                                    <SignalDot
                                      key={`${asset.assetKey}-${author.accountName}-${view.date}-${index}`}
                                      asset={asset}
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
            {!matrixLoading && matrix && (!matrix.assets.length || !matrix.authors.length) ? (
              <div className="m-4 empty">{profile ? emptyLabel : "暂无公开预览数据"}</div>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
