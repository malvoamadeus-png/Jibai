import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full text-sm font-medium transition-all disabled:pointer-events-none disabled:opacity-50 outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--ring)] focus-visible:ring-offset-2 focus-visible:ring-offset-[color:var(--paper)]",
  {
    variants: {
      variant: {
        primary:
          "bg-[color:var(--accent)] px-4 py-2 text-[color:var(--accent-foreground)] shadow-[0_10px_30px_rgba(181,106,59,0.25)] hover:-translate-y-0.5 hover:bg-[color:var(--accent-strong)]",
        secondary:
          "border border-[color:var(--border-strong)] bg-[color:var(--paper)] px-4 py-2 text-[color:var(--ink)] hover:bg-[color:var(--paper-strong)]",
        ghost:
          "px-3 py-2 text-[color:var(--muted-ink)] hover:bg-[color:var(--paper-strong)] hover:text-[color:var(--ink)]",
      },
      size: {
        default: "h-10",
        sm: "h-8 px-3 text-xs",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export function Button({ className, variant, size, asChild = false, ...props }: ButtonProps) {
  const Comp = asChild ? Slot : "button";
  return <Comp className={cn(buttonVariants({ variant, size, className }))} {...props} />;
}
