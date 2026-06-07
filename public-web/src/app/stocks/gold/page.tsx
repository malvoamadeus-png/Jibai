import { Suspense } from "react";

import { LoadingPanel } from "@/components/page-states";
import { StockBloggerGoldRankings } from "@/components/stock-blogger-gold-rankings";

export default function StockGoldPage() {
  return (
    <Suspense fallback={<LoadingPanel />}>
      <StockBloggerGoldRankings />
    </Suspense>
  );
}
