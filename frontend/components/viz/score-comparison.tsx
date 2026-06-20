"use client";

import { motion } from "framer-motion";
import { ArrowDown, ArrowRight, Flag } from "lucide-react";
import { bandForScore, colorsForScore, fmtDelta } from "@/lib/format";

function Donut({ score, label, pulse, size = 124 }: { score: number; label: string; pulse?: boolean; size?: number }) {
  const stroke = size <= 84 ? 9 : 12;
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const c = colorsForScore(score);
  const band = bandForScore(score);
  const pct = Math.max(0, Math.min(100, score)) / 100;
  const big = size > 100;

  return (
    <div className="flex flex-col items-center gap-1.5">
      <div className="relative" style={{ width: size, height: size }}>
        {pulse && (
          <motion.span
            className="absolute inset-0 rounded-full"
            style={{ boxShadow: `0 0 0 0 ${c.ring}` }}
            animate={{ boxShadow: [`0 0 0 0 ${c.ring}80`, `0 0 0 14px ${c.ring}00`] }}
            transition={{ duration: 1.6, repeat: Infinity, ease: "easeOut" }}
          />
        )}
        <svg width={size} height={size} className="-rotate-90">
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#eef0f2" strokeWidth={stroke} />
          <motion.circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={c.fg}
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={circ}
            initial={{ strokeDashoffset: circ }}
            animate={{ strokeDashoffset: circ * (1 - pct) }}
            transition={{ duration: 1, ease: [0.4, 0, 0.2, 1], delay: 0.3 }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={`tabular font-bold ${big ? "text-2xl" : "text-lg"}`} style={{ color: c.fg }}>
            {Math.round(score)}
          </span>
          <span className={`font-semibold tracking-wide ${big ? "text-[10px]" : "text-[9px]"}`} style={{ color: c.fg }}>
            {band}
          </span>
        </div>
      </div>
      <span className={`uppercase tracking-wide text-ink-muted ${big ? "text-xs" : "text-[10px]"}`}>{label}</span>
    </div>
  );
}

export function ScoreComparison({
  oldScore,
  newScore,
  driftScore,
  compact = false,
  oldLabel = "At onboarding",
  newLabel = "Live (now)",
}: {
  oldScore: number;
  newScore: number;
  driftScore: number;
  compact?: boolean;
  oldLabel?: string;
  newLabel?: string;
}) {
  const delta = Math.round(newScore - oldScore);
  const flipped = bandForScore(oldScore) !== bandForScore(newScore);

  if (compact) {
    return (
      <div className="flex flex-col items-center gap-1 text-center">
        <Donut score={oldScore} label={oldLabel} size={72} />
        <div className="flex items-center gap-1.5 py-0.5">
          <span className="tabular text-sm font-bold text-risk-high">{fmtDelta(delta)}</span>
          <ArrowDown className="size-4 text-ink-muted" strokeWidth={2.2} />
        </div>
        <Donut score={newScore} label={newLabel} size={72} pulse={flipped} />
        {flipped && (
          <span className="mt-1.5 inline-flex items-center gap-1 rounded-pill bg-risk-high-bg px-2 py-0.5 text-[11px] font-semibold text-risk-high">
            <Flag className="size-3" /> {bandForScore(oldScore)} → {bandForScore(newScore)}
          </span>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-3">
      <div className="flex items-center gap-5">
        <Donut score={oldScore} label={oldLabel} />
        <div className="flex flex-col items-center gap-1">
          <span className="tabular text-lg font-bold text-risk-high">{fmtDelta(delta)}</span>
          <ArrowRight className="size-6 text-ink-muted" strokeWidth={2.2} />
          <span className="rounded-pill bg-surface-card px-2 py-0.5 text-[10px] text-ink-muted">
            drift {driftScore.toFixed(2)}
          </span>
        </div>
        <Donut score={newScore} label={newLabel} pulse={flipped} />
      </div>
      {flipped && (
        <span className="inline-flex items-center gap-1.5 rounded-pill bg-risk-high-bg px-3 py-1 text-xs font-semibold text-risk-high">
          <Flag className="size-3.5" /> Risk band changed — {bandForScore(oldScore)} → {bandForScore(newScore)}
        </span>
      )}
    </div>
  );
}
