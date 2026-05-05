"use client";

import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "@/components/status-badge";
import type { AuthorListItem, EntityListItem } from "@/lib/types";
import { cn, formatCount, formatDate, platformLabel } from "@/lib/utils";

type InsightListCardProps =
  | {
      type: "author";
      item: AuthorListItem;
      active: boolean;
      onSelect: () => void;
    }
  | {
      type: "entity";
      item: EntityListItem;
      active: boolean;
      onSelect: () => void;
    };

export function InsightListCard(props: InsightListCardProps) {
  const isAuthor = props.type === "author";
  const title = isAuthor ? props.item.accountName || props.item.authorNickname : props.item.displayName;
  const subtitle = isAuthor
    ? props.item.authorNickname && props.item.authorNickname !== props.item.accountName
      ? props.item.authorNickname
      : props.item.profileUrl
    : [props.item.ticker, props.item.market].filter(Boolean).join(" / ") || props.item.key;
  const updatedAt = props.item.updatedAt;
  const metrics = isAuthor
    ? [
        { label: "最近日期", value: formatDate(props.item.latestDate) },
        { label: "记录天数", value: formatCount(props.item.totalDays) },
        { label: "累计内容", value: formatCount(props.item.totalNotes) },
      ]
    : [
        { label: "最近日期", value: formatDate(props.item.latestDate) },
        { label: "提及天数", value: formatCount(props.item.mentionDays) },
        { label: "累计提及", value: formatCount(props.item.totalMentions) },
      ];

  return (
    <button
      type="button"
      onClick={props.onSelect}
      className={cn(
        "block w-full rounded-[24px] border p-4 text-left transition",
        props.active
          ? "border-[color:var(--accent)] bg-[color:rgba(181,106,59,0.12)] shadow-[0_14px_32px_rgba(44,33,22,0.08)]"
          : "border-[color:var(--border)] bg-[color:var(--paper)] hover:border-[color:var(--accent)] hover:bg-[color:var(--paper-strong)]",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-1.5">
          {isAuthor ? (
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="neutral" className="tracking-[0.06em] normal-case">
                {platformLabel(props.item.platform)}
              </Badge>
              <StatusBadge status={props.item.latestStatus} />
            </div>
          ) : null}
          <p className="truncate text-base font-semibold text-[color:var(--ink)]">{title}</p>
          <p className="truncate text-sm text-[color:var(--muted-ink)]">{subtitle}</p>
        </div>
        {updatedAt ? <span className="shrink-0 text-[11px] text-[color:var(--soft-ink)]">{formatDate(updatedAt)}</span> : null}
      </div>

      <div className="mt-4 grid grid-cols-3 gap-2">
        {metrics.map((metric) => (
          <div key={`${title}-${metric.label}`} className="rounded-2xl bg-[color:var(--panel)]/65 px-3 py-2">
            <p className="text-[11px] text-[color:var(--soft-ink)]">{metric.label}</p>
            <p className="mt-1 text-sm font-semibold text-[color:var(--ink)]">{metric.value}</p>
          </div>
        ))}
      </div>
    </button>
  );
}
