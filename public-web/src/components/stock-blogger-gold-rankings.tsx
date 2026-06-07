"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ArrowDownRight,
  ArrowUpRight,
  CalendarDays,
  ChevronDown,
  ChevronRight,
  Clock3,
  Trophy,
} from "lucide-react";

import { LoadingPanel } from "@/components/page-states";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/lib/auth-context";
import { getStockBloggerGoldRankings } from "@/lib/direct-data";
import type { StockBloggerAuthorScore, StockBloggerGoldData, StockBloggerHorizonScore, StockBloggerScoreEvent } from "@/lib/types";
import { cn, formatCount } from "@/lib/utils";

const HORIZONS = ["1d", "5d", "20d"] as const;
const GOLD_RANKINGS_FETCH_ENABLED = process.env.NEXT_PUBLIC_STOCK_BLOGGER_GOLD_FETCH_ENABLED === "true";

function formatScore(value: number | null) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "暂无";
  return value.toFixed(1);
}

function formatSignedScore(value: number | null) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "暂无";
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}`;
}

function formatPct(value: number | null) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "";
  return `${value > 0 ? "+" : ""}${(value * 100).toFixed(1)}%`;
}

function horizonValue(author: StockBloggerAuthorScore, label: (typeof HORIZONS)[number]) {
  if (label === "1d") return author.score1d;
  if (label === "5d") return author.score5d;
  return author.score20d;
}

function convictionWidth(value: string) {
  if (value === "strong") return "100%";
  if (value === "medium") return "72%";
  if (value === "weak") return "44%";
  return "58%";
}

function directionLabel(event: StockBloggerScoreEvent) {
  return event.direction === "negative" ? "看空" : "看多";
}

function statusLabel(score: StockBloggerHorizonScore) {
  if (score.status === "scored") return formatSignedScore(score.score);
  if (score.status === "pending") return "待成熟";
  if (score.status === "missing_price") return "缺行情";
  return score.status || "未评分";
}

function ScorePill({ score }: { score: StockBloggerHorizonScore }) {
  const numeric = score.status === "scored" && score.score !== null;
  const positive = numeric && (score.score ?? 0) >= 0;
  return (
    <div
      className={cn(
        "min-w-[82px] rounded-[8px] border px-2.5 py-2 text-xs",
        numeric
          ? positive
            ? "border-[color:rgba(25,131,93,0.18)] bg-[color:rgba(25,131,93,0.07)] text-[color:var(--success)]"
            : "border-[color:rgba(212,67,67,0.18)] bg-[color:rgba(212,67,67,0.07)] text-[color:var(--danger)]"
          : "border-[color:var(--border)] bg-white/58 text-[color:var(--muted-ink)]",
      )}
      title={formatPct(score.directionalExcess)}
    >
      <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[color:var(--soft-ink)]">
        {score.status || "empty"}
      </div>
      <div className="mt-1 font-semibold">{statusLabel(score)}</div>
    </div>
  );
}

function DirectionChip({ event }: { event: StockBloggerScoreEvent }) {
  const positive = event.direction === "positive";
  const Icon = positive ? ArrowUpRight : ArrowDownRight;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-semibold",
        positive
          ? "border-[color:rgba(25,131,93,0.18)] bg-[color:rgba(25,131,93,0.08)] text-[color:var(--success)]"
          : "border-[color:rgba(212,67,67,0.18)] bg-[color:rgba(212,67,67,0.08)] text-[color:var(--danger)]",
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      {directionLabel(event)}
    </span>
  );
}

function ConvictionBar({ value }: { value: string }) {
  return (
    <span className="inline-flex min-w-[76px] flex-col gap-1">
      <span className="text-[11px] font-semibold text-[color:var(--muted-ink)]">{value || "unknown"}</span>
      <span className="h-1.5 rounded-full bg-[color:rgba(99,112,131,0.18)]">
        <span
          className="block h-1.5 rounded-full bg-[color:var(--accent)]"
          style={{ width: convictionWidth(value) }}
        />
      </span>
    </span>
  );
}

function AuthorDetail({ author }: { author: StockBloggerAuthorScore }) {
  const events = author.events.slice().sort((left, right) => right.eventTradingDay.localeCompare(left.eventTradingDay));
  return (
    <div className="space-y-2 border-t border-[color:var(--border)] bg-[color:rgba(248,251,255,0.58)] p-3 md:p-4">
      {events.length ? (
        events.map((event) => (
          <div
            key={event.id}
            className="grid gap-3 rounded-[8px] border border-[color:var(--border)] bg-white/72 p-3 md:grid-cols-[minmax(160px,1.1fr)_auto_minmax(260px,1.6fr)] md:items-center"
          >
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="truncate text-sm font-semibold text-[color:var(--ink)]">{event.displayName}</span>
                {event.ticker ? <Badge variant="neutral" className="normal-case">{event.ticker}</Badge> : null}
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-[color:var(--muted-ink)]">
                <CalendarDays className="h-3.5 w-3.5" />
                {event.eventTradingDay}
                {event.benchmarkSymbol ? <span>· {event.benchmarkSymbol}</span> : null}
              </div>
            </div>
            <div className="flex items-center gap-3">
              <DirectionChip event={event} />
              <ConvictionBar value={event.conviction} />
            </div>
            <div className="grid grid-cols-3 gap-2">
              {HORIZONS.map((label) => (
                <ScorePill key={label} score={event.horizonScores[label]} />
              ))}
            </div>
          </div>
        ))
      ) : (
        <div className="rounded-[8px] border border-[color:var(--border)] bg-white/72 p-4 text-sm text-[color:var(--muted-ink)]">
          暂无已生成的事件明细。
        </div>
      )}
    </div>
  );
}

function AuthorRow({ author, index }: { author: StockBloggerAuthorScore; index: number }) {
  const [open, setOpen] = useState(false);
  const positiveTotal = Math.max(1, author.positiveCount + author.negativeCount);
  const positivePct = (author.positiveCount / positiveTotal) * 100;
  return (
    <div className="overflow-hidden rounded-[8px] border border-[color:var(--border)] bg-white/76">
      <button
        type="button"
        className="grid w-full gap-3 p-3 text-left transition hover:bg-[color:var(--paper-strong)] md:grid-cols-[48px_minmax(150px,1.2fr)_110px_repeat(3,86px)_110px_120px_150px] md:items-center"
        onClick={() => setOpen((current) => !current)}
      >
        <div className="flex items-center gap-2 text-sm font-semibold text-[color:var(--muted-ink)]">
          {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          #{index + 1}
        </div>
        <div className="min-w-0">
          <div className="truncate font-semibold text-[color:var(--ink)]">@{author.accountName}</div>
          <div className="mt-1 truncate text-xs text-[color:var(--muted-ink)]">{author.authorNickname || author.accountName}</div>
        </div>
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[color:var(--soft-ink)]">综合分</div>
          <div className="mt-1 text-xl font-semibold text-[color:var(--ink)]">{formatScore(author.overallScore)}</div>
        </div>
        {HORIZONS.map((label) => (
          <div key={label}>
            <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[color:var(--soft-ink)]">{label}</div>
            <div className="mt-1 font-semibold text-[color:var(--ink)]">{formatSignedScore(horizonValue(author, label))}</div>
          </div>
        ))}
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[color:var(--soft-ink)]">评分天数</div>
          <div className="mt-1 font-semibold text-[color:var(--ink)]">{author.scoredDayCount}</div>
        </div>
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[color:var(--soft-ink)]">事件</div>
          <div className="mt-1 font-semibold text-[color:var(--ink)]">{author.scoredEventCount}/{author.eventCount}</div>
        </div>
        <div>
          <div className="flex items-center justify-between text-[11px] font-semibold uppercase tracking-[0.08em] text-[color:var(--soft-ink)]">
            <span>方向</span>
            <span>{author.pendingCount} pending</span>
          </div>
          <div className="mt-2 h-2 rounded-full bg-[color:rgba(212,67,67,0.18)]">
            <div className="h-2 rounded-full bg-[color:rgba(25,131,93,0.72)]" style={{ width: `${positivePct}%` }} />
          </div>
          <div className="mt-1 text-xs text-[color:var(--muted-ink)]">+{author.positiveCount} / -{author.negativeCount}</div>
        </div>
      </button>
      {open ? <AuthorDetail author={author} /> : null}
    </div>
  );
}

export function StockBloggerGoldRankings() {
  const { loading, profile, signIn, supabase } = useAuth();
  const [data, setData] = useState<StockBloggerGoldData | null>(null);
  const [rankingLoading, setRankingLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (loading || !profile) return;
    if (!GOLD_RANKINGS_FETCH_ENABLED) return;
    let cancelled = false;
    Promise.resolve().then(() => {
      if (!cancelled) setRankingLoading(true);
    });
    getStockBloggerGoldRankings(supabase)
      .then((nextData) => {
        if (cancelled) return;
        setData(nextData);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setData(null);
        setError(err instanceof Error ? err.message : "点金榜加载失败");
      })
      .finally(() => {
        if (!cancelled) setRankingLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [loading, profile, supabase]);

  const authors = useMemo(() => data?.authors ?? [], [data]);

  if (loading) return <LoadingPanel />;

  if (!profile) {
    return (
      <main className="page space-y-6">
        <Card variant="elevated">
          <CardHeader>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="warm">点金榜</Badge>
              <Badge variant="neutral">登录可见</Badge>
            </div>
            <CardTitle className="text-3xl">点金榜</CardTitle>
            <CardDescription>登录后查看股票博主历史观点的超额收益评分。</CardDescription>
          </CardHeader>
          <CardContent>
            <Button type="button" onClick={signIn}>Google 登录</Button>
          </CardContent>
        </Card>
      </main>
    );
  }

  return (
    <main className="page space-y-6">
      <Card>
        <CardHeader className="gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="warm">点金榜</Badge>
            <Badge variant="neutral">作者观点日归一化</Badge>
          </div>
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <CardTitle className="text-3xl">点金榜</CardTitle>
              <CardDescription>按 1/5/20 交易日方向超额收益评价首批股票博主。</CardDescription>
            </div>
            <div className="grid grid-cols-2 gap-2 text-sm md:grid-cols-4">
              <div className="rounded-[8px] border border-[color:var(--border)] bg-white/62 px-3 py-2">
                <div className="text-xs text-[color:var(--muted-ink)]">窗口</div>
                <div className="mt-1 font-semibold">{data?.run?.windowStart || "-"} 至 {data?.run?.windowEnd || "-"}</div>
              </div>
              <div className="rounded-[8px] border border-[color:var(--border)] bg-white/62 px-3 py-2">
                <div className="text-xs text-[color:var(--muted-ink)]">作者</div>
                <div className="mt-1 font-semibold">{formatCount(data?.run?.authorCount ?? authors.length)}</div>
              </div>
              <div className="rounded-[8px] border border-[color:var(--border)] bg-white/62 px-3 py-2">
                <div className="text-xs text-[color:var(--muted-ink)]">事件</div>
                <div className="mt-1 font-semibold">{formatCount(data?.run?.eventCount ?? 0)}</div>
              </div>
              <div className="rounded-[8px] border border-[color:var(--border)] bg-white/62 px-3 py-2">
                <div className="flex items-center gap-1 text-xs text-[color:var(--muted-ink)]"><Clock3 className="h-3.5 w-3.5" /> 更新</div>
                <div className="mt-1 font-semibold">{data?.run?.updatedAt ? data.run.updatedAt.slice(0, 10) : "-"}</div>
              </div>
            </div>
          </div>
        </CardHeader>
      </Card>

      {error ? (
        <Card variant="muted">
          <CardContent className="py-8 text-sm text-[color:var(--danger)]">{error}</CardContent>
        </Card>
      ) : null}

      {!GOLD_RANKINGS_FETCH_ENABLED ? (
        <Card variant="muted">
          <CardContent className="py-8 text-sm text-[color:var(--muted-ink)]">
            点金榜数据暂未开启。
          </CardContent>
        </Card>
      ) : null}

      <Card variant="elevated">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-2xl">
            <Trophy className="h-5 w-5 text-[color:var(--accent-strong)]" />
            作者排名
          </CardTitle>
          <CardDescription>样本量只作为提示，不参与排序分。</CardDescription>
        </CardHeader>
        <CardContent>
          {!GOLD_RANKINGS_FETCH_ENABLED ? (
            <div className="rounded-[8px] border border-[color:var(--border)] bg-white/62 p-6 text-sm text-[color:var(--muted-ink)]">
              当前不拉取点金榜后端数据，其他页面和组件不受影响。
            </div>
          ) : rankingLoading ? (
            <div className="rounded-[8px] border border-[color:var(--border)] bg-white/62 p-6 text-sm text-[color:var(--muted-ink)]">
              正在加载点金榜。
            </div>
          ) : authors.length ? (
            <div className="space-y-3">
              {authors.map((author, index) => (
                <AuthorRow key={author.accountId || author.accountName} author={author} index={index} />
              ))}
            </div>
          ) : (
            <div className="rounded-[8px] border border-[color:var(--border)] bg-white/62 p-6 text-sm text-[color:var(--muted-ink)]">
              暂无可展示的评分快照。
            </div>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
