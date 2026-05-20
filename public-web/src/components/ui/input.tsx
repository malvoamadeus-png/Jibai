import * as React from "react";

import { cn } from "@/lib/utils";

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "flex h-11 w-full rounded-[18px] border border-[color:var(--border-strong)] bg-white/84 px-4 py-2 text-sm text-[color:var(--ink)] shadow-[inset_0_1px_0_rgba(255,255,255,0.75),0_1px_2px_rgba(15,23,42,0.04)] outline-none transition placeholder:text-[color:var(--soft-ink)] focus:border-[color:var(--accent)] focus:ring-4 focus:ring-[color:var(--ring)]",
        className,
      )}
      {...props}
    />
  );
}
