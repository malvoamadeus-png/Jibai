import { Suspense } from "react";

import { LoadingPanel } from "@/components/page-states";
import { StockNewsTrackingTable } from "@/components/stock-news-tracking-table";

export default function StockNewsTrackingPage() {
  return (
    <Suspense fallback={<LoadingPanel />}>
      <StockNewsTrackingTable />
    </Suspense>
  );
}
