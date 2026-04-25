import { ControlPanel } from "@/components/control-panel";
import { getControlPanelData } from "@/lib/control";

export const dynamic = "force-dynamic";

export default function ControlPage() {
  const data = getControlPanelData();
  return <ControlPanel initialData={data} />;
}
