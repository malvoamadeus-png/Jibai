import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full border text-sm font-medium transition-all disabled:pointer-events-none disabled:opacity-50 outline-none focus-visible:ring-4 focus-visible:ring-[color:var(--ring)] focus-visible:ring-offset-0",
  {
    variants: {
      variant: {
        primary:
          "border-transparent bg-[linear-gradient(180deg,#1991ff,#0a84ff)] px-4 py-2 text-[color:var(--accent-foreground)] shadow-[0_12px_30px_rgba(10,132,255,0.24)] hover:-translate-y-0.5 hover:bg-[linear-gradient(180deg,#1189fa,#0076eb)]",
        secondary:
          "border-[color:var(--border-strong)] bg-white/80 px-4 py-2 text-[color:var(--ink)] shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] hover:-translate-y-0.5 hover:bg-white",
        ghost: "border-transparent bg-transparent px-3 py-2 text-[color:var(--muted-ink)] hover:bg-white/70 hover:text-[color:var(--ink)]",
        destructive:
          "border-[color:rgba(212,67,67,0.16)] bg-[color:rgba(255,243,243,0.96)] px-4 py-2 text-[color:var(--danger)] hover:-translate-y-0.5 hover:bg-[color:rgba(255,235,235,1)]",
        tinted:
          "border-[color:rgba(10,132,255,0.12)] bg-[color:rgba(234,243,255,0.86)] px-4 py-2 text-[color:var(--accent-strong)] hover:-translate-y-0.5 hover:bg-[color:rgba(226,239,255,1)]",
      },
      size: {
        default: "h-11",
        sm: "h-9 px-3 text-xs",
        icon: "h-11 w-11 p-0",
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
