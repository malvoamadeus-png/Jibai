import type { StockTimelineDay } from "@/lib/types";
import { EntityDayCard } from "@/components/entity-day-card";

export function StockDayCard({
  day,
  domain = "stock",
}: {
  day: StockTimelineDay;
  domain?: "stock" | "crypto";
}) {
  return <EntityDayCard day={day} domain={domain} />;
}
