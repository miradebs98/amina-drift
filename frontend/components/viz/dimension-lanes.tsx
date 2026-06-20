"use client";

import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Fingerprint, Share2, Activity, Globe, ChevronDown, Zap } from "lucide-react";
import type { EvidenceEvent, AssertionDrift } from "@/lib/types";
import { toEpoch, fmtDate, fmtMonthYear, predicateLabel } from "@/lib/format";

// The four KYC-drift dimensions, in plain analyst language. Lit lanes are the ones that drove the
// alert (the engine's breadth set); the story is the COMBINATION across them.
const LANES = [
  { key: "identity_ownership", label: "Identity & Ownership", sub: "who they are / who owns them", icon: Fingerprint },
  { key: "network_risk", label: "Network Risk", sub: "who they're connected to", icon: Share2 },
  { key: "behavioural_drift", label: "Behavioural Drift", sub: "what their money does", icon: Activity },
  { key: "contextual_change", label: "Contextual Change", sub: "their business & context", icon: Globe },
] as const;

export function DimensionLanes({
  events,
  dimensionsDrifted = [],
  breadth = 0,
  assertionDrift = [],
  selectedId,
  onSelectEvent,
  replayT,
}: {
  events: EvidenceEvent[];
  dimensionsDrifted?: string[];
  breadth?: number;
  assertionDrift?: AssertionDrift[];
  selectedId?: string | null;
  onSelectEvent?: (e: EvidenceEvent) => void;
  replayT?: number | null;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const lit = useMemo(() => new Set(dimensionsDrifted), [dimensionsDrifted]);
  const eventById = useMemo(() => new Map(events.map((e) => [e.id, e])), [events]);

  // shared time axis across all lanes
  const { minT, span, ticks } = useMemo(() => {
    const ts = events.map((e) => toEpoch(e.published_at)).filter(Boolean);
    const lo = ts.length ? Math.min(...ts) : 0;
    const hi = ts.length ? Math.max(...ts) : 1;
    const s = Math.max(1, hi - lo);
    const t = Array.from({ length: 4 }, (_, i) => lo + (i / 3) * s); // 4 evenly-spaced date ticks
    return { minT: lo, span: s, ticks: t };
  }, [events]);
  const xpct = (t: number) => 3 + ((t - minT) / span) * 94; // 3%..97%

  // Per lane: the BELIEFS that drifted in this dimension, and the SIGNALS (evidence events) behind
  // them — so the dots are exactly the evidence for the beliefs you see when you expand.
  const lanes = useMemo(() => {
    return LANES.map((L) => {
      const beliefs = assertionDrift.filter((a) => a.dimension === L.key);
      const sigIds = new Set<string>();
      beliefs.forEach((b) => b.evidence_ids.forEach((id) => sigIds.add(id)));
      const signals = [...sigIds].map((id) => eventById.get(id)).filter((e): e is EvidenceEvent => Boolean(e));
      return { ...L, beliefs, signals, on: lit.has(L.key) };
    });
  }, [assertionDrift, eventById, lit]);

  return (
    <div className="flex flex-col gap-4">
      {/* breadth headline */}
      {breadth >= 3 ? (
        <div className="flex items-start gap-2 rounded-md bg-risk-high-bg px-3 py-2.5 text-sm font-medium text-risk-high">
          <Zap className="mt-0.5 size-4 shrink-0" />
          <span>
            {breadth} of 4 dimensions converging — combination drift. No single signal crossed a
            threshold; together they re-rate the client.
          </span>
        </div>
      ) : (
        <p className="text-xs text-ink-muted">
          <span className="font-semibold text-ink tabular">{breadth}</span> of 4 risk dimensions
          moved. KYC drift is the <span className="font-medium text-ink">combination</span> across
          dimensions over time — lit lanes drove the alert.
        </p>
      )}
      <p className="-mt-1 text-[11px] text-ink-muted">
        Each <span className="inline-block size-2 translate-y-px rounded-full bg-teal align-middle" /> is a
        public signal on the timeline; one signal can contradict several on-file beliefs. Click a lane for the beliefs + dates.
      </p>

      {/* the four lanes */}
      <div className="divide-y divide-surface-line overflow-hidden rounded-md border border-surface-line">
        {lanes.map(({ key, label, sub, icon: Icon, on, beliefs, signals }) => {
          const expanded = open === key;
          return (
            <div key={key} className={on ? "bg-teal-wash/40" : ""}>
              <div className="grid grid-cols-[210px_1fr] items-center gap-3 px-3 py-2.5">
                {/* lane label */}
                <button
                  onClick={() => beliefs.length && setOpen(expanded ? null : key)}
                  className="flex items-center gap-2.5 text-left disabled:cursor-default"
                  disabled={!beliefs.length}
                >
                  <span
                    className={`grid size-8 shrink-0 place-items-center rounded-md ${
                      on ? "bg-teal text-white" : "bg-surface-card text-ink-muted"
                    }`}
                  >
                    <Icon className="size-4" />
                  </span>
                  <span className="min-w-0">
                    <span className={`block truncate text-[13px] font-medium ${on ? "text-ink" : "text-ink-muted"}`}>
                      {label}
                    </span>
                    <span className="block truncate text-[11px] text-ink-muted">
                      {on ? (
                        <>
                          <span className="font-medium text-ink-body">{beliefs.length}</span> belief
                          {beliefs.length !== 1 ? "s" : ""} ·{" "}
                          <span className="font-medium text-ink-body">{signals.length}</span> signal
                          {signals.length !== 1 ? "s" : ""}
                        </>
                      ) : (
                        sub
                      )}
                    </span>
                  </span>
                  {beliefs.length > 0 && (
                    <ChevronDown className={`ml-auto size-3.5 shrink-0 text-ink-muted transition-transform ${expanded ? "rotate-180" : ""}`} />
                  )}
                </button>

                {/* the time track + signal dots (evidence behind this lane's beliefs) */}
                <div className="relative h-8">
                  <div className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-surface-line" />
                  {signals.map((e) => {
                    const t = toEpoch(e.published_at);
                    const future = replayT != null && t > replayT;
                    const sel = selectedId === e.id;
                    return (
                      <button
                        key={e.id}
                        title={`${fmtDate(e.published_at)} · ${e.summary}`}
                        onClick={() => onSelectEvent?.(e)}
                        style={{ left: `${xpct(t)}%` }}
                        className={`absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border transition-all hover:scale-125 ${
                          sel ? "z-10 scale-125 ring-2 ring-teal ring-offset-1" : ""
                        } ${
                          future
                            ? "border-surface-line bg-white opacity-40"
                            : on
                              ? "border-teal-hover bg-teal"
                              : "border-ink-muted bg-surface-card"
                        }`}
                      />
                    );
                  })}
                </div>
              </div>

              {/* expand: ALL beliefs that moved here, each with the signal date(s) behind it */}
              <AnimatePresence initial={false}>
                {expanded && beliefs.length > 0 && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.18, ease: [0.4, 0, 0.2, 1] }}
                    className="overflow-hidden"
                  >
                    <div className="grid gap-1.5 px-3 pb-3 pl-[58px]">
                      {beliefs.map((a) => {
                        const evs = a.evidence_ids.map((id) => eventById.get(id)).filter((e): e is EvidenceEvent => Boolean(e));
                        const dates = [...new Set(evs.map((e) => fmtDate(e.published_at)))];
                        return (
                          <button
                            key={a.assertion_id}
                            onClick={() => evs[0] && onSelectEvent?.(evs[0])}
                            className="rounded-md bg-surface-subtle px-2.5 py-1.5 text-left hover:bg-surface-card"
                          >
                            <div className="flex items-baseline justify-between gap-2">
                              <span className="text-[13px] font-medium text-ink">
                                {predicateLabel(a.predicate)}
                                <span className="font-normal text-ink-muted"> — {a.status}</span>
                              </span>
                              {dates.length > 0 && (
                                <span className="shrink-0 tabular text-[10px] text-ink-muted">{dates.slice(0, 2).join(" · ")}</span>
                              )}
                            </div>
                            {a.why?.[0] && <div className="mt-0.5 text-[11px] leading-snug text-ink-body">{a.why[0]}</div>}
                          </button>
                        );
                      })}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}

        {/* shared date axis (aligned to the track column) */}
        <div className="grid grid-cols-[210px_1fr] gap-3 px-3 py-1.5">
          <div />
          <div className="relative h-4">
            {ticks.map((t, i) => (
              <span
                key={i}
                style={{ left: `${xpct(t)}%` }}
                className="absolute -translate-x-1/2 tabular text-[10px] text-ink-muted"
              >
                {fmtMonthYear(new Date(t).toISOString())}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
