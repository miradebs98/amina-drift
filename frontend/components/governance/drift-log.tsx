"use client";

import type { Customer, DriftAlert, EvidenceEvent } from "@/lib/types";
import { fmtDate, eventTypeLabel, toEpoch, colorsForScore } from "@/lib/format";
import {
  Newspaper,
  FileText,
  Users,
  Ban,
  UserCheck,
  Globe,
  Banknote,
  ArrowLeftRight,
  Flag,
  ExternalLink,
} from "lucide-react";

const ICONS: Record<string, React.ElementType> = {
  news: Newspaper,
  registry_change: FileText,
  ownership_change: Users,
  sanctions_hit: Ban,
  pep_hit: UserCheck,
  website_change: Globe,
  funding: Banknote,
  transaction: ArrowLeftRight,
};

export function DriftLog({
  customer,
  events,
  alert,
  selectedId,
  onSelect,
}: {
  customer: Customer;
  events: EvidenceEvent[];
  alert: DriftAlert;
  selectedId?: string | null;
  onSelect?: (e: EvidenceEvent) => void;
}) {
  const sorted = [...events].sort((a, b) => toEpoch(b.published_at) - toEpoch(a.published_at));
  const old = alert.old_risk_score ?? customer.risk_model.onboarding_score;
  const now = alert.new_risk_score ?? old;
  const cNow = colorsForScore(now);

  return (
    <div className="flex flex-col">
      {/* headline: the re-tiering alert */}
      <div className="relative flex gap-3 pb-4">
        <div className="flex flex-col items-center">
          <span className="flex size-8 items-center justify-center rounded-full" style={{ background: cNow.bg }}>
            <Flag className="size-4" style={{ color: cNow.fg }} />
          </span>
          <span className="mt-1 w-px flex-1 bg-surface-line" />
        </div>
        <div className="flex-1 pb-1">
          <div className="flex items-center gap-2">
            <span className="tabular text-xs text-ink-muted">{fmtDate(alert.created_at)}</span>
            <span className="rounded-pill px-2 py-0.5 text-[10px] font-semibold uppercase" style={{ background: cNow.bg, color: cNow.fg }}>
              Re-tier {old} → {now}
            </span>
          </div>
          <div className="mt-0.5 text-sm font-semibold text-ink">{alert.flag}</div>
          <p className="mt-0.5 text-xs leading-relaxed text-ink-body">{alert.recommended_action}</p>
        </div>
      </div>

      {/* signal history */}
      {sorted.map((e, i) => {
        const Icon = ICONS[e.type] ?? FileText;
        const active = selectedId === e.id;
        const last = i === sorted.length - 1;
        const num = sorted.length - i; // chronological signal number
        return (
          <button
            key={e.id}
            onClick={() => onSelect?.(e)}
            className={`group relative flex gap-3 rounded-md text-left transition-colors ${
              active ? "bg-teal-wash" : "hover:bg-surface-subtle"
            }`}
          >
            <div className="flex flex-col items-center pl-px">
              <span
                className={`flex size-8 items-center justify-center rounded-full border ${
                  active ? "border-teal bg-white" : "border-surface-line bg-white"
                }`}
              >
                <Icon className={`size-4 ${active ? "text-teal-hover" : "text-ink-muted"}`} />
              </span>
              {!last && <span className="mt-1 w-px flex-1 bg-surface-line" />}
            </div>
            <div className="flex-1 pb-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="tabular text-xs text-ink-muted">{fmtDate(e.published_at)}</span>
                <span className="rounded-pill bg-surface-card px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-ink-body">
                  Signal {num} · {eventTypeLabel(e.type)}
                </span>
              </div>
              <div className="mt-0.5 text-sm text-ink">{e.summary}</div>
              <div className="mt-0.5 flex items-center gap-2 text-[11px] text-ink-muted">
                <span>{e.source}</span>
                {e.source_url ? (
                  <span className="inline-flex items-center gap-1 text-teal-hover">
                    cited <ExternalLink className="size-3" />
                  </span>
                ) : (
                  <span className="rounded-pill bg-risk-med-bg px-1.5 py-0.5 font-medium text-risk-med">SIMULATED</span>
                )}
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
}
