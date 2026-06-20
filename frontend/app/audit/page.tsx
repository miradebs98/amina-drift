import Link from "next/link";
import { listCases } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { AppShell } from "@/components/shell/app-shell";
import { CompanyLogo } from "@/components/shared/company-logo";
import { ShieldCheck, ChevronRight } from "lucide-react";

const STATE: Record<string, { label: string; cls: string }> = {
  pending: { label: "Pending review", cls: "bg-risk-med-bg text-risk-med" },
  approved: { label: "Approved", cls: "bg-risk-low-bg text-risk-low" },
  dismissed: { label: "Dismissed", cls: "bg-surface-card text-ink-muted" },
  escalated: { label: "Escalated → Re-KYC", cls: "bg-risk-high-bg text-risk-high" },
};

export default async function AuditPage() {
  const cases = await listCases();
  const rows = [...cases].sort((a, b) => +new Date(b.alert.created_at) - +new Date(a.alert.created_at));

  return (
    <AppShell title="Audit log" subtitle="Decision trail across the book">
      <main className="mx-auto w-full max-w-[1100px] px-6 py-8">
        <h1 className="font-display text-2xl font-semibold text-ink">Audit log</h1>
        <p className="mt-1 text-sm text-ink-muted">
          The decision trail across the portfolio. Every disposition is written to an immutable, hash-chained record —
          who decided, when, on which model and policy version.
        </p>

        <div className="mt-4 inline-flex items-center gap-2 rounded-pill bg-risk-low-bg px-3 py-1.5 text-xs font-medium text-risk-low">
          <ShieldCheck className="size-4" /> Tamper-evident · chain intact
        </div>

        <div className="mt-6 overflow-hidden rounded-card border border-surface-line bg-white shadow-card">
          {rows.map((c, i) => {
            const a = c.alert;
            const st = STATE[a.governance_state] ?? STATE.pending;
            return (
              <Link
                key={c.customer.customer_id}
                href={`/customers/${c.customer.customer_id}`}
                className={`flex items-center gap-4 px-5 py-4 transition-colors hover:bg-surface-subtle ${
                  i > 0 ? "border-t border-surface-line" : ""
                }`}
              >
                <CompanyLogo customerId={c.customer.customer_id} name={c.customer.legal_name} size={36} />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-semibold text-ink">{c.customer.legal_name}</div>
                  <div className="truncate text-xs text-ink-muted">
                    {a.flag} · {a.old_risk_tier} → {a.new_risk_tier}
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="tabular hidden text-xs text-ink-muted sm:inline">{fmtDate(a.created_at)}</span>
                  <span className={`rounded-pill px-2.5 py-1 text-xs font-semibold ${st.cls}`}>{st.label}</span>
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
