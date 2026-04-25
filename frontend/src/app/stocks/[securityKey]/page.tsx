import { notFound } from "next/navigation";

import { EmptyState } from "@/components/empty-state";
import { PaginationLinks } from "@/components/pagination-links";
import { StockKlineCard } from "@/components/stock-kline-card";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { StockDayCard } from "@/components/stock-day-card";
import { getStockKlineData } from "@/lib/stock-chart";
import { getStockDetail } from "@/lib/queries";
import { parsePositiveInt } from "@/lib/utils";

export const dynamic = "force-dynamic";

type Params = Promise<{ securityKey: string }>;
type SearchParams = Promise<{ page?: string }>;

export default async function StockDetailPage({
  params,
  searchParams,
}: {
  params: Params;
  searchParams: SearchParams;
}) {
  const { securityKey } = await params;
  const query = await searchParams;
  const page = parsePositiveInt(query.page, 1, 1, 9999);
  const data = getStockDetail({ securityKey: decodeURIComponent(securityKey), page, pageSize: 20 });

  if (!data) {
    notFound();
  }

  const chart = await getStockKlineData({
    securityKey: data.securityKey,
    displayName: data.displayName,
    ticker: data.ticker,
    market: data.market,
  });

  const currentParams = new URLSearchParams();

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="gap-4">
          {data.ticker || data.market ? (
            <div className="flex flex-wrap items-center gap-2">
              {data.ticker ? <Badge variant="warm">{data.ticker}</Badge> : null}
              {data.market ? <Badge variant="neutral">{data.market}</Badge> : null}
            </div>
          ) : null}
          <CardTitle className="text-3xl">{data.displayName}</CardTitle>
        </CardHeader>
      </Card>

      <StockKlineCard
        displayName={data.displayName}
        chart={chart}
        identity={{
          securityKey: data.securityKey,
          ticker: data.ticker,
          market: data.market,
        }}
      />

      {data.timeline.rows.length === 0 ? (
        <EmptyState title="这只股票还没有时间线记录" description="先跑一次抓取和分析，这里就会出现记录。" />
      ) : (
        <>
          <div className="space-y-4">
            {data.timeline.rows.map((day) => (
              <StockDayCard key={`${day.date}-${day.updatedAt}`} day={day} />
            ))}
          </div>
          <PaginationLinks
            basePath={`/stocks/${encodeURIComponent(data.securityKey)}`}
            page={data.timeline.page}
            totalPages={data.timeline.totalPages}
            currentParams={currentParams}
          />
        </>
      )}
    </div>
  );
}
