import type { ReactNode } from "react";

import { BrowseShell } from "@/components/browse-shell";

export default function ThemesLayout({ children }: { children: ReactNode }) {
  return <BrowseShell resource="themes">{children}</BrowseShell>;
}
