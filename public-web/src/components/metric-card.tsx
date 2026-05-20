import { ArrowUpRight } from "lucide-react";

import { StatCard } from "@/components/ui/page";

export function MetricCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint: string;
}) {
  return <StatCard label={label} value={value} hint={hint} icon={<ArrowUpRight className="h-4 w-4" />} />;
}
