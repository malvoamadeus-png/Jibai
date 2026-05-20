import Link from "next/link";
import { DatabaseZap } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export function EmptyState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <Card variant="muted" className="border-dashed">
      <CardHeader>
        <div className="inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-[color:rgba(10,132,255,0.1)] text-[color:var(--accent-strong)]">
          <DatabaseZap className="h-5 w-5" />
        </div>
        <CardTitle className="mt-4">{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <Button asChild variant="secondary">
          <Link href="/">返回总览</Link>
        </Button>
      </CardContent>
    </Card>
  );
}
