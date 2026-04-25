import { redirect } from "next/navigation";

import { EmptyState } from "@/components/empty-state";
import { getAuthorsPage } from "@/lib/queries";
import { parsePositiveInt } from "@/lib/utils";

export const dynamic = "force-dynamic";

type SearchParams = Promise<{
  listPage?: string;
  q?: string;
  platform?: string;
}>;

export default async function AuthorsPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const params = await searchParams;
  const listPage = parsePositiveInt(params.listPage, 1, 1, 9999);
  const q = params.q ?? "";
  const platform = params.platform ?? "";
  const result = getAuthorsPage({ page: listPage, pageSize: 20, q, platform });

  if (result.total === 0 || result.rows.length === 0) {
    return (
      <EmptyState
        title="暂无作者时间线"
        description="先完成一次抓取和分析，这里才会出现可切换的作者清单。"
      />
    );
  }

  const nextParams = new URLSearchParams();
  if (q) nextParams.set("q", q);
  if (platform) nextParams.set("platform", platform);
  if (listPage > 1) nextParams.set("listPage", String(listPage));

  redirect(
    `/authors/${encodeURIComponent(result.rows[0].accountKey)}${nextParams.toString() ? `?${nextParams.toString()}` : ""}`,
  );
}
