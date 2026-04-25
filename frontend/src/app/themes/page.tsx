import { redirect } from "next/navigation";

import { EmptyState } from "@/components/empty-state";
import { getThemesPage } from "@/lib/queries";
import { parsePositiveInt } from "@/lib/utils";

export const dynamic = "force-dynamic";

type SearchParams = Promise<{
  listPage?: string;
  q?: string;
}>;

export default async function ThemesPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const params = await searchParams;
  const listPage = parsePositiveInt(params.listPage, 1, 1, 9999);
  const q = params.q ?? "";
  const result = getThemesPage({ page: listPage, pageSize: 20, q });

  if (result.total === 0 || result.rows.length === 0) {
    return (
      <EmptyState
        title="暂无 Theme 时间线"
        description="先完成一次抓取和分析，这里才会出现 Theme 时间线。"
      />
    );
  }

  const nextParams = new URLSearchParams();
  if (q) nextParams.set("q", q);
  if (listPage > 1) nextParams.set("listPage", String(listPage));

  redirect(
    `/themes/${encodeURIComponent(result.rows[0].themeKey)}${nextParams.toString() ? `?${nextParams.toString()}` : ""}`,
  );
}
