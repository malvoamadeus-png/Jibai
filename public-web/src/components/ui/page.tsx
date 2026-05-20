import type * as React from "react";

import { cn } from "@/lib/utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  badges,
  className,
}: {
  eyebrow?: string;
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  badges?: React.ReactNode;
  className?: string;
}) {
  return (
    <Card variant="elevated" className={cn("overflow-hidden", className)}>
      <CardHeader className="gap-5">
        <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
          <div className="space-y-4">
            {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
            {badges ? <div className="flex flex-wrap items-center gap-2">{badges}</div> : null}
            <div className="space-y-2">
              <CardTitle className="text-4xl sm:text-5xl">{title}</CardTitle>
              {description ? <CardDescription className="max-w-3xl text-[15px] leading-7">{description}</CardDescription> : null}
            </div>
          </div>
          {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
        </div>
      </CardHeader>
    </Card>
  );
}

export function StatGrid({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("grid gap-4 md:grid-cols-2 xl:grid-cols-3", className)} {...props} />;
}

export function StatCard({
  label,
  value,
  hint,
  icon,
  className,
}: {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  icon?: React.ReactNode;
  className?: string;
}) {
  return (
    <Card variant="muted" className={cn("overflow-hidden", className)}>
      <CardHeader className="gap-5 pb-4">
        <div className="flex items-center justify-between gap-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[color:var(--soft-ink)]">{label}</p>
          {icon ? <span className="text-[color:var(--accent-strong)]">{icon}</span> : null}
        </div>
        <CardTitle className="text-4xl leading-none">{value}</CardTitle>
      </CardHeader>
      {hint ? (
        <CardContent>
          <p className="text-sm leading-6 text-[color:var(--muted-ink)]">{hint}</p>
        </CardContent>
      ) : null}
    </Card>
  );
}

export function SectionCard({
  title,
  description,
  actions,
  children,
  className,
}: {
  title?: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <Card className={className}>
      {title || description || actions ? (
        <CardHeader className="gap-4">
          <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div>
              {title ? <CardTitle>{title}</CardTitle> : null}
              {description ? <CardDescription>{description}</CardDescription> : null}
            </div>
            {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
          </div>
        </CardHeader>
      ) : null}
      <CardContent className={cn(title || description || actions ? "" : "pt-7", "space-y-4")}>{children}</CardContent>
    </Card>
  );
}
