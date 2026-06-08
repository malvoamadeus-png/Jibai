import { Suspense } from "react";

import { LoadingPanel } from "@/components/page-states";
import { StockNewsTimeline } from "@/components/stock-news-timeline";

export default function StockNewsPage() {
  return (
    <Suspense fallback={<LoadingPanel />}>
      <StockNewsTimeline />
    </Suspense>
  );
}
