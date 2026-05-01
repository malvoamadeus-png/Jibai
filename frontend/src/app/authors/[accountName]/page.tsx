import { notFound } from "next/navigation";

import { AuthorDayCard } from "@/components/author-day-card";
import { EmptyState } from "@/components/empty-state";
import { PaginationLinks } from "@/components/pagination-links";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getAuthorDetail } from "@/lib/queries";
import { parsePositiveInt, platformLabel } from "@/lib/utils";

export const dynamic = "force-dynamic";

type Params = Promise<{ accountName: string }>;
type SearchParams = Promise<{ page?: string }>;

export default async function AuthorDetailPage({
  params,
  searchParams,
}: {
  params: Params;
  searchParams: SearchParams;
}) {
  const { accountName } = await params;
  const query = await searchParams;
  const page = parsePositiveInt(query.page, 1, 1, 9999);
  const data = getAuthorDetail({ accountKey: decodeURIComponent(accountName), page, pageSize: 20 });

  if (!data) {
    notFound();
  }

  const currentParams = new URLSearchParams();

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="warm" className="normal-case tracking-[0.04em]">{platformLabel(data.platform)}</Badge>
            {data.authorId ? <Badge variant="neutral">{data.authorId}</Badge> : null}
          </div>
          <CardTitle className="text-3xl">{data.accountName || data.authorNickname}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {data.profileUrl ? (
            <a
              className="text-sm font-medium text-[color:var(--accent-strong)] underline-offset-4 hover:underline"
              href={data.profileUrl}
              target="_blank"
              rel="noreferrer"
            >
              打开原始主页
            </a>
          ) : null}
        </CardContent>
      </Card>

      {data.timeline.rows.length === 0 ? (
        <EmptyState title="这个作者还没有有效观点记录" description="先完成一次抓取和分析，这里才会出现观点时间线。" />
      ) : (
        <>
          <div className="space-y-4">
            {data.timeline.rows.map((day) => (
              <AuthorDayCard key={`${day.date}-${day.status}`} day={day} />
            ))}
          </div>
          <PaginationLinks
            basePath={`/authors/${encodeURIComponent(data.accountKey)}`}
            page={data.timeline.page}
            totalPages={data.timeline.totalPages}
            currentParams={currentParams}
          />
        </>
      )}
    </div>
  );
}
