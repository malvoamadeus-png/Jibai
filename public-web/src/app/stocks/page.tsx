import { Suspense } from "react";

import { EntityBrowser } from "@/components/entity-browser";
import { LoadingPanel } from "@/components/page-states";

export default function StocksPage() {
  return (
    <Suspense fallback={<LoadingPanel />}>
      <EntityBrowser type="stock" />
    </Suspense>
  );
}
