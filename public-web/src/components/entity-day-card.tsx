import Link from "next/link";

import type { EntityAuthorView } from "@/lib/types";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { viewSignalLabel, viewSignalVariant } from "@/lib/utils";

export function EntityDayCard({
  day,
}: {
  day: {
    date: string;
    mentionCount: number;
    authorViews: EntityAuthorView[];
  };
}) {
  return (
    <Card>
      <CardHeader className="gap-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <Badge variant="warm">{day.date}</Badge>
          <div className="rounded-2xl border border-[color:var(--border)] bg-[color:var(--paper-strong)] px-4 py-3 text-right">
            <p className="text-xs uppercase tracking-[0.16em] text-[color:var(--soft-ink)]">提及次数</p>
            <p className="mt-2 text-3xl font-semibold">{day.mentionCount}</p>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        <div className="overflow-hidden rounded-[24px] border border-[color:var(--border)]">
          <div className="hidden grid-cols-[180px_128px_minmax(0,1fr)_112px] gap-4 bg-[color:var(--paper-strong)] px-4 py-3 text-xs font-semibold uppercase tracking-[0.14em] text-[color:var(--soft-ink)] md:grid">
            <span>作者</span>
            <span>态度</span>
            <span>逻辑</span>
            <span>来源</span>
          </div>
          {day.authorViews.map((view) => (
            <div
              key={`${day.date}-${view.platform}-${view.account_name}`}
              className="grid gap-3 border-t border-[color:var(--border)] bg-[color:var(--panel)] px-4 py-4 first:border-t-0 md:grid-cols-[180px_128px_minmax(0,1fr)_112px] md:gap-4"
            >
              <div className="space-y-2">
                <Link
                  href={`/feed?q=${encodeURIComponent(view.account_name || view.author_nickname)}`}
                  className="text-base font-semibold underline-offset-4 hover:text-[color:var(--accent-strong)] hover:underline"
                >
                  {view.account_name || view.author_nickname}
                </Link>
              </div>

              <div className="flex flex-wrap items-start gap-2">
                <Badge variant={viewSignalVariant(view)}>{viewSignalLabel(view)}</Badge>
              </div>

              <div className="space-y-2">
                <p className="text-sm leading-7 text-[color:var(--muted-ink)]">{view.logic || "暂无逻辑说明"}</p>
                {view.evidence.length > 0 && (
                  <p className="text-xs leading-6 text-[color:var(--soft-ink)]">
                    证据：{view.evidence.join("；")}
                  </p>
                )}
              </div>

              <div className="flex flex-wrap items-start gap-1.5 md:self-start">
                {view.note_urls.map((url, index) => (
                  <a
                    key={`${url}-${index}`}
                    href={url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center whitespace-nowrap rounded-full border border-[color:var(--border-strong)] px-2.5 py-1 text-[11px] font-medium text-[color:var(--muted-ink)] transition hover:border-[color:var(--accent)] hover:text-[color:var(--accent-strong)]"
                  >
                    来源 {index + 1}
                  </a>
                ))}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
