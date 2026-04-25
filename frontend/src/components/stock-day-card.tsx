import type { StockTimelineDay } from "@/lib/types";
import { EntityDayCard } from "@/components/entity-day-card";

export function StockDayCard({ day }: { day: StockTimelineDay }) {
  return <EntityDayCard day={day} />;
}
