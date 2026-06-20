"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import {
  Users,
  Share2,
  Activity,
  Briefcase,
  Flag,
  ExternalLink,
  Check,
  ChevronRight,
  ShieldAlert,
} from "lucide-react";
import type { CustomerCase, Severity } from "@/lib/types";
import { buildAlertFeed, DIMENSIONS, eventTypeLabel, type AlertItem } from "@/lib/alerts";
import { bandForScore, colorsForScore, fmtDate } from "@/lib/format";
import { CompanyLogo } from "@/components/shared/company-logo";

const DIM_ICON: Record<string, React.ElementType> = {
  identity_ownership: Users,
  network_risk: Share2,
  behavioural_drift: Activity,
  contextual_change: Briefcase,
};

const SEV_PILL: Record<Severity, string> = {
  high: "bg-risk-high-bg text-risk-high",
  medium: "bg-risk-med-bg text-risk-med",
  low: "bg-surface-card text-ink-muted",
};

function AlertRow({
  a,
  done,
  onAct,
}: {
  a: AlertItem;
  done: boolean;
  onAct: (a: AlertItem) => void;
}) {
  const DimIcon = DIM_ICON[a.dimension] ?? Briefcase;
  const typeLabel = a.headline ? "Drift re-tiering" : eventTypeLabel(a.type);

  return (
    <div
      className={`flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-start sm:gap-4 ${
        a.headline ? "bg-surface-subtle" : ""
      }`}
    >
      {/* dimension icon */}
      <span
        className={`mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full border ${
          a.headline ? "border-transparent" : "border-surface-line bg-white"
        }`}
        style={a.headline ? { background: colorsForScore(a.severity === "high" ? 85 : a.severity === "medium" ? 50 : 20).bg } : undefined}
      >
        {a.headline ? <Flag className="size-4 text-risk-high" /> : <DimIcon className="size-4 text-ink-muted" />}
      </span>

      {/* what happened */}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`rounded-pill px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${SEV_PILL[a.severity]}`}>
            {a.severity}
          </span>
          <span className="rounded-pill bg-surface-card px-2 py-0.5 text-[10px] font-medium text-ink-body">{typeLabel}</span>
          <span className="inline-flex items-center gap-1 text-[10px] text-ink-muted">
            <DimIcon className="size-3" /> {DIMENSIONS[a.dimension] ?? "Contextual Change"}
          </span>
        </div>
        <div className={`mt-1 text-sm ${a.headline ? "font-semibold text-ink" : "text-ink"}`}>{a.title}</div>
        {a.detail && <div className="mt-0.5 text-xs text-ink-body">{a.detail}</div>}
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-ink-muted">
          <span className="tabular">{fmtDate(a.date)}</span>
          {a.source && <span>{a.source}</span>}
          {a.sourceUrl && (
            <a
              href={a.sourceUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-teal-hover hover:underline"
            >
              source <ExternalLink className="size-3" />
            </a>
          )}
        </div>
      </div>

      {/* CTA / info marker + view client */}
      <div className="flex shrink-0 items-center gap-2 sm:flex-col sm:items-end">
        {a.cta ? (
          done ? (
            <span className="inline-flex items-center gap-1.5 rounded-md border border-risk-low/40 bg-risk-low-bg px-3 py-1.5 text-xs font-medium text-risk-low">
              <Check className="size-3.5" /> {a.cta.done}
            </span>
          ) : (
            <button
              onClick={() => onAct(a)}
              className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
                a.headline || a.severity === "high"
                  ? "bg-brand text-white hover:bg-brand-deep"
                  : "border border-surface-line bg-white text-ink-body hover:border-teal hover:bg-teal-wash hover:text-teal-hover"
              }`}
            >
              {a.severity === "high" && <ShieldAlert className="size-3.5" />} {a.cta.label}
            </button>
          )
        ) : (
          <span className="rounded-pill bg-surface-card px-2.5 py-1 text-[11px] text-ink-muted">Informational</span>
        )}
        <Link
          href={`/customers/${a.customerId}`}
          className="inline-flex items-center gap-0.5 text-[11px] text-ink-muted hover:text-teal-hover"
        >
          View client <ChevronRight className="size-3" />
        </Link>
      </div>
    </div>
  );
}

export function AlertsView({ cases }: { cases: CustomerCase[] }) {
  const feed = useMemo(() => buildAlertFeed(cases), [cases]);
  const [done, setDone] = useState<Set<string>>(new Set());

  const totals = useMemo(() => {
    const all = feed.flatMap((g) => g.items);
    return {
      total: all.length,
      action: all.filter((i) => i.cta).length,
      high: all.filter((i) => i.severity === "high").length,
      companies: feed.length,
    };
  }, [feed]);

  function act(a: AlertItem) {
    setDone((prev) => new Set(prev).add(`${a.customerId}:${a.id}:${a.cta?.key}`));
    toast.success(a.cta?.done ?? "Logged", { description: "Logged for the demo — no live downstream system." });
  }

  return (
    <main className="mx-auto w-full max-w-[1100px] px-6 py-8">
      <h1 className="font-display text-2xl font-semibold text-ink">Alerts</h1>
      <p className="mt-1 text-sm text-ink-muted">
        What public &amp; internal intelligence changed, per client — with the response when one is needed.
      </p>

      {/* summary strip */}
      <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: "Open alerts", value: totals.total },
          { label: "Need action", value: totals.action },
          { label: "High severity", value: totals.high },
          { label: "Clients flagged", value: totals.companies },
        ].map((s) => (
          <div key={s.label} className="rounded-card border border-surface-line bg-white p-4 shadow-card">
            <div className="tabular text-2xl font-bold text-ink">{s.value}</div>
            <div className="text-xs text-ink-muted">{s.label}</div>
          </div>
        ))}
      </div>

      {/* company-grouped alert list */}
      <div className="mt-6 space-y-5">
        {feed.map((g) => {
          const col = colorsForScore(g.score);
          return (
            <section key={g.customerId} className="overflow-hidden rounded-card border border-surface-line bg-white shadow-card">
              <header className="flex items-center gap-3 border-b border-surface-line px-4 py-3">
                <CompanyLogo customerId={g.customerId} name={g.company} size={40} />
                <div className="min-w-0 flex-1">
                  <Link href={`/customers/${g.customerId}`} className="truncate text-sm font-semibold text-ink hover:text-teal-hover">
                    {g.company}
                  </Link>
                  <div className="text-xs text-ink-muted">
                    <span className="tabular font-semibold" style={{ color: col.fg }}>
                      {Math.round(g.score)} · {bandForScore(g.score)}
                    </span>{" "}
                    · {g.counts.total} alert{g.counts.total === 1 ? "" : "s"} · {g.counts.action} need action
                  </div>
                </div>
              </header>
              <div className="divide-y divide-surface-line">
                {g.items.map((a) => (
                  <AlertRow key={a.id} a={a} done={done.has(`${a.customerId}:${a.id}:${a.cta?.key}`)} onAct={act} />
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </main>
  );
}
