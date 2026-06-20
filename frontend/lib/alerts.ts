import type { CustomerCase, EvidenceEvent, Severity } from "./types";
import { toEpoch, eventTypeLabel } from "./format";

// Derives a company-grouped alert feed from the loaded cases. Each alert states
// WHAT HAPPENED (the triggering public/internal signal) and is either:
//   - informational  (cta === null), or
//   - informational + a CTA  (the standard analyst response).
// The CTAs are grounded in the challenge brief's response actions: open EDD,
// pull the review off-cycle / Re-KYC, re-verify UBO, request source-of-wealth,
// re-baseline transaction-monitoring thresholds, screen sanctions / escalate (SAR).

export type AlertKind = "action" | "info";

export type AlertCTA = { key: string; label: string; done: string };

export type AlertItem = {
  id: string;
  customerId: string;
  company: string;
  dimension: string; // identity_ownership | network_risk | behavioural_drift | contextual_change
  type: string; // event type, or "structural" for the headline drift
  severity: Severity;
  title: string; // what happened
  detail?: string;
  date: string; // ISO
  source?: string;
  sourceUrl?: string | null;
  cta: AlertCTA | null; // null = informational only
  headline?: boolean; // the aggregated re-tiering alert
};

export type CompanyAlerts = {
  customerId: string;
  company: string;
  score: number;
  items: AlertItem[];
  counts: { total: number; action: number; high: number };
};

export const DIMENSIONS: Record<string, string> = {
  identity_ownership: "Identity & Ownership",
  network_risk: "Network Risk",
  behavioural_drift: "Behavioural Drift",
  contextual_change: "Contextual Change",
};

const SEV_RANK: Record<Severity, number> = { high: 3, medium: 2, low: 1 };

// event type → default dimension (fallback when the event has no dimension tag)
const TYPE_DIMENSION: Record<string, string> = {
  ownership_change: "identity_ownership",
  pep_hit: "identity_ownership",
  registry_change: "identity_ownership",
  sanctions_hit: "network_risk",
  news: "network_risk",
  transaction: "behavioural_drift",
  website_change: "contextual_change",
  funding: "contextual_change",
};

// event type → analyst response (severity + CTA). funding is info-only.
const TYPE_RESPONSE: Record<string, { severity: Severity; cta: AlertCTA | null }> = {
  sanctions_hit: { severity: "high", cta: { key: "sar", label: "Escalate to MLRO · file internal SAR", done: "Escalated to MLRO — SAR drafted" } },
  pep_hit: { severity: "high", cta: { key: "sow", label: "Refresh UBO & source-of-wealth", done: "Source-of-wealth refresh requested" } },
  ownership_change: { severity: "high", cta: { key: "ubo", label: "Re-verify UBO & screen new owner", done: "UBO re-verification opened" } },
  registry_change: { severity: "medium", cta: { key: "entity", label: "Verify entity & jurisdiction", done: "Entity / jurisdiction check queued" } },
  website_change: { severity: "medium", cta: { key: "edd", label: "Open EDD · business-model review", done: "EDD case opened" } },
  transaction: { severity: "medium", cta: { key: "tm", label: "Re-baseline TM thresholds", done: "TM thresholds re-baselined" } },
  news: { severity: "medium", cta: { key: "media", label: "Review adverse media", done: "Adverse-media review logged" } },
  funding: { severity: "low", cta: null },
};

const ADVERSE = /fraud|investigat|sanction|probe|lawsuit|adverse|breach|launder|terror|bribe/i;

function eventToAlert(e: EvidenceEvent, customerId: string, company: string): AlertItem {
  const resp = TYPE_RESPONSE[e.type] ?? { severity: "low" as Severity, cta: null };
  // neutral/positive news is informational; only adverse news carries a CTA
  const info = e.type === "news" && !ADVERSE.test(e.summary);
  return {
    id: e.id,
    customerId,
    company,
    dimension: e.dimension ?? TYPE_DIMENSION[e.type] ?? "contextual_change",
    type: e.type,
    severity: info ? "low" : resp.severity,
    title: e.summary,
    date: e.published_at,
    source: e.source,
    sourceUrl: e.source_url,
    cta: info ? null : resp.cta,
  };
}

export function buildAlertFeed(cases: CustomerCase[]): CompanyAlerts[] {
  const groups = cases.map(({ customer, events, alert }) => {
    const company = customer.legal_name;
    const score = alert.new_risk_score ?? customer.risk_model.onboarding_score;
    const items: AlertItem[] = [];

    // headline: the aggregated re-tiering / drift alert (only when there is real drift)
    const drifted = (alert.drift_score ?? 0) > 0 || alert.new_risk_tier !== alert.old_risk_tier;
    if (drifted) {
      items.push({
        id: alert.id,
        customerId: customer.customer_id,
        company,
        dimension: "contextual_change",
        type: "structural",
        severity: alert.severity,
        title: alert.flag,
        detail: alert.recommended_action,
        date: alert.created_at,
        source: alert.model_used && alert.model_used !== "none" ? "drift engine" : undefined,
        cta: { key: "edd", label: "Open Enhanced Due Diligence", done: "EDD case opened — review pulled off-cycle" },
        headline: true,
      });
    }

    // one alert per public/internal signal
    const drivers = new Set(alert.evidence_ids);
    const evAlerts = [...events]
      .map((e) => ({ a: eventToAlert(e, customer.customer_id, company), drove: drivers.has(e.id) }))
      // surface evidence that drove the drift first, then everything else
      .sort((x, y) => {
        if (x.drove !== y.drove) return x.drove ? -1 : 1;
        if (SEV_RANK[y.a.severity] !== SEV_RANK[x.a.severity]) return SEV_RANK[y.a.severity] - SEV_RANK[x.a.severity];
        return toEpoch(y.a.date) - toEpoch(x.a.date);
      })
      .map((x) => x.a);
    items.push(...evAlerts);

    const counts = {
      total: items.length,
      action: items.filter((i) => i.cta).length,
      high: items.filter((i) => i.severity === "high").length,
    };
    return { customerId: customer.customer_id, company, score, items, counts };
  });

  // most-at-risk companies first
  return groups.sort((a, b) => b.score - a.score);
}

export { eventTypeLabel };
