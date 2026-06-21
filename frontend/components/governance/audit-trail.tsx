"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getAudit, verifyAudit } from "@/lib/api";
import type { AuditRow, VerifyResult } from "@/lib/types";
import { fmtDate } from "@/lib/format";
import { ShieldCheck, ShieldX, ScrollText, RefreshCw, Lock } from "lucide-react";

const ACTION_LABEL: Record<string, string> = {
  human_approved: "Approved",
  human_dismissed: "Overridden / dismissed",
  human_escalated: "Escalated → Re-KYC",
  alert_created: "Alert created",
  stage_escalated: "Stage escalated",
  profile_updated: "Profile updated",
  internal_data_revealed: "Restricted KYC data revealed",
};

function short(h?: string | null) {
  return h ? `${h.slice(0, 10)}…` : "—";
}

export function AuditTrail({ customerId, alertId }: { customerId: string; alertId?: string }) {
  const [verify, setVerify] = useState<VerifyResult | null>(null);
  const [verifying, setVerifying] = useState(false);

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery<AuditRow[]>({
    queryKey: ["audit", customerId],
    queryFn: () => getAudit(customerId),
    retry: false,
    refetchOnWindowFocus: false,
  });

  async function runVerify() {
    setVerifying(true);
    try {
      setVerify(await verifyAudit());
    } catch {
      setVerify(null);
    } finally {
      setVerifying(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="inline-flex items-center gap-1.5 text-xs text-ink-muted">
          <Lock className="size-3.5" /> Append-only, hash-chained · stores hashes + model provenance, never raw KYC/PII.
        </p>
        <div className="flex items-center gap-2">
          <button
            onClick={() => refetch()}
            className="inline-flex items-center gap-1.5 rounded-md border border-surface-line bg-white px-2.5 py-1 text-xs text-ink-body hover:bg-surface-subtle"
          >
            <RefreshCw className={`size-3.5 ${isFetching ? "animate-spin" : ""}`} /> Refresh
          </button>
          <button
            onClick={runVerify}
            disabled={verifying}
            className="inline-flex items-center gap-1.5 rounded-md bg-brand px-2.5 py-1 text-xs font-semibold text-white hover:bg-brand-deep disabled:opacity-50"
          >
            <ShieldCheck className="size-3.5" /> Verify integrity
          </button>
        </div>
      </div>

      {/* verify badge */}
      {verify &&
        (verify.ok ? (
          <div className="inline-flex items-center gap-2 rounded-md bg-risk-low-bg px-3 py-2 text-sm font-medium text-risk-low">
            <ShieldCheck className="size-4" /> Chain intact — {verify.length} entries verified · tamper-evident ✓
          </div>
        ) : (
          <div className="inline-flex items-center gap-2 rounded-md bg-risk-high-bg px-3 py-2 text-sm font-medium text-risk-high">
            <ShieldX className="size-4" /> Tampering detected — chain broke at entry #{verify.broken_at_seq}
          </div>
        ))}

      {/* trail */}
      {isLoading ? (
        <div className="text-sm text-ink-muted">Loading audit trail…</div>
      ) : isError ? (
        <div className="rounded-md border border-surface-line bg-surface-subtle p-4 text-sm text-ink-muted">
          {(error as Error)?.message ?? "Audit backend not reachable."}
          <div className="mt-1 text-xs">
            Start the API to see the live trail: <code className="rounded bg-surface-card px-1">uvicorn backend.api.main:app --port 8000</code>
          </div>
        </div>
      ) : !data || data.length === 0 ? (
        <div className="flex items-center gap-2 rounded-md border border-dashed border-surface-line p-4 text-sm text-ink-muted">
          <ScrollText className="size-4" /> No decisions recorded yet — disposition this alert to write the first entry.
        </div>
      ) : (
        <div className="overflow-hidden rounded-md border border-surface-line">
          {data.map((r, i) => (
            <div key={r.id} className={`px-4 py-3 text-sm ${i > 0 ? "border-t border-surface-line" : ""}`}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="tabular text-xs text-ink-muted">#{r.seq}</span>
                <span className="font-medium text-ink">{ACTION_LABEL[r.action] ?? r.action}</span>
                <span className="text-xs text-ink-muted">
                  by {r.actor} ({r.role})
                </span>
                <span className="tabular ml-auto text-xs text-ink-muted">{fmtDate(r.timestamp)}</span>
              </div>
              {/* WHAT was decided — the frozen decision snapshot */}
              {(() => {
                const d = r.details?.decision as
                  | { flag?: string; old_risk?: string; new_risk?: string; evidence_count?: number; recommended_action?: string }
                  | undefined;
                if (!d) return null;
                return (
                  <div className="mt-1.5 rounded-md border border-surface-line bg-surface-subtle px-2.5 py-1.5">
                    <div className="text-[13px] font-medium text-ink">{d.flag ?? "—"}</div>
                    <div className="mt-0.5 flex flex-wrap items-center gap-x-3 text-[11px] text-ink-muted">
                      {d.old_risk && d.new_risk && (
                        <span className="tabular">risk {d.old_risk} → {d.new_risk}</span>
                      )}
                      {typeof d.evidence_count === "number" && <span>{d.evidence_count} cited signals</span>}
                      {d.recommended_action && <span className="truncate">action: {d.recommended_action}</span>}
                    </div>
                  </div>
                );
              })()}
              {typeof r.details?.note === "string" && r.details.note && (
                <div className="mt-1 text-sm text-ink-body">“{r.details.note}”</div>
              )}
              <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-ink-muted">
                {r.model_name && r.model_name !== "none" && (
                  <span>model: {r.model_name}{r.model_version ? ` · ${r.model_version}` : ""}</span>
                )}
                {r.policy_version && <span>policy: {r.policy_version}</span>}
                <span className="tabular">inputs_hash: {short(r.inputs_hash)}</span>
                <span className="tabular">entry_hash: {short(r.entry_hash)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
