"use client";

import { Play, Square } from "lucide-react";
import type { Frame } from "@/lib/trajectory";
import { bandForScore, colorsForScore } from "@/lib/format";

type PeriodOption = { key: string; label: string; months: number | null };

export function ReplayControls({
  playing,
  idx,
  total,
  frame,
  onToggle,
  periodOptions,
  periodKey,
  onPeriodChange,
}: {
  playing: boolean;
  idx: number;
  total: number;
  frame: Frame | null;
  onToggle: () => void;
  periodOptions: PeriodOption[];
  periodKey: string;
  onPeriodChange: (k: string) => void;
}) {
  const c = frame ? colorsForScore(frame.score) : null;

  return (
    <div className="flex items-center gap-3 rounded-md border border-surface-line bg-surface-subtle px-3 py-2">
      <button
        onClick={onToggle}
        className="inline-flex shrink-0 items-center gap-1.5 rounded-md bg-brand px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-brand-deep"
      >
        {playing ? <Square className="size-3.5" /> : <Play className="size-3.5" />}
        {playing ? "Stop" : "Replay the drift"}
      </button>

      {/* reference-period selector */}
      {periodOptions.length > 1 && (
        <div className="flex shrink-0 items-center gap-1.5">
          <span className="text-[11px] uppercase tracking-wide text-ink-muted">Period</span>
          <div className="inline-flex overflow-hidden rounded-md border border-surface-line bg-white">
            {periodOptions.map((p) => (
              <button
                key={p.key}
                onClick={() => onPeriodChange(p.key)}
                className={`px-2.5 py-1 text-xs transition-colors ${
                  p.key === periodKey ? "bg-teal text-white" : "text-ink-body hover:bg-teal-wash"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* progress dots — take the flexible middle, clip if space is tight */}
      <div className="flex min-w-0 flex-1 items-center gap-1 overflow-hidden">
        {Array.from({ length: total }).map((_, i) => (
          <span
            key={i}
            className={`h-1.5 shrink-0 rounded-full transition-all ${
              playing && i <= idx ? "w-4 bg-teal" : "w-1.5 bg-surface-line"
            }`}
          />
        ))}
      </div>

      {/* running score / caption — pinned top-right */}
      <div className="shrink-0 whitespace-nowrap text-right">
        {playing && frame && c ? (
          <span className="tabular rounded-pill px-2 py-0.5 text-xs font-bold" style={{ background: c.bg, color: c.fg }}>
            {frame.score} · {bandForScore(frame.score)}
          </span>
        ) : (
          <span className="text-xs text-ink-muted">▶ Walk each public signal in time</span>
        )}
      </div>
    </div>
  );
}
