import { Suspense } from "react";

import { EntityBrowser } from "@/components/entity-browser";
import { LoadingPanel } from "@/components/page-states";

export default function CryptoAssetsPage() {
  return (
    <Suspense fallback={<LoadingPanel />}>
      <EntityBrowser type="crypto" domain="crypto" />
    </Suspense>
  );
}
