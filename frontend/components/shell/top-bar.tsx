"use client";

import { Search, Database } from "lucide-react";
import { DATA_MODE } from "@/lib/api";

export function TopBar({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="sticky top-0 z-20 flex items-center gap-4 border-b border-surface-line bg-white/90 px-6 py-3 backdrop-blur">
      <div className="min-w-0">
        <h1 className="truncate font-display text-lg font-semibold text-ink">{title}</h1>
        {subtitle && <p className="truncate text-xs text-ink-muted">{subtitle}</p>}
      </div>

      <div className="ml-auto flex items-center gap-3">
        <div className="hidden items-center gap-2 rounded-md border border-surface-line bg-surface-subtle px-3 py-1.5 text-sm text-ink-muted sm:flex">
          <Search className="size-4" />
          <span className="text-xs">Search clients…</span>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-pill bg-surface-card px-2.5 py-1 text-[11px] font-medium uppercase tracking-wide text-ink-muted">
          <Database className="size-3" /> {DATA_MODE} data
        </span>
      </div>
    </div>
  );
}
