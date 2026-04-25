import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium tracking-[0.08em] uppercase",
  {
    variants: {
      variant: {
        neutral: "border-[color:var(--border-strong)] bg-[color:var(--paper-strong)] text-[color:var(--muted-ink)]",
        warm: "border-[color:rgba(181,106,59,0.28)] bg-[color:rgba(181,106,59,0.12)] text-[color:var(--accent-strong)]",
        positive: "border-[color:rgba(65,122,90,0.28)] bg-[color:rgba(65,122,90,0.12)] text-[#28593f]",
        danger: "border-[color:rgba(138,61,61,0.28)] bg-[color:rgba(138,61,61,0.12)] text-[#7d2a2a]",
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
