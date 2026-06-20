"use client";

import { Button } from "@/components/ui/button";
import { Check, ShieldAlert, ArrowUpRight, Sparkles, Globe, MapPin, Calendar, Hash } from "lucide-react";
import type { Customer, DriftAlert } from "@/lib/types";
import { bandForScore, colorsForScore, fmtDate, monogram } from "@/lib/format";

function Fact({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value?: string }) {
  return (
    <div className="flex items-start gap-2">
      <Icon className="mt-0.5 size-3.5 shrink-0 text-ink-muted" />
      <div className="min-w-0">
        <div className="text-[10px] uppercase tracking-wide text-ink-muted">{label}</div>
        <div className="truncate text-sm text-ink" title={value}>
          {value || "—"}
        </div>
      </div>
    </div>
  );
}

export function ClientSection({ customer, alert }: { customer: Customer; alert: DriftAlert }) {
  const ep = customer.entity_profile;
  const score = alert.new_risk_score ?? customer.risk_model.onboarding_score;
  const band = bandForScore(score);
  const c = colorsForScore(score);
  const materialChanges = (alert.contradicted_assertion_id ? 1 : 0) + alert.also_contradicts.length;

  return (
    <section className="overflow-hidden rounded-card border border-surface-line bg-white shadow-card">
      {/* top band */}
      <div className="flex flex-wrap items-start gap-5 border-b border-surface-line p-6">
        {/* logo */}
        <div
          className="flex size-16 shrink-0 items-center justify-center rounded-2xl text-xl font-bold text-white shadow-card"
          style={{ background: "linear-gradient(135deg,#0d2936,#14b8a6)" }}
        >
          {monogram(customer.legal_name)}
        </div>

        {/* identity */}
        <div className="min-w-0 flex-1">
          <h2 className="font-serif text-2xl font-semibold leading-tight text-ink">{customer.legal_name}</h2>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
            <span className="rounded-pill bg-surface-card px-2 py-0.5 text-ink-body">{ep.legal_form}</span>
            <span className="rounded-pill bg-surface-card px-2 py-0.5 text-ink-body">{ep.country_of_incorporation}</span>
            {ep.listed_on_exchange && (
              <span className="rounded-pill bg-surface-card px-2 py-0.5 text-ink-body">{ep.ticker ?? "Listed"}</span>
            )}
            <span className="text-ink-muted">RM: G. Cozzio</span>
          </div>
        </div>

        {/* verdict */}
        <div className="flex flex-col items-end gap-1">
          <span className="rounded-pill px-3 py-1 text-sm font-bold tracking-wide tabular" style={{ background: c.bg, color: c.fg }}>
            DRIFT: {band}
          </span>
          <span className="text-xs text-ink-muted">
            {materialChanges} material changes · score{" "}
            <span className="tabular font-semibold" style={{ color: c.fg }}>
              {score}
            </span>
          </span>
        </div>
      </div>

      {/* facts grid */}
      <div className="grid grid-cols-2 gap-x-6 gap-y-4 p-6 sm:grid-cols-3 lg:grid-cols-4">
        <Fact icon={Hash} label="Register / LEI" value={ep.commercial_register_number ?? ep.lei} />
        <Fact icon={Calendar} label="Incorporated" value={ep.date_of_incorporation} />
        <Fact icon={MapPin} label="Domicile" value={ep.registered_address} />
        <Fact icon={MapPin} label="Principal place" value={ep.principal_place_of_business} />
        <Fact icon={Globe} label="Website" value={ep.website} />
        <Fact icon={Calendar} label="Onboarded" value={fmtDate(customer.onboarded_as_of)} />
        <Fact icon={Calendar} label="Last review" value={fmtDate(customer.kyc_review.last_review)} />
        <Fact icon={Calendar} label="Next review (scheduled)" value={fmtDate(customer.kyc_review.next_periodic_review)} />
      </div>

      {/* action bar */}
      <div className="flex flex-wrap items-center gap-2 border-t border-surface-line bg-surface-subtle px-6 py-3">
        <span className="mr-auto text-xs text-ink-muted">
          Disposition required — every action is written to the audit log.
        </span>
        <Button size="sm" variant="outline" className="gap-1.5">
          <Sparkles className="size-4 text-teal-hover" /> Ask the data
        </Button>
        <Button size="sm" className="gap-1.5 bg-teal text-white hover:bg-teal-hover">
          <Check className="size-4" /> Approve
        </Button>
        <Button size="sm" variant="outline" className="gap-1.5">
          <ArrowUpRight className="size-4" /> Override
        </Button>
        <Button size="sm" className="gap-1.5 bg-risk-high text-white hover:bg-risk-high/90">
          <ShieldAlert className="size-4" /> Escalate → Re-KYC
        </Button>
      </div>
    </section>
  );
}
