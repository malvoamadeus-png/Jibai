import type { ThemeTimelineDay } from "@/lib/types";
import { EntityDayCard } from "@/components/entity-day-card";

export function ThemeDayCard({ day }: { day: ThemeTimelineDay }) {
  return <EntityDayCard day={day} />;
}
