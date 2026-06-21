"use client";

import type { Customer, Role } from "@/lib/types";
import { restrictedAssertions, RESTRICTED_ENTITY_FIELDS, MASK_TOKEN, canReveal } from "@/lib/policy";
import { predicateLabel, formatAssertionValue } from "@/lib/format";
import { Lock, Globe, ShieldCheck, Eye, EyeOff, TriangleAlert } from "lucide-react";

// Public (Layer 1) vs internal (Layer 2) data separation + masking of PII-grade KYC fields,
// with an RBAC-gated, audited reveal. Display logic only — the values it masks never reach scoring.
export function DataProtectionBar({
  customer,
  role,
  onRoleChange,
  revealed,
  revealing,
  error,
  onReveal,
  onHide,
}: {
  customer: Customer;
  role: Role;
  onRoleChange: (r: Role) => void;
  revealed: boolean;
  revealing: boolean;
  error: string | null;
  onReveal: () => void;
  onHide: () => void;
}) {
  const rows = [
    ...restrictedAssertions(customer).map((a) => ({ key: a.id, label: predicateLabel(a.predicate), value: a.value })),
    ...RESTRICTED_ENTITY_FIELDS.flatMap((f) => {
      const v = customer.entity_profile?.[f];
      return v ? [{ key: f, label: "Tax ID (TIN)", value: String(v) }] : [];
    }),
  ];
  if (rows.length === 0) return null;
  const allowed = canReveal(role);

  return (
    <section className="rounded-card border border-surface-line bg-white shadow-card">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-surface-line px-5 py-3">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
          <Lock className="size-4 text-ink-muted" />
          <span className="font-medium text-ink">Data protection</span>
          <span className="text-ink-muted">·</span>
          <span className="inline-flex items-center gap-1 text-xs text-ink-muted">
            <Globe className="size-3.5" /> Layer 1 public — shown
          </span>
          <span className="text-ink-muted">·</span>
          <span className="inline-flex items-center gap-1 text-xs text-ink-muted">
            <Lock className="size-3.5" /> Layer 2 internal —{" "}
            {revealed ? "revealed" : `${rows.length} field${rows.length > 1 ? "s" : ""} masked`}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {/* acting role (RBAC / four-eyes) */}
          <div className="inline-flex overflow-hidden rounded-md border border-surface-line">
            {(["analyst", "mlro"] as Role[]).map((r) => (
              <button
                key={r}
                onClick={() => onRoleChange(r)}
                className={`px-2.5 py-1 text-xs font-medium transition-colors ${
                  role === r ? "bg-brand text-white" : "bg-white text-ink-muted hover:bg-surface-subtle"
                }`}
              >
                {r === "mlro" ? "MLRO" : "Analyst"}
              </button>
            ))}
          </div>
          {revealed ? (
            <button
              onClick={onHide}
              className="inline-flex items-center gap-1.5 rounded-md border border-surface-line bg-white px-2.5 py-1 text-xs text-ink-body hover:bg-surface-subtle"
            >
              <EyeOff className="size-3.5" /> Hide
            </button>
          ) : (
            <button
              onClick={onReveal}
              disabled={revealing}
              className="inline-flex items-center gap-1.5 rounded-md bg-teal px-2.5 py-1 text-xs font-semibold text-white hover:bg-teal-hover disabled:opacity-50"
            >
              <Eye className="size-3.5" /> {revealing ? "Revealing…" : "Reveal restricted"}
            </button>
          )}
        </div>
      </div>

      <div className="grid gap-x-6 gap-y-2 px-5 py-3 sm:grid-cols-2">
        {rows.map((r) => (
          <div key={r.key} className="flex items-start gap-2 text-sm">
            <span className="mt-0.5 inline-block w-40 shrink-0 text-[11px] uppercase tracking-wide text-ink-muted">
              {r.label}
            </span>
            <span className={`min-w-0 break-words ${revealed ? "text-ink" : "italic text-ink-muted"}`}>
              {revealed ? formatAssertionValue(r.value) : MASK_TOKEN}
            </span>
          </div>
        ))}
      </div>

      {revealed && (
        <div className="flex items-center gap-1.5 border-t border-surface-line bg-risk-low-bg/40 px-5 py-2 text-xs text-risk-low">
          <ShieldCheck className="size-3.5" /> Revealed under role “{role}” — written to the immutable audit log.
        </div>
      )}
      {error && (
        <div className="flex items-start gap-1.5 border-t border-surface-line bg-risk-high-bg px-5 py-2 text-xs font-medium text-risk-high">
          <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
          {error}
          {!allowed && /mlro|compliance/i.test(error) ? " — switch to MLRO above and retry." : ""}
        </div>
      )}
      {!revealed && !error && (
        <div className="border-t border-surface-line px-5 py-2 text-[11px] text-ink-muted">
          Need-to-know: beneficial ownership, source of funds/wealth and tax IDs are masked by default.{" "}
          {allowed ? "Your role may reveal them (audited)." : "Revealing requires MLRO/Compliance sign-off (audited)."}
        </div>
      )}
    </section>
  );
}
