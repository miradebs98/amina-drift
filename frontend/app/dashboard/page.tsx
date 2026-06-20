import Link from "next/link";
import { listCases } from "@/lib/api";
import { bandForScore, colorsForScore, fmtDate, fmtDelta } from "@/lib/format";
import { ChevronRight } from "lucide-react";
import { AppShell } from "@/components/shell/app-shell";

export default async function DashboardPage() {
  const cases = await listCases();
  // rank by drift magnitude (biggest mover first)
  const ranked = [...cases].sort((a, b) => {
    const da = (a.alert.new_risk_score ?? 0) - (a.alert.old_risk_score ?? 0);
    const db = (b.alert.new_risk_score ?? 0) - (b.alert.old_risk_score ?? 0);
    return db - da;
  });

  return (
    <AppShell title="Portfolio" subtitle="Clients ranked by KYC drift">
      <main className="mx-auto w-full max-w-[1100px] px-6 py-8">
        <h1 className="font-serif text-2xl font-semibold text-ink">Portfolio — ranked by KYC drift</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Customers whose live public profile has diverged most from their onboarding KYC.
        </p>

        <div className="mt-6 overflow-hidden rounded-card border border-surface-line bg-white shadow-card">
          {ranked.map((c, i) => {
            const old = c.alert.old_risk_score ?? c.customer.risk_model.onboarding_score;
            const now = c.alert.new_risk_score ?? old;
            const band = bandForScore(now);
            const col = colorsForScore(now);
            const delta = Math.round(now - old);
            return (
              <Link
                key={c.customer.customer_id}
                href={`/customers/${c.customer.customer_id}`}
                className={`flex items-center gap-4 px-5 py-4 transition-colors hover:bg-surface-subtle ${
                  i > 0 ? "border-t border-surface-line" : ""
                }`}
              >
                <span
                  className="flex size-11 shrink-0 items-center justify-center rounded-full text-sm font-bold tabular"
                  style={{ background: col.bg, color: col.fg }}
                >
                  {now}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-semibold text-ink">{c.customer.legal_name}</div>
                  <div className="truncate text-xs text-ink-muted">
                    {c.customer.entity_profile.legal_form} · {c.customer.entity_profile.country_of_incorporation} ·
                    onboarded {fmtDate(c.customer.onboarded_as_of)}
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="tabular text-sm font-semibold text-risk-high">{fmtDelta(delta)}</span>
                  <span
                    className="rounded-pill px-2.5 py-1 text-xs font-semibold"
                    style={{ background: col.bg, color: col.fg }}
                  >
                    {band}
                  </span>
                  <ChevronRight className="size-4 text-ink-muted" />
                </div>
              </Link>
            );
          })}
        </div>
      </main>
    </AppShell>
  );
}
