import Link from "next/link";

import { Button } from "@/components/ui/button";

function buildHref(basePath: string, currentParams: URLSearchParams, page: number) {
  const params = new URLSearchParams(currentParams);
  params.set("page", String(page));
  return `${basePath}?${params.toString()}`;
}

export function PaginationLinks({
  basePath,
  page,
  totalPages,
  currentParams,
}: {
  basePath: string;
  page: number;
  totalPages: number;
  currentParams: URLSearchParams;
}) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-[24px] border border-[color:var(--border)] bg-[color:var(--paper)] px-4 py-3">
      <p className="text-sm text-[color:var(--muted-ink)]">
        第 {page} / {totalPages} 页
      </p>
      <div className="flex items-center gap-2">
        <Button asChild variant="secondary" size="sm" disabled={page <= 1}>
          <Link aria-disabled={page <= 1} href={buildHref(basePath, currentParams, Math.max(1, page - 1))}>
            上一页
          </Link>
        </Button>
        <Button asChild variant="secondary" size="sm" disabled={page >= totalPages}>
          <Link
            aria-disabled={page >= totalPages}
            href={buildHref(basePath, currentParams, Math.min(totalPages, page + 1))}
          >
            下一页
          </Link>
        </Button>
      </div>
    </div>
  );
}
