import type { ReactNode } from "react";

import { BrowseShell } from "@/components/browse-shell";

export default function AuthorsLayout({ children }: { children: ReactNode }) {
  return <BrowseShell resource="authors">{children}</BrowseShell>;
}
