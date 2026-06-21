"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
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
  UserCog,
} from "lucide-react";
import type { Customer, DriftAlert, DecisionAction, DecisionResult, Role } from "@/lib/types";
import { bandForScore, colorsForScore, fmtDate } from "@/lib/format";
import { CompanyLogo } from "@/components/shared/company-logo";

const ACTION_LABEL: Record<DecisionAction, string> = {
  approve: "Approve",
  override: "Override",
  escalate: "Escalate → Re-KYC",
};
const STATE_LABEL: Record<string, string> = {
  approved: "Approved",
  dismissed: "Overridden",
  escalated: "Escalated → Re-KYC",
};

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

export function ClientSection({
  customer,
  alert,
  currentScore,
  role,
  onRoleChange,
  dispo,
  onDispose,
}: {
  customer: Customer;
  alert: DriftAlert;
  currentScore?: number;
  role: Role;
  onRoleChange: (r: Role) => void;
  dispo: DecisionResult | null;
  onDispose: (action: DecisionAction, note: string) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [action, setAction] = useState<DecisionAction | null>(null);
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ep = customer.entity_profile;
  const score = currentScore ?? alert.new_risk_score ?? customer.risk_model.onboarding_score;
  const band = bandForScore(score);
  const c = colorsForScore(score);
  const materialChanges = (alert.contradicted_assertion_id ? 1 : 0) + alert.also_contradicts.length;
  const pending = alert.governance_state === "pending" && !dispo;

  function openDialog(a: DecisionAction) {
    setAction(a);
    setNote("");
    setError(null);
  }

  async function confirm() {
    if (!action) return;
    setSubmitting(true);
    setError(null);
    try {
      await onDispose(action, note);
      setAction(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Decision failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="overflow-hidden rounded-card border border-surface-line bg-white shadow-card">
      {/* HEADER — always visible; click to expand details */}
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-4 p-5 text-left transition-colors hover:bg-surface-subtle"
      >
        <CompanyLogo customerId={customer.customer_id} name={customer.legal_name} size={48} className="shadow-card" />
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

      {/* DISPOSITION BAR — temporarily removed (to be repositioned later).
          The handlers + dialog below stay wired so it can be dropped back in. */}

      {/* DISPOSITION DIALOG — note capture + four-eyes role */}
      <Dialog open={action !== null} onOpenChange={(o) => !o && setAction(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{action ? ACTION_LABEL[action] : ""} — disposition</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <p className="text-sm text-ink-muted">
              This decision is written to the immutable, hash-chained audit log with your ID, the model version,
              a timestamp, and your note.
            </p>

            {/* role (four-eyes) */}
            <div>
              <div className="mb-1.5 text-xs font-medium uppercase tracking-wide text-ink-muted">Acting as</div>
              <div className="inline-flex overflow-hidden rounded-md border border-surface-line">
                {(["analyst", "mlro"] as Role[]).map((r) => (
                  <button
                    key={r}
                    onClick={() => onRoleChange(r)}
                    className={`px-3 py-1.5 text-xs font-medium capitalize transition-colors ${
                      role === r ? "bg-brand text-white" : "bg-white text-ink-muted hover:bg-surface-subtle"
                    }`}
                  >
                    {r === "mlro" ? "MLRO" : "Analyst"}
                  </button>
                ))}
              </div>
            </div>

            {/* note */}
            <div>
              <div className="mb-1.5 text-xs font-medium uppercase tracking-wide text-ink-muted">Reviewer note</div>
              <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                rows={3}
                placeholder="Why this disposition? (recorded in the audit trail)"
                className="w-full resize-none rounded-md border border-surface-line bg-white p-2.5 text-sm outline-none focus:border-teal focus:ring-1 focus:ring-teal"
              />
            </div>

            {error && (
              <div className="inline-flex items-start gap-1.5 rounded-md bg-risk-high-bg px-3 py-2 text-xs font-medium text-risk-high">
                <TriangleAlert className="mt-0.5 size-3.5 shrink-0" /> {error}
                {role !== "mlro" && /mlro/i.test(error) && (
                  <span className="font-normal"> — switch to MLRO above and retry.</span>
                )}
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setAction(null)} disabled={submitting}>
              Cancel
            </Button>
            <Button size="sm" className="bg-teal text-white hover:bg-teal-hover" onClick={confirm} disabled={submitting}>
              {submitting ? "Recording…" : `Confirm ${action ? ACTION_LABEL[action] : ""}`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
