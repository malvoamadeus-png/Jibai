"use client";

import { RefreshCw, Sparkles, TrendingDown, Waves } from "lucide-react";
import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { LoadingPanel } from "@/components/page-states";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/lib/auth-context";
import { getLatestStockNarrativeBrief } from "@/lib/direct-data";
import type { StockNarrativeBrief } from "@/lib/types";
import { formatCount, formatDate, stripTime } from "@/lib/utils";

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function asNumber(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function metricValue(brief: StockNarrativeBrief | null, key: string) {
  const current = asRecord(brief?.inputDigest.current_window);
  return asNumber(current[key]);
}

function SectionBlock({
  title,
  items,
  icon,
}: {
  title: string;
  items: string[];
  icon: ReactNode;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center gap-3 space-y-0">
        <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-[color:var(--border)] bg-[color:var(--paper-strong)] text-[color:var(--accent-strong)]">
          {icon}
        </span>
        <div>
          <CardTitle className="text-lg">{title}</CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        {items.length ? (
          <ul className="space-y-3">
            {items.map((item, index) => (
              <li key={`${title}-${index}`} className="rounded-2xl border border-[color:var(--border)] bg-[color:var(--paper-strong)] px-4 py-3 text-sm leading-7 text-[color:var(--muted-ink)]">
                {item}
              </li>
            ))}
          </ul>
        ) : (
          <p className="empty">本期没有形成稳定结论。</p>
        )}
      </CardContent>
    </Card>
  );
}

export default function StockNarrativePage() {
  const { loading, supabase } = useAuth();
  const [brief, setBrief] = useState<StockNarrativeBrief | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      setBrief(await getLatestStockNarrativeBrief(supabase));
      setError(null);
    } catch (err) {
      setBrief(null);
      setError(err instanceof Error ? err.message : "叙事简报加载失败");
    } finally {
      setRefreshing(false);
    }
  }, [supabase]);

  useEffect(() => {
    if (loading) return;
    Promise.resolve().then(load);
  }, [load, loading]);

  const paragraphs = useMemo(
    () => (brief?.briefText || "").split(/\n{2,}/).map((item) => item.trim()).filter(Boolean),
    [brief?.briefText],
  );

  if (loading) return <LoadingPanel />;

  return (
    <main className="page space-y-6">
      <Card>
        <CardHeader className="gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="warm">股票叙事简报</Badge>
            <Badge variant="neutral">全站可见</Badge>
          </div>
          <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
            <div>
              <CardTitle className="text-3xl">主流叙事与新风向</CardTitle>
              <CardDescription>
                基于全部管理员已审批股票账号的近期观点，归纳大家正在认可的主线、开始升温的话题和少数负面声音。
              </CardDescription>
            </div>
            <button className="secondary-button" type="button" disabled={refreshing} onClick={load}>
              <RefreshCw size={16} />
              {refreshing ? "刷新中" : "刷新"}
            </button>
          </div>
        </CardHeader>
      </Card>

      {error ? <div className="empty field-error">数据接口未就绪：{error}</div> : null}

      {!brief && !error ? (
        <div className="empty">还没有生成股票叙事简报。生成任务完成后，这里会展示最新一篇。</div>
      ) : null}

      {brief ? (
        <>
          <div className="grid gap-3 md:grid-cols-4">
            <div className="rounded-2xl border border-[color:var(--border)] bg-[color:var(--paper)] px-4 py-3">
              <p className="text-xs text-[color:var(--soft-ink)]">观点窗口</p>
              <p className="mt-1 text-sm font-semibold">
                {brief.windowStart && brief.windowEnd ? `${formatDate(brief.windowStart)} 至 ${formatDate(brief.windowEnd)}` : "暂无"}
              </p>
            </div>
            <div className="rounded-2xl border border-[color:var(--border)] bg-[color:var(--paper)] px-4 py-3">
              <p className="text-xs text-[color:var(--soft-ink)]">观点条目</p>
              <p className="mt-1 text-sm font-semibold">{formatCount(metricValue(brief, "viewpoint_count"))}</p>
            </div>
            <div className="rounded-2xl border border-[color:var(--border)] bg-[color:var(--paper)] px-4 py-3">
              <p className="text-xs text-[color:var(--soft-ink)]">作者</p>
              <p className="mt-1 text-sm font-semibold">{formatCount(metricValue(brief, "author_count"))}</p>
            </div>
            <div className="rounded-2xl border border-[color:var(--border)] bg-[color:var(--paper)] px-4 py-3">
              <p className="text-xs text-[color:var(--soft-ink)]">生成时间</p>
              <p className="mt-1 text-sm font-semibold">{stripTime(brief.updatedAt || brief.createdAt)}</p>
            </div>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>本期小作文</CardTitle>
              <CardDescription>
                简报日期 {formatDate(brief.briefDate)}；历史基线 {brief.baselineStart && brief.baselineEnd ? `${formatDate(brief.baselineStart)} 至 ${formatDate(brief.baselineEnd)}` : "暂无"}。
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {paragraphs.length ? (
                paragraphs.map((paragraph, index) => (
                  <p key={index} className="text-sm leading-8 text-[color:var(--muted-ink)]">
                    {paragraph}
                  </p>
                ))
              ) : (
                <p className="empty">简报正文为空。</p>
              )}
            </CardContent>
          </Card>

          <div className="grid gap-4 xl:grid-cols-3">
            <SectionBlock title="主流叙事" items={brief.sections.mainstreamNarrative} icon={<Waves size={18} />} />
            <SectionBlock title="新风向" items={brief.sections.newDirections} icon={<Sparkles size={18} />} />
            <SectionBlock title="少见负面声音" items={brief.sections.rareNegativeSignals} icon={<TrendingDown size={18} />} />
          </div>
        </>
      ) : null}
    </main>
  );
}
