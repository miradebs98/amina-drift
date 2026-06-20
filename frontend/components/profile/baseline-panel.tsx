import type { Customer } from "@/lib/types";
import { colorsForScore } from "@/lib/format";

function val(customer: Customer, predicate: string): string | undefined {
  return customer.assertions.find((a) => a.predicate === predicate)?.value ?? undefined;
}

export function BaselinePanel({ customer }: { customer: Customer }) {
  const onb = customer.risk_model.onboarding_score;
  const c = colorsForScore(onb);

  const facts: { label: string; value?: string }[] = [
    { label: "Declared business", value: val(customer, "business_model") },
    { label: "Source of funds", value: val(customer, "source_of_funds") },
    { label: "Operating geographies", value: val(customer, "operating_geographies") },
    { label: "PEP @ onboarding", value: val(customer, "pep_status") },
    { label: "Sanctions @ onboarding", value: val(customer, "sanctions_status") },
    { label: "Digital-asset policy", value: val(customer, "digital_asset_policy") },
  ];

  return (
    <section className="rounded-card border border-surface-line bg-surface-subtle p-5">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-muted">
          Onboarding baseline — “what we believed then”
        </h2>
        <span
          className="rounded-pill px-2.5 py-0.5 text-xs font-semibold tabular"
          style={{ background: c.bg, color: c.fg }}
        >
          Onboarded {onb} · {customer.risk_model.onboarding_band}
        </span>
      </div>
      <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
        {facts.map((f) => (
          <div key={f.label} className="min-w-0">
            <dt className="text-[11px] uppercase tracking-wide text-ink-muted">{f.label}</dt>
            <dd className="truncate text-sm text-ink" title={f.value}>
              {f.value ?? "—"}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
