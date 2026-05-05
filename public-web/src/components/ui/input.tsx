import * as React from "react";

import { cn } from "@/lib/utils";

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "flex h-11 w-full rounded-full border border-[color:var(--border-strong)] bg-[color:var(--paper)] px-4 py-2 text-sm text-[color:var(--ink)] shadow-sm outline-none transition placeholder:text-[color:var(--soft-ink)] focus:border-[color:var(--accent)] focus:ring-2 focus:ring-[color:rgba(181,106,59,0.15)]",
        className,
      )}
      {...props}
    />
  );
}
