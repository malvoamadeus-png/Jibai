import { Suspense } from "react";

import { CryptoMatrixOverview } from "@/components/crypto-matrix-overview";
import { LoadingPanel } from "@/components/page-states";

export default function CryptoAssetsOverviewPage() {
  return (
    <Suspense fallback={<LoadingPanel />}>
      <CryptoMatrixOverview />
    </Suspense>
  );
}
