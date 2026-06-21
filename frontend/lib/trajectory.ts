import type { Customer, EvidenceEvent, DriftAlert, TimelinePoint } from "./types";
import { toEpoch } from "./format";

// how hard each signal type pushes the score (drives spike size)
export const IMPACT: Record<string, number> = {
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

export type TrajPoint = { t: number; estimate: number; eventId?: string; kind?: "endpoint" | "event" };
export type Frame = { t: number; score: number; event?: EvidenceEvent; label: string };

/**
 * Builds the event-weighted drift trajectory between the two REAL endpoints
 * (onboarding score, current score). Big-impact signals create sharp spikes;
 * quiet stretches drift gently. Returns:
 *  - points: dense series for the line chart (with shoulders + event nodes)
 *  - frames: key-frames for the time-compressed replay (onboarding → each event → today)
 */
export function buildTrajectory(
  customer: Customer,
  events: EvidenceEvent[],
  alert: DriftAlert,
  timeline?: TimelinePoint[],
) {
  // PREFERRED: the engine's OWN arc (onboarding → final, including any fall-back from resolving events,
  // e.g. Coinbase 60→82→67). Each tick is real; events attach to their tick by day.
  if (timeline && timeline.length >= 2) {
    const day = (s: string) => Math.floor(toEpoch(s) / 864e5);
    const evByDay = new Map<number, EvidenceEvent[]>();
    for (const e of events) {
      const d = day(e.published_at);
      (evByDay.get(d) ?? evByDay.set(d, []).get(d)!).push(e);
    }
    const startT = toEpoch(timeline[0].as_of);
    const endT = toEpoch(timeline[timeline.length - 1].as_of);
    const tOld = timeline[0].risk_score;
    const tNow = timeline[timeline.length - 1].risk_score;
    const points: TrajPoint[] = [];
    const frames: Frame[] = [];
    timeline.forEach((tp, i) => {
      const t = toEpoch(tp.as_of);
      const ev0 = (evByDay.get(day(tp.as_of)) ?? [])[0];
      const isEnd = i === 0 || i === timeline.length - 1;
      points.push({ t, estimate: tp.risk_score, eventId: ev0?.id, kind: isEnd ? "endpoint" : "event" });
      frames.push({
        t,
        score: tp.risk_score,
        event: ev0,
        label: i === 0 ? "Onboarding" : ev0 ? ev0.summary : i === timeline.length - 1 ? "Today" : "Re-assessed",
      });
    });
    return { points, frames, old: tOld, now: tNow, startT, endT };
  }

  const old = alert.old_risk_score ?? customer.risk_model.onboarding_score;
  const now = alert.new_risk_score ?? old;
  const startT = toEpoch(customer.onboarded_as_of);
  const endT = Math.max(toEpoch(alert.created_at), ...events.map((e) => toEpoch(e.published_at)));

  const rand = mulberry32(seedFrom(customer.customer_id));
  const ev = [...events]
    .filter((e) => toEpoch(e.published_at) > startT && toEpoch(e.published_at) < endT)
    .sort((a, b) => toEpoch(a.published_at) - toEpoch(b.published_at));

  const weights = ev.map((e) => IMPACT[e.type] ?? 2);
  const totalW = weights.reduce((s, w) => s + w, 0) || 1;
  const span = now - old;
  const clamp = (v: number) => Math.max(Math.min(old, now), Math.min(Math.max(old, now), v));

  const points: TrajPoint[] = [{ t: startT, estimate: old, kind: "endpoint" }];
  const frames: Frame[] = [{ t: startT, score: old, label: "Onboarding" }];
  let cum = old;
  let lastT = startT;

  ev.forEach((e, i) => {
    const t = toEpoch(e.published_at);
    const target = old + (span * weights.slice(0, i + 1).reduce((s, w) => s + w, 0)) / totalW;

    const shoulderT = Math.min(t - 9 * 864e5, (lastT + t) / 2);
    if (shoulderT > lastT) {
      const wander = cum + (rand() - 0.45) * 3;
      points.push({ t: shoulderT, estimate: Math.round(clamp(wander)) });
    }
    cum = Math.round(clamp(target));
    points.push({ t, estimate: cum, eventId: e.id, kind: "event" });
    frames.push({ t, score: cum, event: e, label: e.summary });
    lastT = t;
  });

  points.push({ t: endT, estimate: now, kind: "endpoint" });
  frames.push({ t: endT, score: now, label: "Today" });

  return { points, frames, old, now, startT, endT };
}
