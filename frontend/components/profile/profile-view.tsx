"use client";

import { useState } from "react";
import type { CustomerCase, EvidenceEvent } from "@/lib/types";
import { AppShell } from "@/components/shell/app-shell";
import { ClientSection } from "./client-section";
import { BaselinePanel } from "./baseline-panel";
import { NewsPanel } from "./news-panel";
import { RiskGauge } from "@/components/viz/risk-gauge";
import { ScoreComparison } from "@/components/viz/score-comparison";
import { DriftScoreOverTime } from "@/components/viz/drift-score-line";
import { DriftLog } from "@/components/governance/drift-log";
import { Card } from "@/components/ui/card";
import { fmtDate, eventTypeLabel } from "@/lib/format";
import { ExternalLink, TrendingUp, History } from "lucide-react";

function SectionTitle({ children, hint }: { children: React.ReactNode; hint?: string }) {
  return (
    <div className="mb-4">
      <h2 className="font-serif text-lg font-semibold text-ink">{children}</h2>
      {hint && <p className="text-xs text-ink-muted">{hint}</p>}
    </div>
  );
}

export function ProfileView({ data }: { data: CustomerCase }) {
  const { customer, events, alert } = data;
  const [selected, setSelected] = useState<EvidenceEvent | null>(null);

  const old = alert.old_risk_score ?? customer.risk_model.onboarding_score;
  const now = alert.new_risk_score ?? old;
  const drivers = alert.evidence_ids
    .map((id) => events.find((e) => e.id === id))
    .filter((e): e is EvidenceEvent => Boolean(e));

  return (
    <AppShell title="Risk Profile" subtitle={customer.legal_name}>
      <div className="mx-auto w-full max-w-[1500px] space-y-5 px-6 py-6">
        {/* CLIENT SECTION */}
        <ClientSection customer={customer} alert={alert} />

        {/* ONBOARDING BASELINE */}
        <BaselinePanel customer={customer} />

        <div className="grid grid-cols-1 gap-5 xl:grid-cols-[1fr_340px]">
          {/* CENTER COLUMN */}
          <div className="space-y-5">
            {/* RISK HERO */}
            <Card className="rounded-card border-surface-line p-6 shadow-card">
              <div className="grid grid-cols-1 items-center gap-6 lg:grid-cols-[300px_1px_1fr]">
                <div className="flex justify-center">
                  <RiskGauge score={now} from={old} confidence={alert.confidence} />
                </div>
                <div className="hidden h-full w-px bg-surface-line lg:block" />
                <div className="flex flex-col gap-4">
                  <ScoreComparison oldScore={old} newScore={now} driftScore={alert.drift_score} />
                  <div className="rounded-md bg-surface-subtle p-3">
                    <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">{alert.flag}</div>
                    <p className="text-sm leading-relaxed text-ink-body">{alert.rationale}</p>
                  </div>
                </div>
              </div>

              <div className="mt-5 border-t border-surface-line pt-4">
                <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">
                  <TrendingUp className="size-3.5" /> Score drivers — each links to its evidence
                </div>
                <div className="flex flex-wrap gap-2">
                  {drivers.map((e) => (
                    <button
                      key={e.id}
                      title={e.id}
                      onClick={() => setSelected(e)}
                      className={`group inline-flex items-center gap-2 rounded-pill border px-3 py-1 text-xs transition-colors ${
                        selected?.id === e.id
                          ? "border-teal bg-teal-wash text-teal-hover"
                          : "border-surface-line bg-white text-ink-body hover:border-teal hover:bg-teal-wash"
                      }`}
                    >
                      <span className="font-medium">{eventTypeLabel(e.type)}</span>
                      <span className="max-w-[200px] truncate text-ink-muted">{e.summary}</span>
                    </button>
                  ))}
                </div>
              </div>
            </Card>

            {/* DRIFT TIMELINE */}
            <Card className="rounded-card border-surface-line p-6 shadow-card">
              <SectionTitle
                hint={`The scheduled review would not run until ${fmtDate(
                  customer.kyc_review.next_periodic_review,
                )} — the divergence accumulated silently before then.`}
              >
                Risk-score drift over time
              </SectionTitle>
              <DriftScoreOverTime customer={customer} events={events} alert={alert} onSelectEvent={setSelected} />

              {selected && (
                <div className="mt-4 flex items-start gap-3 rounded-md border border-teal/30 bg-teal-wash p-3">
                  <span className="mt-0.5 rounded bg-white px-1.5 py-0.5 text-[11px] font-semibold text-teal-hover">
                    {eventTypeLabel(selected.type)}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-ink">{selected.summary}</div>
                    <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-muted">
                      <span className="tabular">{fmtDate(selected.published_at)}</span>
                      <span>{selected.source}</span>
                      {selected.source_url ? (
                        <a
                          href={selected.source_url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 text-teal-hover hover:underline"
                        >
                          source <ExternalLink className="size-3" />
                        </a>
                      ) : (
                        <span className="rounded-pill bg-risk-med-bg px-2 py-0.5 text-[10px] font-medium text-risk-med">
                          SIMULATED
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </Card>

            {/* DRIFT LOG / HISTORY */}
            <Card className="rounded-card border-surface-line p-6 shadow-card">
              <SectionTitle hint="Every signal the engine flagged for this client, newest first — the auditable record.">
                <span className="inline-flex items-center gap-2">
                  <History className="size-4 text-ink-muted" /> Drift &amp; alert history
                </span>
              </SectionTitle>
              <DriftLog
                customer={customer}
                events={events}
                alert={alert}
                selectedId={selected?.id}
                onSelect={setSelected}
              />
            </Card>
          </div>

          {/* RIGHT RAIL — NEWS / SOCIAL */}
          <div className="xl:sticky xl:top-20 xl:self-start">
            <NewsPanel data={data} />
          </div>
        </div>
      </div>
    </AppShell>
  );
}
