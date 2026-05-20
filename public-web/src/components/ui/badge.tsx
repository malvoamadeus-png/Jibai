import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold tracking-[0.06em]",
  {
    variants: {
      variant: {
        neutral: "border-[color:var(--border-strong)] bg-white/72 text-[color:var(--muted-ink)]",
        warm: "border-[color:rgba(10,132,255,0.16)] bg-[color:rgba(10,132,255,0.09)] text-[color:var(--accent-strong)]",
        positive: "border-[color:rgba(25,131,93,0.18)] bg-[color:rgba(25,131,93,0.09)] text-[color:var(--success)]",
        danger: "border-[color:rgba(212,67,67,0.18)] bg-[color:rgba(212,67,67,0.08)] text-[color:var(--danger)]",
      },
    },
    defaultVariants: {
      variant: "neutral",
    },
  },
);

type BadgeProps = React.HTMLAttributes<HTMLDivElement> & VariantProps<typeof badgeVariants>;

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}
