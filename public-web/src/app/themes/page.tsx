import { Suspense } from "react";

import { EntityBrowser } from "@/components/entity-browser";
import { LoadingPanel } from "@/components/page-states";

export default function ThemesPage() {
  return (
    <Suspense fallback={<LoadingPanel />}>
      <EntityBrowser type="theme" />
    </Suspense>
  );
}
