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
import { AssertionDiff } from "@/components/customers/assertion-diff";
import { DriftLog } from "@/components/governance/drift-log";
import { AuditTrail } from "@/components/governance/audit-trail";
import { AskChat } from "@/components/chat/ask-chat";
import { Card } from "@/components/ui/card";
import { postDecision, revealInternal } from "@/lib/api";
import { fmtDate, eventTypeLabel } from "@/lib/format";
import { maskCustomer, hasRestricted } from "@/lib/policy";
import { DataProtectionBar } from "@/components/governance/data-protection-bar";
import { buildTrajectory, type Frame } from "@/lib/trajectory";
import { AnimatePresence, motion } from "framer-motion";
import { ExternalLink, Newspaper, History, GitCompareArrows, ScrollText, ChevronDown } from "lucide-react";

const MONTH_MS = 30.44 * 864e5;
const PERIOD_PRESETS: { key: string; label: string; months: number | null }[] = [
  { key: "all", label: "Since onboarding", months: null },
  { key: "24m", label: "24m", months: 24 },
  { key: "12m", label: "12m", months: 12 },
  { key: "6m", label: "6m", months: 6 },
  { key: "3m", label: "3m", months: 3 },
];

function SectionTitle({ children, hint }: { children: React.ReactNode; hint?: string }) {
  return (
    <div className="mb-4">
      <h2 className="font-display text-lg font-semibold text-ink">{children}</h2>
      {hint && <p className="text-xs text-ink-muted">{hint}</p>}
    </div>
  );
}

export function ProfileView({ data }: { data: CustomerCase }) {
  const { customer, events, alert, timeline } = data;
  const qc = useQueryClient();
  const [selected, setSelected] = useState<EvidenceEvent | null>(null);
  const [replayIdx, setReplayIdx] = useState<number | null>(null);
  const [twinOpen, setTwinOpen] = useState(false);
  const [driftLogOpen, setDriftLogOpen] = useState(false);

  // governance / HITL
  const [role, setRole] = useState<Role>("analyst");
  const [dispo, setDispo] = useState<DecisionResult | null>(null);

  // data protection: restricted Layer-2 KYC fields are masked until an authorised role reveals
  // them — the reveal is written to the immutable audit log (RBAC-gated server-side).
  const [revealed, setRevealed] = useState(false);
  const [revealing, setRevealing] = useState(false);
  const [revealError, setRevealError] = useState<string | null>(null);
  const viewData = useMemo(
    () => (revealed ? data : { ...data, customer: maskCustomer(customer) }),
    [data, customer, revealed],
  );
  async function handleReveal() {
    setRevealing(true);
    setRevealError(null);
    try {
      const r = await revealInternal({ customerId: customer.customer_id, reviewer: "G. Cozzio", role });
      setRevealed(true);
      toast.success("Restricted KYC data revealed — written to audit log", {
        description: `by G. Cozzio (${role}) · entry ${r.audit_id}`,
      });
      qc.invalidateQueries({ queryKey: ["audit", customer.customer_id] });
    } catch (e) {
      setRevealError(e instanceof Error ? e.message : "Reveal failed");
    } finally {
      setRevealing(false);
    }
  }
  function handleHide() {
    setRevealed(false);
    setRevealError(null);
  }

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

  const { frames, old, now, startT, endT } = useMemo(
    () => buildTrajectory(customer, events, alert, timeline),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [customer.customer_id],
  );

  // user-chosen reference window — scopes both the replay and the before/after comparison
  const periodOptions = useMemo(() => {
    const spanMonths = (endT - startT) / MONTH_MS;
    return PERIOD_PRESETS.filter((p) => p.months === null || p.months < spanMonths - 0.5);
  }, [startT, endT]);
  const [periodKey, setPeriodKey] = useState("all");
  const period = periodOptions.find((p) => p.key === periodKey) ?? periodOptions[0];
  const windowStart = period.months === null ? startT : Math.max(startT, endT - period.months * MONTH_MS);

  // frames + baseline score for the chosen window (synthetic "period start" frame when mid-trajectory)
  const { playFrames, baseOld } = useMemo(() => {
    if (windowStart <= startT) return { playFrames: frames, baseOld: old };
    const before = frames.filter((f) => f.t <= windowStart);
    const b = before.length ? before[before.length - 1].score : old;
    const inWin = frames.filter((f) => f.t > windowStart);
    const baseFrame: Frame = { t: windowStart, score: b, label: "Period start" };
    return { playFrames: [baseFrame, ...inWin], baseOld: b };
  }, [frames, windowStart, startT, old]);

  function changePeriod(k: string) {
    setReplayIdx(null);
    setPeriodKey(k);
  }

  // time-compressed replay: walk the window's key-frames, climbing the score + firing evidence
  const playing = replayIdx !== null;
  useEffect(() => {
    if (replayIdx === null) return;
    const f = playFrames[replayIdx];
    if (f?.event) setSelected(f.event);
    if (replayIdx >= playFrames.length - 1) {
      const t = setTimeout(() => setReplayIdx(null), 2400);
      return () => clearTimeout(t);
    }
    const t = setTimeout(() => setReplayIdx((i) => (i === null ? null : i + 1)), 2600);
    return () => clearTimeout(t);
  }, [replayIdx, playFrames]);

  const currentFrame = playing ? playFrames[replayIdx!] : null;
  const currentScore = currentFrame ? currentFrame.score : now;
  const replayT = currentFrame ? currentFrame.t : null;
  const prevScore = playing && replayIdx! > 0 ? playFrames[replayIdx! - 1].score : baseOld;
  const stepDelta = currentFrame ? currentFrame.score - prevScore : 0;

  return (
    <AppShell title="Risk Profile" subtitle={customer.legal_name}>
      <div className="mx-auto w-full max-w-[1500px] space-y-5 px-6 py-6">
        <ClientSection
          customer={customer}
          alert={alert}
          currentScore={now}
          role={role}
          onRoleChange={setRole}
          dispo={dispo}
          onDispose={handleDispose}
        />

        <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
          <div className="min-w-0 space-y-5">
            {/* RISK HERO */}
            <Card className="rounded-card border-surface-line p-6 shadow-card">
              <ReplayControls
                playing={playing}
                idx={replayIdx ?? 0}
                total={playFrames.length}
                frame={currentFrame}
                onToggle={() => {
                  setSelected(null); // start/stop a replay fresh — no stale selection lingering
                  setReplayIdx((i) => (i === null ? 0 : null));
                }}
                periodOptions={periodOptions}
                periodKey={periodKey}
                onPeriodChange={changePeriod}
              />

              {/* news pop — each public signal surfaces above the dial as it moves the score */}
              <div className="relative mt-4 min-h-[80px]">
                <AnimatePresence mode="wait">
                  {currentFrame ? (
                    <motion.div
                      key={currentFrame.event?.id ?? `${currentFrame.label}-${currentFrame.t}`}
                      initial={{ opacity: 0, y: -8 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -8 }}
                      transition={{ duration: 0.3 }}
                      className={`rounded-md border px-4 py-3 ${
                        currentFrame.event ? "border-teal/30 bg-teal-wash" : "border-surface-line bg-surface-subtle"
                      }`}
                    >
                      {currentFrame.event ? (
                        <>
                          <div className="flex items-center justify-between gap-3">
                            <div className="flex min-w-0 items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-teal-hover">
                              <Newspaper className="size-3.5 shrink-0" />
                              <span>{eventTypeLabel(currentFrame.event.type)}</span>
                              <span className="tabular text-ink-muted">· {fmtDate(currentFrame.event.published_at)}</span>
                            </div>
                            {stepDelta > 0 && (
                              <span className="tabular shrink-0 rounded-pill bg-risk-high-bg px-2 py-0.5 text-xs font-bold text-risk-high">
                                +{Math.round(stepDelta)} → {Math.round(currentFrame.score)}
                              </span>
                            )}
                          </div>
                          <p className="mt-1.5 text-sm font-medium leading-snug text-ink">{currentFrame.event.summary}</p>
                          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-muted">
                            <span>{currentFrame.event.source}</span>
                            {currentFrame.event.source_url ? (
                              <a
                                href={currentFrame.event.source_url}
                                target="_blank"
                                rel="noreferrer"
                                className="inline-flex items-center gap-1 text-teal-hover hover:underline"
                              >
                                source <ExternalLink className="size-3" />
                              </a>
                            ) : null}
                          </div>
                        </>
                      ) : (
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-sm font-medium text-ink">{currentFrame.label}</span>
                          <span className="tabular text-xs text-ink-muted">score {Math.round(currentFrame.score)}</span>
                        </div>
                      )}
                    </motion.div>
                  ) : (
                    <motion.div
                      key="idle"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      className="flex items-center gap-2 rounded-md border border-dashed border-surface-line bg-surface-subtle px-4 py-3 text-xs text-ink-muted"
                    >
                      <Newspaper className="size-3.5 shrink-0" />
                      <span>
                        Press <span className="font-semibold text-ink-body">Replay the drift</span> — each public signal pops up here as it re-tiers the score.
                      </span>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              <div className="mt-4 grid grid-cols-1 items-center gap-6 lg:grid-cols-[1fr_220px]">
                <div className="flex justify-center">
                  <RiskGauge score={currentScore} from={baseOld} confidence={alert.confidence} />
                </div>
                <div className="lg:border-l lg:border-surface-line lg:pl-6">
                  <ScoreComparison
                    compact
                    oldScore={baseOld}
                    newScore={currentScore}
                    driftScore={alert.drift_score}
                    oldLabel="Period start"
                    newLabel="Now"
                  />
                </div>
              </div>
            </Card>

            {/* DRIFT TIMELINE — sits directly under the dial; the replay's marker tracks it */}
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
                timeline={timeline}
                onSelectEvent={setSelected}
                replayT={replayT}
              />

              <div className="mt-4">
                <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-muted">
                  Selected signal{" "}
                  <span className="font-normal normal-case tracking-normal text-ink-muted/70">· click any point on the chart</span>
                </div>
                {selected ? (
                  <div className="flex items-start gap-3 rounded-md border border-teal/30 bg-teal-wash p-3">
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
                        ) : null}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="rounded-md border border-dashed border-surface-line bg-surface-subtle px-3 py-2.5 text-xs text-ink-muted">
                    Click any point on the chart to inspect the public signal behind it.
                  </div>
                )}
              </div>
            </Card>

            {/* TWIN DIFF — perception vs reality (collapsible) */}
            <Card className="rounded-card border-surface-line p-6 shadow-card">
              <button
                onClick={() => setTwinOpen((o) => !o)}
                className="flex w-full items-start justify-between gap-3 text-left"
              >
                <div>
                  <h2 className="font-display text-lg font-semibold text-ink">
                    <span className="inline-flex items-center gap-2">
                      <GitCompareArrows className="size-4 text-ink-muted" /> Last KYC on file → live picture
                    </span>
                  </h2>
                  <p className="text-xs text-ink-muted">
                    What the bank last verified at review on {fmtDate(customer.kyc_review.last_review)} vs. what public
                    intelligence shows today. Contradicted beliefs in red.
                  </p>
                </div>
                <ChevronDown
                  className={`mt-1 size-5 shrink-0 text-ink-muted transition-transform ${twinOpen ? "rotate-180" : ""}`}
                />
              </button>
              <AnimatePresence initial={false}>
                {twinOpen && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2, ease: [0.4, 0, 0.2, 1] }}
                    className="overflow-hidden"
                  >
                    <div className="pt-4">
                      <AssertionDiff data={viewData} onSelectEvent={setSelected} />
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </Card>

            {/* DRIFT LOG / HISTORY (collapsible) */}
            <Card className="rounded-card border-surface-line p-6 shadow-card">
              <button
                onClick={() => setDriftLogOpen((o) => !o)}
                className="flex w-full items-start justify-between gap-3 text-left"
              >
                <div>
                  <h2 className="font-display text-lg font-semibold text-ink">
                    <span className="inline-flex items-center gap-2">
                      <History className="size-4 text-ink-muted" /> Drift &amp; alert history
                    </span>
                  </h2>
                  <p className="text-xs text-ink-muted">
                    The drift the engine flagged, the evidence that drove it, and its disposition — not the raw feed
                    (that&apos;s the News radar).
                  </p>
                </div>
                <ChevronDown
                  className={`mt-1 size-5 shrink-0 text-ink-muted transition-transform ${driftLogOpen ? "rotate-180" : ""}`}
                />
              </button>
              <AnimatePresence initial={false}>
                {driftLogOpen && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2, ease: [0.4, 0, 0.2, 1] }}
                    className="overflow-hidden"
                  >
                    <div className="pt-4">
                      <DriftLog
                        customer={customer}
                        events={events}
                        alert={alert}
                        currentScore={now}
                        dispo={dispo}
                        selectedId={selected?.id}
                        onSelect={setSelected}
                      />
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
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

            {/* DATA PROTECTION — public/internal separation + masked Layer-2 fields (RBAC reveal) */}
            {hasRestricted(customer) && (
              <DataProtectionBar
                customer={customer}
                role={role}
                onRoleChange={setRole}
                revealed={revealed}
                revealing={revealing}
                error={revealError}
                onReveal={handleReveal}
                onHide={handleHide}
              />
            )}
          </div>

          {/* RIGHT RAIL — NEWS / SOCIAL */}
          <div className="xl:sticky xl:top-20 xl:self-start">
            <NewsPanel data={data} />
          </div>
        </div>
      </div>

      {/* floating grounded assistant — always visible. Uses masked data so the chat respects
          need-to-know: it cannot surface restricted KYC fields until they are revealed. */}
      <AskChat data={viewData} />
    </AppShell>
  );
}
