"use client";

import { motion } from "framer-motion";
import { bandForScore, colorsForScore, letterForScore } from "@/lib/format";

/**
 * RiskGauge — 180° speedometer of the 0-100 risk score.
 * Needle animates from `from` (onboarding) to `score` (current). Band arcs are a
 * pure function of the score scale, so the dial can never disagree with the number.
 */
export function RiskGauge({
  score,
  from,
  confidence,
  size = 280,
}: {
  score: number;
  from?: number;
  confidence?: number;
  size?: number;
}) {
  const w = size;
  const h = size * 0.62;
  const cx = w / 2;
  const cy = h - 8;
  const r = w / 2 - 22;
  const stroke = 18;

  // 180° dial, 180°(left)=0 → 0°(right)=100
  const angleFor = (v: number) => 180 - (Math.max(0, Math.min(100, v)) / 100) * 180;
  const polar = (deg: number, radius: number) => {
    const rad = (deg * Math.PI) / 180;
    return { x: cx + radius * Math.cos(rad), y: cy - radius * Math.sin(rad) };
  };
  const arcPath = (a0: number, a1: number, radius: number) => {
    const p0 = polar(a0, radius);
    const p1 = polar(a1, radius);
    const large = Math.abs(a1 - a0) > 180 ? 1 : 0;
    // sweep flag 0 because we go counter-clockwise in screen space
    return `M ${p0.x} ${p0.y} A ${radius} ${radius} 0 ${large} 1 ${p1.x} ${p1.y}`;
  };

  const bands = [
    { lo: 0, hi: 33, color: "#4ade80" },
    { lo: 34, hi: 66, color: "#facc15" },
    { lo: 67, hi: 100, color: "#f87171" },
  ];

  const c = colorsForScore(score);
  const band = bandForScore(score);
  const letter = letterForScore(score);
  const tip = polar(angleFor(score), r - 6);
  const fromTip = polar(angleFor(from ?? score), r - 6);

  return (
    <div className="flex flex-col items-center">
      <svg width={w} height={h + 56} viewBox={`0 0 ${w} ${h + 56}`} className="overflow-visible">
        {/* track */}
        <path d={arcPath(180, 0, r)} fill="none" stroke="#eef0f2" strokeWidth={stroke} strokeLinecap="round" />
        {/* colored bands */}
        {bands.map((b) => (
          <path
            key={b.lo}
            d={arcPath(angleFor(b.lo), angleFor(b.hi), r)}
            fill="none"
            stroke={b.color}
            strokeWidth={stroke}
            strokeLinecap="butt"
            opacity={band === bandForScore((b.lo + b.hi) / 2) ? 1 : 0.32}
          />
        ))}

        {/* ticks + labels at band edges */}
        {[0, 33, 66, 100].map((t) => {
          const p = polar(angleFor(t), r - stroke - 6);
          return (
            <text
              key={t}
              x={p.x}
              y={p.y}
              fontSize={11}
              fill="#9ca3af"
              textAnchor="middle"
              dominantBaseline="middle"
              fontFamily="var(--font-mono)"
            >
              {t}
            </text>
          );
        })}

        {/* needle — animates to the current score (drives the replay) */}
        <motion.line
          x1={cx}
          y1={cy}
          stroke={c.fg}
          strokeWidth={4}
          strokeLinecap="round"
          initial={{ x2: fromTip.x, y2: fromTip.y }}
          animate={{ x2: tip.x, y2: tip.y }}
          transition={{ type: "spring", stiffness: 90, damping: 15 }}
        />
        <motion.circle cx={cx} cy={cy} r={9} animate={{ fill: c.fg }} />
        <circle cx={cx} cy={cy} r={4} fill="#fff" />

        {/* center readout */}
        <text x={cx} y={cy - r * 0.46} textAnchor="middle" fontFamily="var(--font-mono)" fontSize={42} fontWeight={700} fill={c.fg}>
          {Math.round(score)}
        </text>
        <text x={cx} y={cy - r * 0.46 + 22} textAnchor="middle" fontSize={12} fill="#9ca3af" fontFamily="var(--font-mono)">
          / 100
        </text>
      </svg>

      <div className="-mt-10 flex flex-col items-center gap-1">
        <span
          className="rounded-pill px-3 py-1 text-xs font-semibold tracking-wide tabular"
          style={{ background: c.bg, color: c.fg }}
        >
          {band} · GRADE {letter}
        </span>
        {confidence !== undefined && (
          <span className="text-xs text-ink-muted">model confidence {(confidence * 100).toFixed(0)}%</span>
        )}
      </div>
    </div>
  );
}
