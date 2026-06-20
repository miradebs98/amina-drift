import type { CustomerCase, EvidenceEvent } from "./types";
import { eventTypeLabel, fmtDate, bandForScore, toEpoch } from "./format";

// Grounded "ask the data" engine. Answers are derived ONLY from the loaded case
// (events, alert, assertions) and always carry citations — no free invention.
// Swappable later for POST /api/customers/{id}/ask without changing the chat UI.

export type Citation = {
  id: string;
  label: string;
  date: string;
  source: string;
  url?: string | null;
  simulated: boolean;
};

export type Answer = {
  text: string;
  citations: Citation[];
  coverage: "grounded" | "partial" | "insufficient";
};

export const SUGGESTED = [
  "Why is the risk HIGH?",
  "What drove the drift?",
  "What happened with ownership?",
  "What would lower the risk?",
  "What happened in 2024?",
];

const MONTHS = [
  "january", "february", "march", "april", "may", "june",
  "july", "august", "september", "october", "november", "december",
];

function toCitation(e: EvidenceEvent): Citation {
  return {
    id: e.id,
    label: eventTypeLabel(e.type),
    date: fmtDate(e.published_at),
    source: e.source,
    url: e.source_url,
    simulated: !e.source_url,
  };
}

export function askData(question: string, c: CustomerCase): Answer {
  const q = question.toLowerCase().trim();
  const { customer, events, alert } = c;
  const old = alert.old_risk_score ?? customer.risk_model.onboarding_score;
  const now = alert.new_risk_score ?? old;
  const sorted = [...events].sort((a, b) => toEpoch(a.published_at) - toEpoch(b.published_at));
  const cite = (list: EvidenceEvent[]) => list.map(toCitation);
  const driverEvents = alert.evidence_ids
    .map((id) => events.find((e) => e.id === id))
    .filter((e): e is EvidenceEvent => Boolean(e));

  // why is it high / explain the flag
  if (/\b(why|explain|reason|what.*(flag|elevated|happened to))\b/.test(q) && /\b(high|risk|score|drift|flag|elevated|rating|tier)\b/.test(q)) {
    return {
      text: `${customer.legal_name}'s risk score moved from ${old} (${bandForScore(old)}) to ${now} (${bandForScore(now)}).\n\n${alert.rationale}`,
      citations: cite(driverEvents).slice(0, 6),
      coverage: "grounded",
    };
  }

  // what would flip / lower the risk
  if (/\b(flip|lower|reduce|drop|de-?risk|improve|clear|resolve)\b/.test(q) && /\b(risk|score|this|decision|rating|it)\b/.test(q)) {
    return {
      text: `To bring the risk back down:\n\n${alert.what_would_flip ?? alert.recommended_action}`,
      citations: [],
      coverage: "partial",
    };
  }

  // drivers / what caused it
  if (/\b(driver|drove|cause|caused|contribut|pushed|raised|behind|factors?)\b/.test(q)) {
    const cs = cite(driverEvents);
    return {
      text:
        `The drift is the sum of ${cs.length} signals:\n` +
        cs.map((x) => `•  ${x.label} — ${x.date}`).join("\n"),
      citations: cs,
      coverage: "grounded",
    };
  }

  // ownership
  if (/\b(owner|ownership|ubo|shareholder|stake|beneficial|control)\b/.test(q)) {
    const evs = events.filter((e) => e.type === "ownership_change");
    const ubo = customer.assertions.find((a) => a.predicate === "ubo");
    return {
      text:
        `At onboarding the beneficial owners were: ${ubo?.value ?? "n/a"}.\n\n` +
        (evs.length
          ? evs.map((e) => `Since then: ${e.summary} (${fmtDate(e.published_at)}).`).join("\n")
          : "No ownership changes have been detected since onboarding."),
      citations: cite(evs),
      coverage: evs.length ? "grounded" : "partial",
    };
  }

  // sanctions
  if (/\bsanction|ofac|watchlist|embargo\b/.test(q)) {
    const evs = events.filter((e) => e.type === "sanctions_hit");
    const a = customer.assertions.find((x) => x.predicate === "sanctions_status");
    return {
      text: evs.length
        ? evs.map((e) => `${e.summary} (${fmtDate(e.published_at)}).`).join("\n")
        : `No direct sanctions designation on file. Onboarding status: ${a?.value ?? "no exposure"}. Note: jurisdictional expansion can raise indirect nexus risk.`,
      citations: cite(evs),
      coverage: evs.length ? "grounded" : "partial",
    };
  }

  // PEP
  if (/\bpep\b|politically exposed/.test(q)) {
    const evs = events.filter((e) => e.type === "pep_hit" || /pep|politically/i.test(e.summary));
    return {
      text: evs.length
        ? evs.map((e) => `${e.summary} (${fmtDate(e.published_at)}).`).join("\n")
        : "No PEP match recorded at onboarding; watch the latest ownership change for PEP-adjacency.",
      citations: cite(evs),
      coverage: evs.length ? "grounded" : "partial",
    };
  }

  // crypto / business pivot
  if (/\b(crypto|web3|business model|pivot|digital asset|product)\b/.test(q)) {
    const evs = events.filter(
      (e) => e.type === "website_change" || /crypto|web3|trading|brokerage|treasury/i.test(e.summary),
    );
    return {
      text: evs.length
        ? `Business-activity signals:\n` + evs.map((e) => `•  ${e.summary} (${fmtDate(e.published_at)})`).join("\n")
        : "No business-model change detected.",
      citations: cite(evs),
      coverage: evs.length ? "grounded" : "partial",
    };
  }

  // recent / last month
  if (/\b(last month|recently|lately|recent|latest|past (month|weeks?|days?|30 days))\b/.test(q)) {
    const today = new Date();
    const cutoff = today.getTime() - 120 * 864e5;
    const recent = sorted.filter((e) => toEpoch(e.published_at) >= cutoff);
    if (recent.length) {
      return {
        text: `Signals in the recent period:\n` + recent.map((e) => `•  ${e.summary} (${fmtDate(e.published_at)})`).join("\n"),
        citations: cite(recent),
        coverage: "grounded",
      };
    }
    const last = sorted[sorted.length - 1];
    return {
      text: last
        ? `No new public signals in the last ~120 days. The most recent was: ${last.summary} (${fmtDate(last.published_at)}).`
        : "No signals on file.",
      citations: last ? cite([last]) : [],
      coverage: last ? "partial" : "insufficient",
    };
  }

  // date-specific (year and/or month)
  const year = q.match(/20\d{2}/)?.[0];
  const monthIdx = MONTHS.findIndex((m) => q.includes(m));
  if (year || monthIdx >= 0 || /\bwhat happened|what occurred|any (news|events|signals|activity)\b/.test(q)) {
    const inRange = sorted.filter((e) => {
      const d = new Date(e.published_at);
      if (year && String(d.getFullYear()) !== year) return false;
      if (monthIdx >= 0 && d.getMonth() !== monthIdx) return false;
      return true;
    });
    const when = [monthIdx >= 0 ? MONTHS[monthIdx] : "", year ?? ""].filter(Boolean).join(" ") || "that period";
    if (inRange.length) {
      return {
        text: `In ${when}:\n` + inRange.map((e) => `•  ${e.summary} (${fmtDate(e.published_at)})`).join("\n"),
        citations: cite(inRange),
        coverage: "grounded",
      };
    }
    return { text: `No public signals were detected in ${when}.`, citations: [], coverage: "insufficient" };
  }

  // fallback — overview
  return {
    text:
      `${customer.legal_name} — current risk ${now} (${bandForScore(now)}), up from ${old} at onboarding.\n` +
      `${driverEvents.length} signals on file. Recommended action: ${alert.recommended_action}\n\n` +
      `Try: "why is the risk high?", "what drove the drift?", "what happened in 2024?", or "what would lower the risk?"`,
    citations: cite(driverEvents).slice(0, 4),
    coverage: "partial",
  };
}
