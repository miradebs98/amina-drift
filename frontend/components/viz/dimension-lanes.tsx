"use client";

import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Fingerprint, Share2, Activity, Globe, ChevronDown, Zap } from "lucide-react";
import type { EvidenceEvent, AssertionDrift } from "@/lib/types";
import { toEpoch, fmtDate, predicateLabel } from "@/lib/format";

// The four KYC-drift dimensions — in plain analyst language. Lit lanes are the ones that drove
// the alert (the engine's own breadth set); the story is the COMBINATION across them.
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

  const { minT, span } = useMemo(() => {
    const ts = events.map((e) => toEpoch(e.published_at)).filter(Boolean);
    const lo = ts.length ? Math.min(...ts) : 0;
    const hi = ts.length ? Math.max(...ts) : 1;
    return { minT: lo, span: Math.max(1, hi - lo) };
  }, [events]);
  const xpct = (t: number) => 3 + ((t - minT) / span) * 94; // 3%..97%

  const byDim = useMemo(() => {
    const m: Record<string, EvidenceEvent[]> = {};
    for (const e of events) {
      if (!e.dimension) continue;
      (m[e.dimension] ??= []).push(e);
    }
    return m;
  }, [events]);

  return (
    <div className="flex flex-col gap-4">
      {/* breadth headline — the connect-the-dots message */}
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

      {/* the four lanes */}
      <div className="divide-y divide-surface-line overflow-hidden rounded-md border border-surface-line">
        {LANES.map(({ key, label, sub, icon: Icon }) => {
          const on = lit.has(key);
          const evs = byDim[key] ?? [];
          const moved = assertionDrift.filter((a) => a.dimension === key);
          const expanded = open === key;
          return (
            <div key={key} className={on ? "bg-teal-wash/40" : ""}>
              <div className="grid grid-cols-[190px_1fr] items-center gap-3 px-3 py-2.5">
                {/* lane label (click to see which beliefs moved) */}
                <button
                  onClick={() => moved.length && setOpen(expanded ? null : key)}
                  className="flex items-center gap-2.5 text-left disabled:cursor-default"
                  disabled={!moved.length}
                >
                  <span
                    className={`grid size-8 shrink-0 place-items-center rounded-md ${
                      on ? "bg-teal text-white" : "bg-surface-card text-ink-muted"
                    }`}
                  >
                    <Icon className="size-4" />
                  </span>
                  <span className="min-w-0">
                    <span className={`block truncate text-sm font-medium ${on ? "text-ink" : "text-ink-muted"}`}>
                      {label}
                    </span>
                    <span className="block truncate text-[11px] text-ink-muted">
                      {on ? `${moved.length} belief${moved.length !== 1 ? "s" : ""} moved` : sub}
                    </span>
                  </span>
                  {moved.length > 0 && (
                    <ChevronDown className={`ml-auto size-3.5 shrink-0 text-ink-muted transition-transform ${expanded ? "rotate-180" : ""}`} />
                  )}
                </button>

                {/* the time track + event dots */}
                <div className="relative h-8">
                  <div className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-surface-line" />
                  {evs.map((e) => {
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

              {/* expand: WHICH beliefs moved in this dimension (the "why") */}
              <AnimatePresence initial={false}>
                {expanded && moved.length > 0 && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.18, ease: [0.4, 0, 0.2, 1] }}
                    className="overflow-hidden"
                  >
                    <div className="grid gap-1.5 px-3 pb-3 pl-[58px]">
                      {moved.slice(0, 5).map((a) => (
                        <div key={a.assertion_id} className="rounded-md bg-surface-subtle px-2.5 py-1.5">
                          <div className="text-[13px] font-medium text-ink">
                            {predicateLabel(a.predicate)}
                            <span className="font-normal text-ink-muted"> — {a.status}</span>
                          </div>
                          {a.why?.[0] && <div className="mt-0.5 text-[11px] leading-snug text-ink-body">{a.why[0]}</div>}
                        </div>
                      ))}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </div>
    </div>
  );
}
