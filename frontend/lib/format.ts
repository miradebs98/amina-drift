import type { RiskBand } from "./types";

// Band / letter / color are PURE FUNCTIONS of the 0-100 score, so the gauge,
// donuts, line chart and log can never disagree. Bands: LOW 0-33 / MED 34-66 / HIGH 67-100.

export function bandForScore(score: number): RiskBand {
  if (score <= 33) return "LOW";
  if (score <= 66) return "MEDIUM";
  return "HIGH";
}

export function letterForScore(score: number): "A" | "B" | "C" | "D" {
  if (score <= 25) return "A";
  if (score <= 50) return "B";
  if (score <= 75) return "C";
  return "D";
}

export type RiskColors = {
  fg: string;
  bg: string;
  ring: string;
  label: string;
};

const PALETTE: Record<RiskBand, RiskColors> = {
  LOW: { fg: "#15803d", bg: "#dcfce7", ring: "#4ade80", label: "LOW" },
  MEDIUM: { fg: "#b45309", bg: "#fef2d6", ring: "#facc15", label: "MEDIUM" },
  HIGH: { fg: "#b91c1c", bg: "#fee2e2", ring: "#f87171", label: "HIGH" },
};

export function colorsForBand(band: RiskBand): RiskColors {
  return PALETTE[band];
}

export function colorsForScore(score: number): RiskColors {
  return PALETTE[bandForScore(score)];
}

// dates
export function fmtDate(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

export function fmtMonthYear(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-GB", { month: "short", year: "numeric" });
}

export function toEpoch(iso: string): number {
  return new Date(iso).getTime();
}

// numbers
export function fmtScore(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return Math.round(n).toString();
}

export function fmtDelta(n: number): string {
  return n > 0 ? `+${n}` : `${n}`;
}

export function fmtTokens(n: number): string {
  return n.toLocaleString("en-US");
}

export function severityLabel(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

// Human-readable names for evidence types (MS-EV3 → "Ownership change").
const EVENT_LABELS: Record<string, string> = {
  news: "News / adverse media",
  registry_change: "Registry filing",
  ownership_change: "Ownership change",
  sanctions_hit: "Sanctions hit",
  pep_hit: "PEP match",
  website_change: "Business / website change",
  funding: "Funding round",
  transaction: "Transaction pattern",
};

export function eventTypeLabel(type: string): string {
  return EVENT_LABELS[type] ?? type.replace(/_/g, " ");
}

// Human labels for KYC predicates (business_model → "Business model").
const PREDICATE_LABELS: Record<string, string> = {
  business_model: "Business model",
  industry_sector: "Industry / sector",
  product_mix: "Products & services",
  listing_status: "Listing status",
  legal_form: "Legal form",
  domicile: "Domicile",
  principal_place_of_business: "Principal place of business",
  domain: "Website / domain",
  ubo: "Beneficial ownership",
  directors: "Directors",
  ownership_structure: "Ownership structure",
  operating_geographies: "Operating geographies",
  counterparty_geographies: "Counterparty geographies",
  expected_monthly_volume: "Expected volume",
  financial_profile: "Financial profile",
  source_of_wealth: "Source of wealth",
  source_of_funds: "Source of funds",
  activity_level: "Activity level",
  digital_asset_policy: "Digital-asset policy",
  digital_asset_holdings: "Digital-asset holdings",
  tax_residency: "Tax residency",
  tax_classification: "Tax classification",
  regulatory_status: "Regulatory status",
  pep_status: "PEP status",
  sanctions_status: "Sanctions status",
  adverse_media_status: "Adverse media",
  risk_score: "Risk score",
  risk_tier: "Risk tier",
};

export function predicateLabel(predicate: string): string {
  return PREDICATE_LABELS[predicate] ?? predicate.replace(/_/g, " ");
}

// Some assertion values are stringified JSON dicts (e.g. UBO). Render them readably.
export function formatAssertionValue(value: string): string {
  const v = value.trim();
  if (v.startsWith("{")) {
    try {
      const obj = JSON.parse(v) as Record<string, string>;
      return Object.entries(obj)
        .map(([k, val]) => `${k} (${val})`)
        .join("; ");
    } catch {
      return value;
    }
  }
  return value;
}

// initials monogram for a company logo placeholder
export function monogram(name: string): string {
  return name
    .replace(/\b(Ltd|AG|Inc|Global|Technologies|DMCC|GmbH|PLC|Corp)\b\.?/gi, "")
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
}
