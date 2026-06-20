"use client";

import { useMemo, useState } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceArea,
  ReferenceLine,
  ReferenceDot,
} from "recharts";
import type { DriftAlert, EvidenceEvent, Customer } from "@/lib/types";
import { fmtDate, fmtMonthYear, toEpoch, bandForScore, colorsForScore, eventTypeLabel } from "@/lib/format";

const PERIODS = [
  { key: "1d", label: "1D", ms: 864e5 },
  { key: "1w", label: "1W", ms: 7 * 864e5 },
  { key: "1m", label: "1M", ms: 30 * 864e5 },
  { key: "1y", label: "1Y", ms: 365 * 864e5 },
  { key: "all", label: "ALL", ms: Infinity },
] as const;

// how hard each signal type pushes the score (drives spike size)
const IMPACT: Record<string, number> = {
  sanctions_hit: 3.5,
  pep_hit: 3,
  ownership_change: 3,
  news: 2.6,
  transaction: 2.2,
  website_change: 2,
  registry_change: 1.8,
  funding: 1.3,
};

// deterministic PRNG so SSR and client render identical wander (no hydration drift)
function mulberry32(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function seedFrom(s: string) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return h >>> 0;
}

type Pt = { t: number; estimate: number; eventId?: string; kind?: "endpoint" | "event" };

export function DriftScoreOverTime({
  customer,
  events,
  alert,
  onSelectEvent,
}: {
  customer: Customer;
  events: EvidenceEvent[];
  alert: DriftAlert;
  onSelectEvent?: (e: EvidenceEvent) => void;
}) {
  const [period, setPeriod] = useState<(typeof PERIODS)[number]["key"]>("all");

  const old = alert.old_risk_score ?? customer.risk_model.onboarding_score;
  const now = alert.new_risk_score ?? old;
  const startT = toEpoch(customer.onboarded_as_of);
  const endT = Math.max(toEpoch(alert.created_at), ...events.map((e) => toEpoch(e.published_at)));
  const reviewT = toEpoch(customer.kyc_review.next_periodic_review);

  // Build a varied, event-weighted trajectory between the two REAL endpoints.
  // Big-impact signals create sudden spikes; quiet stretches drift gently.
  const series: Pt[] = useMemo(() => {
    const rand = mulberry32(seedFrom(customer.customer_id));
    const ev = [...events]
      .filter((e) => toEpoch(e.published_at) > startT && toEpoch(e.published_at) < endT)
      .sort((a, b) => toEpoch(a.published_at) - toEpoch(b.published_at));

    const weights = ev.map((e) => IMPACT[e.type] ?? 2);
    const totalW = weights.reduce((s, w) => s + w, 0) || 1;
    const span = now - old;

    const pts: Pt[] = [{ t: startT, estimate: old, kind: "endpoint" }];
    let cum = old;
    let lastT = startT;

    ev.forEach((e, i) => {
      const t = toEpoch(e.published_at);
      const target = old + (span * weights.slice(0, i + 1).reduce((s, w) => s + w, 0)) / totalW;

      // a "shoulder" just before the event = gentle wander on the prior level
      const shoulderT = Math.min(t - 9 * 864e5, (lastT + t) / 2);
      if (shoulderT > lastT) {
        const wander = cum + (rand() - 0.45) * 3; // ±~1.5 noise
        pts.push({ t: shoulderT, estimate: Math.max(old, Math.min(now, Math.round(wander))) });
      }
      // the jump itself (sharp for high impact, soft for low)
      cum = target;
      pts.push({ t, estimate: Math.round(Math.max(old, Math.min(now, cum))), eventId: e.id, kind: "event" });
      lastT = t;
    });

    pts.push({ t: endT, estimate: now, kind: "endpoint" });
    return pts;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customer.customer_id]);

  const sel = PERIODS.find((p) => p.key === period)!;
  const domain: [number, number] =
    sel.ms === Infinity
      ? [startT, Math.max(endT, reviewT) + 15 * 864e5]
      : [endT - sel.ms, Math.max(endT, reviewT)];

  const eventById = useMemo(() => new Map(events.map((e) => [e.id, e])), [events]);
  const cOld = colorsForScore(old);
  const cNow = colorsForScore(now);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs text-ink-muted">
          <span className="inline-block h-0 w-5 border-t-2 border-dashed border-teal" />
          modelled trajectory <span className="text-ink-muted/70">(engine estimate · endpoints measured)</span>
        </div>
        <div className="flex overflow-hidden rounded-md border border-surface-line">
          {PERIODS.map((p) => (
            <button
              key={p.key}
              onClick={() => setPeriod(p.key)}
              className={`px-2.5 py-1 text-xs font-medium transition-colors ${
                period === p.key ? "bg-brand text-white" : "bg-white text-ink-muted hover:bg-surface-subtle"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart data={series} margin={{ top: 16, right: 16, bottom: 8, left: -8 }}>
          <ReferenceArea y1={0} y2={33} fill="#15803d" fillOpacity={0.05} />
          <ReferenceArea y1={33} y2={66} fill="#b45309" fillOpacity={0.05} />
          <ReferenceArea y1={66} y2={100} fill="#b91c1c" fillOpacity={0.06} />
          <ReferenceLine y={33} stroke="#e5e7eb" strokeDasharray="2 4" />
          <ReferenceLine y={66} stroke="#e5e7eb" strokeDasharray="2 4" />

          <CartesianGrid vertical={false} stroke="#f1f3f5" />
          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={domain}
            tickFormatter={fmtMonthYear}
            tick={{ fontSize: 11, fill: "#9ca3af", fontFamily: "var(--font-mono)" }}
            tickLine={false}
            axisLine={{ stroke: "#e5e7eb" }}
            allowDataOverflow
          />
          <YAxis
            domain={[0, 100]}
            ticks={[0, 33, 66, 100]}
            tick={{ fontSize: 11, fill: "#9ca3af", fontFamily: "var(--font-mono)" }}
            tickLine={false}
            axisLine={false}
            width={42}
          />

          <ReferenceLine
            x={reviewT}
            stroke="#6b7280"
            strokeDasharray="5 4"
            label={{ value: "scheduled review", position: "top", fontSize: 10, fill: "#6b7280" }}
          />

          <Tooltip
            cursor={{ stroke: "#cbd5e1", strokeWidth: 1 }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const p = payload[0].payload as Pt;
              const e = p.eventId ? eventById.get(p.eventId) : undefined;
              return (
                <div className="max-w-xs rounded-md border border-surface-line bg-white p-3 shadow-card">
                  <div className="tabular text-xs text-ink-muted">{fmtDate(new Date(p.t).toISOString())}</div>
                  <div className="tabular text-sm font-semibold text-ink">
                    risk ≈ {p.estimate} · {bandForScore(p.estimate)}
                  </div>
                  {e && (
                    <div className="mt-1">
                      <div className="text-[10px] font-medium uppercase tracking-wide text-teal-hover">
                        {eventTypeLabel(e.type)}
                      </div>
                      <div className="text-xs text-ink-body">{e.summary}</div>
                    </div>
                  )}
                  {p.kind === "endpoint" && <div className="mt-1 text-[10px] uppercase tracking-wide text-teal">measured</div>}
                </div>
              );
            }}
          />

          <Line
            type="monotone"
            dataKey="estimate"
            stroke="#14b8a6"
            strokeWidth={2.5}
            strokeDasharray="6 5"
            isAnimationActive
            animationDuration={1200}
            dot={(props: { cx?: number; cy?: number; payload?: Pt }) => {
              const { cx, cy, payload } = props;
              if (cx == null || cy == null || !payload) return <g />;
              if (payload.kind === "endpoint") {
                const col = payload.t === startT ? cOld.fg : cNow.fg;
                return <circle cx={cx} cy={cy} r={6} fill={col} stroke="#fff" strokeWidth={2} />;
              }
              if (payload.kind === "event") {
                return (
                  <circle
                    cx={cx}
                    cy={cy}
                    r={5}
                    fill="#fff"
                    stroke="#14b8a6"
                    strokeWidth={2}
                    style={{ cursor: "pointer" }}
                    onClick={() => {
                      const e = eventById.get(payload.eventId!);
                      if (e) onSelectEvent?.(e);
                    }}
                  />
                );
              }
              return <g />;
            }}
            activeDot={{ r: 6 }}
          />

          <ReferenceDot x={startT} y={old} r={0} label={{ value: `${old}`, position: "bottom", fontSize: 11, fill: cOld.fg, fontWeight: 700 }} />
          <ReferenceDot x={endT} y={now} r={0} label={{ value: `${now}`, position: "top", fontSize: 13, fill: cNow.fg, fontWeight: 700 }} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
