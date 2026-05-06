import Link from "next/link";

import type { AuthorTimelineDay } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "@/components/status-badge";
import { entityTypeLabel, viewSignalLabel, viewSignalVariant } from "@/lib/utils";

export function AuthorDayCard({ day }: { day: AuthorTimelineDay }) {
  return (
    <Card>
      <CardHeader className="gap-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="warm">{day.date}</Badge>
              <StatusBadge status={day.status} />
            </div>
            <CardTitle className="text-2xl leading-tight">{day.summaryText}</CardTitle>
          </div>
          <div className="rounded-2xl border border-[color:var(--border)] bg-[color:var(--paper-strong)] px-4 py-3 text-right">
            <p className="text-xs uppercase tracking-[0.16em] text-[color:var(--soft-ink)]">当日内容</p>
            <p className="mt-2 text-3xl font-semibold">{day.noteCountToday}</p>
          </div>
        </div>

        {(day.mentionedStocks.length > 0 || day.mentionedThemes.length > 0) && (
          <div className="flex flex-wrap gap-2">
            {day.mentionedStocks.map((stock) => (
              <span
                key={`stock-${stock}`}
                className="rounded-full border border-[color:var(--border-strong)] px-3 py-1.5 text-xs font-medium text-[color:var(--muted-ink)]"
              >
                股票 · {stock}
              </span>
            ))}
            {day.mentionedThemes.map((theme) => (
              <span
                key={`theme-${theme}`}
                className="rounded-full border border-[color:var(--border-strong)] px-3 py-1.5 text-xs font-medium text-[color:var(--muted-ink)]"
              >
                Theme · {theme}
              </span>
            ))}
          </div>
        )}
      </CardHeader>

      <CardContent className="space-y-4">
        {day.viewpoints.length > 0 ? (
          <div className="overflow-hidden rounded-[24px] border border-[color:var(--border)]">
            <div className="hidden grid-cols-[140px_128px_minmax(0,1fr)_112px] gap-4 bg-[color:var(--paper-strong)] px-4 py-3 text-xs font-semibold uppercase tracking-[0.14em] text-[color:var(--soft-ink)] md:grid">
              <span>对象</span>
              <span>类型 / 态度</span>
              <span>逻辑</span>
              <span>来源</span>
            </div>
            {day.viewpoints.map((viewpoint) => (
              <div
                key={`${day.date}-${viewpoint.entityType}-${viewpoint.entityKey}`}
                className="grid gap-3 border-t border-[color:var(--border)] bg-[color:var(--panel)] px-4 py-4 first:border-t-0 md:grid-cols-[140px_128px_minmax(0,1fr)_112px] md:gap-4"
              >
                <div className="space-y-2">
                  {viewpoint.entityType === "stock" ? (
                    <Link
                      href={`/stocks?stock=${encodeURIComponent(viewpoint.entityKey)}`}
                      className="text-base font-semibold underline-offset-4 hover:text-[color:var(--accent-strong)] hover:underline"
                    >
                      {viewpoint.entityName}
                    </Link>
                  ) : viewpoint.entityType === "theme" ? (
                    <Link
                      href={`/themes?theme=${encodeURIComponent(viewpoint.entityKey)}`}
                      className="text-base font-semibold underline-offset-4 hover:text-[color:var(--accent-strong)] hover:underline"
                    >
                      {viewpoint.entityName}
                    </Link>
                  ) : (
                    <p className="text-base font-semibold">{viewpoint.entityName}</p>
                  )}
                </div>

                <div className="flex flex-wrap items-start gap-2">
                  <Badge variant="neutral">{entityTypeLabel(viewpoint.entityType)}</Badge>
                  <Badge variant={viewSignalVariant(viewpoint)}>{viewSignalLabel(viewpoint)}</Badge>
                </div>

                <div className="space-y-2">
                  <p className="text-sm leading-7 text-[color:var(--muted-ink)]">{viewpoint.logic || "暂无逻辑说明"}</p>
                  {viewpoint.evidence.length > 0 && (
                    <p className="text-xs leading-6 text-[color:var(--soft-ink)]">
                      证据：{viewpoint.evidence.join("；")}
                    </p>
                  )}
                </div>

                <div className="flex flex-wrap items-start gap-1.5 md:self-start">
                  {viewpoint.noteUrls.map((url, index) => (
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
        ) : (
          <div className="space-y-3 rounded-[24px] border border-dashed border-[color:var(--border-strong)] bg-[color:var(--paper-strong)]/60 px-4 py-4">
            <div>
              <p className="text-sm font-semibold text-[color:var(--ink)]">结构化观点未生成</p>
              <p className="mt-1 text-sm leading-6 text-[color:var(--muted-ink)]">
                这一天已经抓到内容，但还没有可展示的观点抽取结果。
              </p>
            </div>
            {day.notes.length > 0 ? (
              <div className="space-y-2">
                {day.notes.map((note, index) => (
                  <a
                    key={note.note_id || `${note.url}-${index}`}
                    href={note.url}
                    target="_blank"
                    rel="noreferrer"
                    className="block rounded-2xl border border-[color:var(--border)] bg-[color:var(--panel)] px-3 py-2 text-sm leading-6 text-[color:var(--muted-ink)] transition hover:border-[color:var(--accent)] hover:text-[color:var(--accent-strong)]"
                  >
                    {note.title || `原文 ${index + 1}`}
                  </a>
                ))}
              </div>
            ) : null}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
