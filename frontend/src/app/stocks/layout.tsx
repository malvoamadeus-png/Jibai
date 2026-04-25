import type { ReactNode } from "react";

import { BrowseShell } from "@/components/browse-shell";

export default function StocksLayout({ children }: { children: ReactNode }) {
  return <BrowseShell resource="stocks">{children}</BrowseShell>;
}
