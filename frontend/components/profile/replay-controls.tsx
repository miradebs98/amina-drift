"use client";

import { Play, Square } from "lucide-react";
import type { Frame } from "@/lib/trajectory";
import { fmtDate, bandForScore, colorsForScore } from "@/lib/format";

export function ReplayControls({
  playing,
  idx,
  total,
  frame,
  onToggle,
}: {
  playing: boolean;
  idx: number;
  total: number;
  frame: Frame | null;
  onToggle: () => void;
}) {
  const c = frame ? colorsForScore(frame.score) : null;

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-md border border-surface-line bg-surface-subtle px-3 py-2">
      <button
        onClick={onToggle}
        className="inline-flex items-center gap-1.5 rounded-md bg-brand px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-brand-deep"
      >
        {playing ? <Square className="size-3.5" /> : <Play className="size-3.5" />}
        {playing ? "Stop" : "Replay the drift"}
      </button>

      {/* progress dots */}
      <div className="flex items-center gap-1">
        {Array.from({ length: total }).map((_, i) => (
          <span
            key={i}
            className={`h-1.5 rounded-full transition-all ${
              playing && i <= idx ? "w-4 bg-teal" : "w-1.5 bg-surface-line"
            }`}
          />
        ))}
      </div>

      {/* caption */}
      <div className="ml-auto min-w-0 text-right">
        {playing && frame ? (
          <div className="flex items-center justify-end gap-2">
            <span className="tabular text-xs text-ink-muted">{fmtDate(new Date(frame.t).toISOString())}</span>
            <span className="max-w-[280px] truncate text-xs text-ink">{frame.label}</span>
            {c && (
              <span className="tabular rounded-pill px-2 py-0.5 text-xs font-bold" style={{ background: c.bg, color: c.fg }}>
                {frame.score} · {bandForScore(frame.score)}
              </span>
            )}
          </div>
        ) : (
          <span className="text-xs text-ink-muted">▶ Watch 30 months of silent drift in ~20 seconds</span>
        )}
      </div>
    </div>
  );
}
