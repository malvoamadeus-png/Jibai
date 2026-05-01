import Link from "next/link";
import {
  ArrowRight,
  BookOpenText,
  CircleDollarSign,
  Radar,
  SlidersHorizontal,
} from "lucide-react";

import { MetricCard } from "@/components/metric-card";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getOverview } from "@/lib/queries";
import { formatCount, makeAccountKey, stripTime } from "@/lib/utils";

export const dynamic = "force-dynamic";

export default function HomePage() {
  const overview = getOverview();

  return (
    <div className="space-y-6">
      <section className="grid gap-4 md:grid-cols-4">
        <MetricCard label="作者" value={formatCount(overview.authorCount)} hint="已建立时间线的账号数" />
        <MetricCard label="股票" value={formatCount(overview.stockCount)} hint="已归一的股票或证券对象" />
        <MetricCard label="Theme" value={formatCount(overview.themeCount)} hint="板块、赛道、概念统一归到 Theme" />
        <MetricCard label="内容" value={formatCount(overview.contentCount)} hint="已写入本地 SQLite 的原始内容数" />
      </section>

      <Card>
        <CardHeader className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div className="space-y-3">
            <Badge variant="warm">{stripTime(overview.lastRunAt)}</Badge>
            <div className="space-y-2">
              <CardTitle className="text-4xl leading-tight">本地观点观察站</CardTitle>
              <p className="max-w-3xl text-sm leading-6 text-[color:var(--muted-ink)]">
                按人、按股票、按 Theme 回看观点变化，也可以直接在本地配置抓取账号、调度时间和立即运行。
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link
              href="/authors"
              className="inline-flex items-center gap-2 rounded-full bg-[color:var(--accent)] px-5 py-3 text-sm font-medium text-white transition hover:opacity-90"
            >
              按人查看
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/stocks"
              className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border-strong)] px-5 py-3 text-sm font-medium transition hover:border-[color:var(--accent)] hover:text-[color:var(--accent-strong)]"
            >
              按股票查看
            </Link>
            <Link
              href="/control"
              className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border-strong)] px-5 py-3 text-sm font-medium transition hover:border-[color:var(--accent)] hover:text-[color:var(--accent-strong)]"
            >
              配置与运行
              <SlidersHorizontal className="h-4 w-4" />
            </Link>
          </div>
        </CardHeader>
      </Card>

      <section className="grid gap-6 xl:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-start justify-between gap-4">
            <div>
              <Badge variant="neutral">按人</Badge>
              <CardTitle className="mt-4 text-2xl">最近活跃作者</CardTitle>
            </div>
            <BookOpenText className="h-5 w-5 text-[color:var(--accent-strong)]" />
          </CardHeader>
          <CardContent className="space-y-3">
            {overview.latestAuthors.map((author) => (
              <Link
                key={author.accountKey}
                href={`/authors/${encodeURIComponent(makeAccountKey(author.platform, author.accountName))}`}
                className="flex items-center justify-between rounded-[22px] border border-[color:var(--border)] bg-[color:var(--panel)] px-4 py-4 transition hover:border-[color:var(--accent)] hover:bg-[color:var(--paper)]"
              >
                <div>
                  <p className="text-lg font-medium">{author.accountName || author.authorNickname}</p>
                  <p className="mt-1 text-sm text-[color:var(--muted-ink)]">
                    {author.platform} · {author.latestDate || "暂无日期"}
                  </p>
                </div>
                <ArrowRight className="h-4 w-4 text-[color:var(--soft-ink)]" />
              </Link>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-start justify-between gap-4">
            <div>
              <Badge variant="neutral">按股票</Badge>
              <CardTitle className="mt-4 text-2xl">最近被讨论的股票</CardTitle>
            </div>
            <CircleDollarSign className="h-5 w-5 text-[color:var(--accent-strong)]" />
          </CardHeader>
          <CardContent className="space-y-3">
            {overview.latestStocks.map((stock) => (
              <Link
                key={stock.securityKey}
                href={`/stocks/${encodeURIComponent(stock.securityKey)}`}
                className="flex items-center justify-between rounded-[22px] border border-[color:var(--border)] bg-[color:var(--panel)] px-4 py-4 transition hover:border-[color:var(--accent)] hover:bg-[color:var(--paper)]"
              >
                <div>
                  <p className="text-lg font-medium">{stock.displayName}</p>
                  <p className="mt-1 text-sm text-[color:var(--muted-ink)]">
                    {stock.latestDate || "暂无日期"} · {stock.totalMentions} 次提及
                  </p>
                </div>
                <ArrowRight className="h-4 w-4 text-[color:var(--soft-ink)]" />
              </Link>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-start justify-between gap-4">
            <div>
              <Badge variant="neutral">按 Theme</Badge>
              <CardTitle className="mt-4 text-2xl">最近被讨论的 Theme</CardTitle>
            </div>
            <Radar className="h-5 w-5 text-[color:var(--accent-strong)]" />
          </CardHeader>
          <CardContent className="space-y-3">
            {overview.latestThemes.map((theme) => (
              <Link
                key={theme.themeKey}
                href={`/themes/${encodeURIComponent(theme.themeKey)}`}
                className="flex items-center justify-between rounded-[22px] border border-[color:var(--border)] bg-[color:var(--panel)] px-4 py-4 transition hover:border-[color:var(--accent)] hover:bg-[color:var(--paper)]"
              >
                <div>
                  <p className="text-lg font-medium">{theme.displayName}</p>
                  <p className="mt-1 text-sm text-[color:var(--muted-ink)]">
                    {theme.latestDate || "暂无日期"} · {theme.totalMentions} 次提及
                  </p>
                </div>
                <ArrowRight className="h-4 w-4 text-[color:var(--soft-ink)]" />
              </Link>
            ))}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
