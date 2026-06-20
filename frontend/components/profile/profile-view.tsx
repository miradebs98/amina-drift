"use client";

import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import type { CustomerCase, EvidenceEvent, Role, DecisionAction, DecisionResult } from "@/lib/types";
import { AppShell } from "@/components/shell/app-shell";
import { ClientSection } from "./client-section";
import { NewsPanel } from "./news-panel";
import { ReplayControls } from "./replay-controls";
import { RiskGauge } from "@/components/viz/risk-gauge";
import { ScoreComparison } from "@/components/viz/score-comparison";
import { DriftScoreOverTime } from "@/components/viz/drift-score-line";
import { DimensionLanes } from "@/components/viz/dimension-lanes";
import { AssertionDiff } from "@/components/customers/assertion-diff";
import { DriftLog } from "@/components/governance/drift-log";
import { AuditTrail } from "@/components/governance/audit-trail";
import { AskChat } from "@/components/chat/ask-chat";
import { Card } from "@/components/ui/card";
import { postDecision } from "@/lib/api";
import { fmtDate, eventTypeLabel } from "@/lib/format";
import { buildTrajectory } from "@/lib/trajectory";
import { ExternalLink, TrendingUp, History, GitCompareArrows, ScrollText, Layers } from "lucide-react";

function SectionTitle({ children, hint }: { children: React.ReactNode; hint?: string }) {
  return (
    <div className="mb-4">
      <h2 className="font-display text-lg font-semibold text-ink">{children}</h2>
      {hint && <p className="text-xs text-ink-muted">{hint}</p>}
    </div>
  );
}

export function ProfileView({ data }: { data: CustomerCase }) {
  const { customer, events, alert, dimensions_drifted, breadth, assertion_drift } = data;
  const qc = useQueryClient();
  const [selected, setSelected] = useState<EvidenceEvent | null>(null);
  const [replayIdx, setReplayIdx] = useState<number | null>(null);

  // governance / HITL
  const [role, setRole] = useState<Role>("analyst");
  const [dispo, setDispo] = useState<DecisionResult | null>(null);
  async function handleDispose(action: DecisionAction, note: string) {
    const r = await postDecision({
      alert_id: alert.id,
      action,
      reviewer: "G. Cozzio",
      role,
      note,
      customer_id: customer.customer_id,
      severity: alert.severity,
    });
    setDispo(r);
    const verb = action === "approve" ? "Approved" : action === "override" ? "Overridden" : "Escalated";
    toast.success(`${verb} — written to audit log`, { description: `by G. Cozzio (${role}) · entry ${r.audit_id}` });
    qc.invalidateQueries({ queryKey: ["audit", customer.customer_id] });
  }

  const { frames, old, now } = useMemo(
    () => buildTrajectory(customer, events, alert),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [customer.customer_id],
  );

  // time-compressed replay: walk the key-frames, climbing the score + firing evidence
  const playing = replayIdx !== null;
  useEffect(() => {
    if (replayIdx === null) return;
    const f = frames[replayIdx];
    if (f?.event) setSelected(f.event);
    if (replayIdx >= frames.length - 1) {
      const t = setTimeout(() => setReplayIdx(null), 1800);
      return () => clearTimeout(t);
    }
    const t = setTimeout(() => setReplayIdx((i) => (i === null ? null : i + 1)), 1500);
    return () => clearTimeout(t);
  }, [replayIdx, frames]);

  const currentScore = playing ? frames[replayIdx!].score : now;
  const replayT = playing ? frames[replayIdx!].t : null;

  const drivers = alert.evidence_ids
    .map((id) => events.find((e) => e.id === id))
    .filter((e): e is EvidenceEvent => Boolean(e));

  return (
    <AppShell title="Risk Profile" subtitle={customer.legal_name}>
      <div className="mx-auto w-full max-w-[1500px] space-y-5 px-6 py-6">
        <ClientSection
          customer={customer}
          alert={alert}
          role={role}
          onRoleChange={setRole}
          dispo={dispo}
          onDispose={handleDispose}
        />

        <div className="grid grid-cols-1 gap-5 xl:grid-cols-[1fr_340px]">
          <div className="space-y-5">
            {/* RISK HERO */}
            <Card className="rounded-card border-surface-line p-6 shadow-card">
              <ReplayControls
                playing={playing}
                idx={replayIdx ?? 0}
                total={frames.length}
                frame={playing ? frames[replayIdx!] : null}
                onToggle={() => setReplayIdx((i) => (i === null ? 0 : null))}
              />
              <div className="mt-5 grid grid-cols-1 items-center gap-6 lg:grid-cols-[300px_1px_1fr]">
                <div className="flex justify-center">
                  <RiskGauge score={currentScore} from={old} confidence={alert.confidence} />
                </div>
                <div className="hidden h-full w-px bg-surface-line lg:block" />
                <div className="flex flex-col gap-4">
                  <ScoreComparison oldScore={old} newScore={currentScore} driftScore={alert.drift_score} />
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

            {/* DIMENSION CONVERGENCE — connect the dots across the 4 risk dimensions */}
            <Card className="rounded-card border-surface-line p-6 shadow-card">
              <SectionTitle hint="No single signal crosses a threshold — KYC drift is several kinds of change moving together. Lit lanes drove the alert.">
                <span className="inline-flex items-center gap-2">
                  <Layers className="size-4 text-ink-muted" /> Dimension convergence
                </span>
              </SectionTitle>
              <DimensionLanes
                events={events}
                dimensionsDrifted={dimensions_drifted}
                breadth={breadth}
                assertionDrift={assertion_drift}
                selectedId={selected?.id}
                onSelectEvent={setSelected}
                replayT={replayT}
              />
            </Card>

            {/* TWIN DIFF — perception vs reality */}
            <Card className="rounded-card border-surface-line p-6 shadow-card">
              <SectionTitle hint="The bank's onboarding KYC belief vs. what public intelligence shows now. Contradicted beliefs in red.">
                <span className="inline-flex items-center gap-2">
                  <GitCompareArrows className="size-4 text-ink-muted" /> Onboarding twin vs. live twin
                </span>
              </SectionTitle>
              <AssertionDiff data={data} onSelectEvent={setSelected} />
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
              <DriftScoreOverTime
                customer={customer}
                events={events}
                alert={alert}
                onSelectEvent={setSelected}
                replayT={replayT}
              />

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

            {/* AUDIT TRAIL — immutable, hash-chained, tamper-evident */}
            <Card className="rounded-card border-surface-line p-6 shadow-card">
              <SectionTitle hint="Immutable, hash-chained record of every decision — reconstruct exactly why this client was re-tiered, by whom, with which model.">
                <span className="inline-flex items-center gap-2">
                  <ScrollText className="size-4 text-ink-muted" /> Audit trail &amp; integrity
                </span>
              </SectionTitle>
              <AuditTrail customerId={customer.customer_id} alertId={alert.id} />
            </Card>
          </div>

          {/* RIGHT RAIL — NEWS / SOCIAL */}
          <div className="xl:sticky xl:top-20 xl:self-start">
            <NewsPanel data={data} />
          </div>
        </div>
      </div>

      {/* floating grounded assistant — always visible */}
      <AskChat data={data} />
    </AppShell>
  );
}
