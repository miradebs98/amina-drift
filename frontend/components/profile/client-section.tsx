"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Check,
  ShieldAlert,
  ArrowUpRight,
  Globe,
  MapPin,
  Calendar,
  Hash,
  ChevronDown,
  CheckCircle2,
  TriangleAlert,
} from "lucide-react";
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
  const [open, setOpen] = useState(false);
  const [disposed, setDisposed] = useState<string | null>(null);
  const ep = customer.entity_profile;
  const score = alert.new_risk_score ?? customer.risk_model.onboarding_score;
  const band = bandForScore(score);
  const c = colorsForScore(score);
  const materialChanges = (alert.contradicted_assertion_id ? 1 : 0) + alert.also_contradicts.length;

  // The disposition surface only appears when there's a PENDING trigger to action.
  const pending = alert.governance_state === "pending" && !disposed;
  function dispose(label: string) {
    setDisposed(label);
    toast.success(`${label} — written to audit log`, { description: "by G. Cozzio · drift-model v2.3" });
  }

  return (
    <section className="overflow-hidden rounded-card border border-surface-line bg-white shadow-card">
      {/* HEADER — always visible; click to expand details */}
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-4 p-5 text-left transition-colors hover:bg-surface-subtle"
      >
        <div
          className="flex size-12 shrink-0 items-center justify-center rounded-xl text-base font-bold text-white shadow-card"
          style={{ background: "linear-gradient(135deg,#0d2936,#14b8a6)" }}
        >
          {monogram(customer.legal_name)}
        </div>

        <div className="min-w-0 flex-1">
          <h2 className="truncate font-display text-xl font-semibold leading-tight text-ink">{customer.legal_name}</h2>
          <div className="mt-0.5 flex items-center gap-2 text-xs text-ink-muted">
            <span>{ep.legal_form}</span>
            <span>·</span>
            <span>{ep.country_of_incorporation}</span>
            <span>·</span>
            <span>RM: G. Cozzio</span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex flex-col items-end">
            <span className="rounded-pill px-3 py-1 text-sm font-bold tracking-wide tabular" style={{ background: c.bg, color: c.fg }}>
              DRIFT: {band}
            </span>
            <span className="mt-0.5 text-xs text-ink-muted">
              {materialChanges} changes · score{" "}
              <span className="tabular font-semibold" style={{ color: c.fg }}>
                {score}
              </span>
            </span>
          </div>
          <ChevronDown className={`size-5 text-ink-muted transition-transform ${open ? "rotate-180" : ""}`} />
        </div>
      </button>

      {/* DETAILS — collapsible */}
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: [0.4, 0, 0.2, 1] }}
            className="overflow-hidden"
          >
            <div className="grid grid-cols-2 gap-x-6 gap-y-4 border-t border-surface-line p-6 sm:grid-cols-3 lg:grid-cols-4">
              <Fact icon={Hash} label="Register / LEI" value={ep.commercial_register_number ?? ep.lei} />
              <Fact icon={Calendar} label="Incorporated" value={ep.date_of_incorporation} />
              <Fact icon={MapPin} label="Domicile" value={ep.registered_address} />
              <Fact icon={MapPin} label="Principal place" value={ep.principal_place_of_business} />
              <Fact icon={Globe} label="Website" value={ep.website} />
              <Fact icon={Calendar} label="Onboarded" value={fmtDate(customer.onboarded_as_of)} />
              <Fact icon={Calendar} label="Last review" value={fmtDate(customer.kyc_review.last_review)} />
              <Fact icon={Calendar} label="Next review (scheduled)" value={fmtDate(customer.kyc_review.next_periodic_review)} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* DISPOSITION BAR — only when an alert trigger is pending */}
      {pending ? (
        <div className="flex flex-wrap items-center gap-2 border-t border-risk-high/30 bg-risk-high-bg/50 px-5 py-3">
          <span className="mr-auto inline-flex items-center gap-1.5 text-xs font-medium text-risk-high">
            <TriangleAlert className="size-4" /> Material drift detected — disposition required (written to audit log)
          </span>
          <Button size="sm" className="gap-1.5 bg-teal text-white hover:bg-teal-hover" onClick={() => dispose("Approved")}>
            <Check className="size-4" /> Approve
          </Button>
          <Button size="sm" variant="outline" className="gap-1.5" onClick={() => dispose("Overridden")}>
            <ArrowUpRight className="size-4" /> Override
          </Button>
          <Button size="sm" className="gap-1.5 bg-risk-high text-white hover:bg-risk-high/90" onClick={() => dispose("Escalated to Re-KYC")}>
            <ShieldAlert className="size-4" /> Escalate → Re-KYC
          </Button>
        </div>
      ) : disposed ? (
        <div className="flex items-center gap-2 border-t border-surface-line bg-surface-subtle px-5 py-3 text-xs text-ink-body">
          <CheckCircle2 className="size-4 text-risk-low" />
          <span className="font-medium">{disposed}</span> by G. Cozzio · just now · written to the audit log
        </div>
      ) : null}
    </section>
  );
}
