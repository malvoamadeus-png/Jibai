import { Badge } from "@/components/ui/badge";

export function StatusBadge({
  status,
}: {
  status: "has_update_today" | "no_update_today" | "crawl_failed" | string | null;
}) {
  if (status === "has_update_today") {
    return <Badge variant="positive">有更新</Badge>;
  }
  if (status === "no_update_today") {
    return <Badge variant="neutral">今日无更新</Badge>;
  }
  if (status === "crawl_failed") {
    return <Badge variant="danger">抓取失败</Badge>;
  }
  return <Badge variant="neutral">{status || "未知状态"}</Badge>;
}
