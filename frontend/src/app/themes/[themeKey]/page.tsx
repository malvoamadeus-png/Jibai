import { notFound } from "next/navigation";

import { EmptyState } from "@/components/empty-state";
import { PaginationLinks } from "@/components/pagination-links";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { ThemeDayCard } from "@/components/theme-day-card";
import { getThemeDetail } from "@/lib/queries";
import { parsePositiveInt } from "@/lib/utils";

export const dynamic = "force-dynamic";

type Params = Promise<{ themeKey: string }>;
type SearchParams = Promise<{ page?: string }>;

export default async function ThemeDetailPage({
  params,
  searchParams,
}: {
  params: Params;
  searchParams: SearchParams;
}) {
  const { themeKey } = await params;
  const query = await searchParams;
  const page = parsePositiveInt(query.page, 1, 1, 9999);
  const data = getThemeDetail({ themeKey: decodeURIComponent(themeKey), page, pageSize: 20 });

  if (!data) {
    notFound();
  }

  const currentParams = new URLSearchParams();

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="warm">{data.themeKey}</Badge>
          </div>
          <CardTitle className="text-3xl">{data.displayName}</CardTitle>
        </CardHeader>
      </Card>

      {data.timeline.rows.length === 0 ? (
        <EmptyState title="这个 Theme 还没有时间线记录" description="先跑一次抓取和分析，这里就会出现记录。" />
      ) : (
        <>
          <div className="space-y-4">
            {data.timeline.rows.map((day) => (
              <ThemeDayCard key={`${day.date}-${day.updatedAt}`} day={day} />
            ))}
          </div>
          <PaginationLinks
            basePath={`/themes/${encodeURIComponent(data.themeKey)}`}
            page={data.timeline.page}
            totalPages={data.timeline.totalPages}
            currentParams={currentParams}
          />
        </>
      )}
    </div>
  );
}
