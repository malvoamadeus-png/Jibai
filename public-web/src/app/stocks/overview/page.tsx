import { Suspense } from "react";

import { LoadingPanel } from "@/components/page-states";
import { StockMatrixOverview } from "@/components/stock-matrix-overview";

export default function StockOverviewPage() {
  return (
    <Suspense fallback={<LoadingPanel />}>
      <StockMatrixOverview />
    </Suspense>
  );
}
