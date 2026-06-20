"use client";

import { useState } from "react";
import { toast } from "sonner";
import type { Customer, DriftAlert, EvidenceEvent, DecisionResult } from "@/lib/types";
import { fmtDate, eventTypeLabel, toEpoch, colorsForScore, bandForScore } from "@/lib/format";
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
  ShieldCheck,
  ExternalLink,
  Layers,
  FolderOpen,
  CalendarClock,
  TrendingUp,
  SlidersHorizontal,
  Check,
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

const STATE_BADGE: Record<string, { label: string; cls: string }> = {
  pending: { label: "Pending review", cls: "bg-risk-med-bg text-risk-med" },
  approved: { label: "Approved", cls: "bg-risk-low-bg text-risk-low" },
  dismissed: { label: "Dismissed", cls: "bg-surface-card text-ink-muted" },
  escalated: { label: "Escalated → Re-KYC", cls: "bg-risk-high-bg text-risk-high" },
};

export function DriftLog({
  customer,
  events,
  alert,
  dispo,
  selectedId,
  onSelect,
}: {
  customer: Customer;
  events: EvidenceEvent[];
  alert: DriftAlert;
  dispo?: DecisionResult | null;
  selectedId?: string | null;
  onSelect?: (e: EvidenceEvent) => void;
}) {
  const old = alert.old_risk_score ?? customer.risk_model.onboarding_score;
  const now = alert.new_risk_score ?? old;
  const cNow = colorsForScore(now);

  const drivers = alert.evidence_ids
    .map((id) => events.find((e) => e.id === id))
    .filter((e): e is EvidenceEvent => Boolean(e))
    .sort((a, b) => toEpoch(b.published_at) - toEpoch(a.published_at));

  const clean = alert.flag === "No material drift" || (alert.drift_score === 0 && drivers.length === 0);
  const state = dispo?.governance_state ?? alert.governance_state;
  const badge = STATE_BADGE[state] ?? STATE_BADGE.pending;

  // RM workflow shortcuts that mirror the agent's recommended action plan.
  // Demo-only: clicking records local state + a toast — no live downstream system.
  const reTierBand = bandForScore(now);
  const ACTIONS = [
    { key: "edd", label: "Open EDD case", done: "EDD case opened", icon: FolderOpen, primary: true },
    { key: "offcycle", label: "Pull review off-cycle", done: "Review pulled off-cycle", icon: CalendarClock, primary: false },
    { key: "retier", label: `Re-tier to ${reTierBand}`, done: `Re-tiered to ${reTierBand}`, icon: TrendingUp, primary: false },
    { key: "tm", label: "Adjust TM thresholds", done: "TM thresholds re-baselined", icon: SlidersHorizontal, primary: false },
  ];
  const [taken, setTaken] = useState<Set<string>>(new Set());
  function take(a: (typeof ACTIONS)[number]) {
    setTaken((prev) => new Set(prev).add(a.key));
    toast.success(a.done, { description: "Logged for the demo — no live downstream system." });
  }

  return (
    <div className="flex flex-col gap-4">
      {/* SITUATION OVERVIEW — the recap of the whole drift episode */}
      <div
        className="rounded-md border border-l-[3px] border-surface-line bg-surface-subtle p-4"
        style={{ borderLeftColor: clean ? undefined : cNow.fg }}
      >
        <div className="mb-2.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-muted">
          <Layers className="size-3.5" /> Situation overview · the whole picture at a glance
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {clean ? (
            <ShieldCheck className="size-4 text-risk-low" />
          ) : (
            <Flag className="size-4" style={{ color: cNow.fg }} />
          )}
          <span className="font-display font-semibold text-ink">{alert.flag}</span>
          {!clean && (
            <span
              className="tabular rounded-pill px-2 py-0.5 text-[10px] font-semibold"
              style={{ background: cNow.bg, color: cNow.fg }}
            >
              {old} → {now}
            </span>
          )}
          <span className="tabular ml-auto text-xs text-ink-muted">{fmtDate(alert.created_at)}</span>
        </div>
        <p className="mt-1.5 text-sm text-ink-body">{alert.recommended_action}</p>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-ink-muted">
          <span className={`rounded-pill px-2 py-0.5 font-medium ${badge.cls}`}>
            {dispo ? `${badge.label} · ${dispo.reviewer} (${dispo.role})` : badge.label}
          </span>
          {!clean && <span>drift {alert.drift_score.toFixed(2)}</span>}
          <span>confidence {(alert.confidence * 100).toFixed(0)}%</span>
          {alert.model_used && alert.model_used !== "none" && <span>model: {alert.model_used}</span>}
        </div>

        {!clean && (
          <div className="mt-3 border-t border-surface-line/70 pt-3">
            <div className="mb-2 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-ink-muted">
              Recommended actions
            </div>
            <div className="flex flex-wrap gap-2">
              {ACTIONS.map((a) => {
                const done = taken.has(a.key);
                const Icon = done ? Check : a.icon;
                return (
                  <button
                    key={a.key}
                    onClick={() => take(a)}
                    disabled={done}
                    className={
                      done
                        ? "inline-flex items-center gap-1.5 rounded-md border border-risk-low/40 bg-risk-low-bg px-3 py-1.5 text-xs font-medium text-risk-low"
                        : a.primary
                          ? "inline-flex items-center gap-1.5 rounded-md bg-brand px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-brand-deep"
                          : "inline-flex items-center gap-1.5 rounded-md border border-surface-line bg-white px-3 py-1.5 text-xs font-medium text-ink-body transition-colors hover:border-teal hover:bg-teal-wash hover:text-teal-hover"
                    }
                  >
                    <Icon className="size-3.5" /> {done ? a.done : a.label}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* the evidence that drove the flag (curated subset, NOT the full signal feed) */}
      {drivers.length > 0 ? (
        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">
            Evidence behind this flag ({drivers.length})
          </div>
          <div className="overflow-hidden rounded-md border border-surface-line">
            {drivers.map((e, i) => {
              const Icon = ICONS[e.type] ?? FileText;
              const active = selectedId === e.id;
              return (
                <button
                  key={e.id}
                  onClick={() => onSelect?.(e)}
                  className={`flex w-full items-start gap-3 px-3 py-2.5 text-left transition-colors ${
                    i > 0 ? "border-t border-surface-line" : ""
                  } ${active ? "bg-teal-wash" : "hover:bg-surface-subtle"}`}
                >
                  <span
                    className={`mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full border ${
                      active ? "border-teal bg-white" : "border-surface-line bg-white"
                    }`}
                  >
                    <Icon className={`size-3.5 ${active ? "text-teal-hover" : "text-ink-muted"}`} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="tabular text-xs text-ink-muted">{fmtDate(e.published_at)}</span>
                      <span className="rounded-pill bg-surface-card px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-ink-body">
                        {eventTypeLabel(e.type)}
                      </span>
                    </div>
                    <div className="mt-0.5 text-sm text-ink">{e.summary}</div>
                    <div className="mt-0.5 flex items-center gap-2 text-[11px] text-ink-muted">
                      <span>{e.source}</span>
                      {e.source_url ? (
                        <span className="inline-flex items-center gap-1 text-teal-hover">
                          cited <ExternalLink className="size-3" />
                        </span>
                      ) : null}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="rounded-md border border-dashed border-surface-line p-3 text-sm text-ink-muted">
          Monitored {events.length} public signals; none contradicted an on-file KYC assertion. The full signal
          feed is in the News &amp; Social radar.
        </div>
      )}
    </div>
  );
}
