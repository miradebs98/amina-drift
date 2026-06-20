import { listCases } from "@/lib/api";
import { AppShell } from "@/components/shell/app-shell";
import { AlertsView } from "@/components/alerts/alerts-view";

export default async function AlertsPage() {
  const cases = await listCases();
  return (
    <AppShell title="Alerts" subtitle="What changed, per client">
      <AlertsView cases={cases} />
    </AppShell>
  );
}
