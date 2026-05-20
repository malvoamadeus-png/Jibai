import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const cardVariants = cva(
  "rounded-[30px] border border-[color:var(--border)] backdrop-blur-[24px] transition-shadow",
  {
    variants: {
      variant: {
        default: "bg-[linear-gradient(180deg,var(--surface-strong),var(--surface))] shadow-[var(--shadow-md)]",
        muted: "bg-[linear-gradient(180deg,rgba(248,251,255,0.9),rgba(241,246,252,0.82))] shadow-[var(--shadow-sm)]",
        elevated: "bg-white/90 shadow-[var(--shadow-lg)]",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

type CardProps = React.HTMLAttributes<HTMLDivElement> & VariantProps<typeof cardVariants>;

export function Card({ className, variant, ...props }: CardProps) {
  return (
    <div
      className={cn(cardVariants({ variant }), className)}
      {...props}
    />
  );
}

export function CardHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("space-y-2 p-6 md:p-7", className)} {...props} />;
}

export function CardTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h2 className={cn("text-xl font-semibold tracking-[-0.03em] text-[color:var(--ink)]", className)} {...props} />;
}

export function CardDescription({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("text-sm leading-6 text-[color:var(--muted-ink)]", className)} {...props} />;
}

export function CardContent({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("px-6 pb-6 md:px-7 md:pb-7", className)} {...props} />;
}
