"use client";

import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Radar, ExternalLink, RefreshCw } from "lucide-react";
import type { CustomerCase, EvidenceEvent } from "@/lib/types";
import { fmtDate, toEpoch } from "@/lib/format";

type Sentiment = "adverse" | "positive" | "neutral";
type NewsItem = {
  source: string;
  headline: string;
  date: string;
  sentiment: Sentiment;
  url?: string | null;
  simulated?: boolean;
};

const SENT: Record<Sentiment, { dot: string; label: string; cls: string }> = {
  adverse: { dot: "#b91c1c", label: "Adverse", cls: "text-risk-high" },
  positive: { dot: "#15803d", label: "Positive", cls: "text-risk-low" },
  neutral: { dot: "#9ca3af", label: "Neutral", cls: "text-ink-muted" },
};

function sentimentForEvent(e: EvidenceEvent): Sentiment {
  if (["sanctions_hit", "pep_hit"].includes(e.type)) return "adverse";
  if (e.type === "news" && /fraud|investigation|suit|sanction|breach/i.test(e.summary)) return "adverse";
  if (e.type === "funding") return "positive";
  return "neutral";
}

// curated context the engine would also watch (shareholders + sector)
const EXTRA: Record<string, { shareholders: NewsItem[]; context: NewsItem[] }> = {
  "coinbase-global": {
    shareholders: [
      { source: "SEC Form 4", headline: "Brian Armstrong sells shares under 10b5-1 plan", date: "2025-01-15", sentiment: "neutral", url: "https://www.sec.gov/", simulated: false },
      { source: "a16z", headline: "Early backer reaffirms long-term crypto thesis", date: "2024-09-01", sentiment: "positive", simulated: false },
    ],
    context: [
      { source: "US SEC", headline: "SEC signals softer crypto-enforcement posture in 2025", date: "2025-02-27", sentiment: "neutral", url: "https://www.sec.gov/", simulated: false },
      { source: "ESMA", headline: "EU MiCA regime fully in force across member states", date: "2025-06-20", sentiment: "neutral", simulated: false },
      { source: "Bloomberg", headline: "Spot Bitcoin ETF inflows hit fresh record", date: "2025-03-10", sentiment: "positive", simulated: false },
    ],
  },
};

function Item({ n }: { n: NewsItem }) {
  const s = SENT[n.sentiment];
  return (
    <div className="border-b border-surface-line px-4 py-3 last:border-0">
      <div className="flex items-center gap-2 text-[11px] text-ink-muted">
        <span className="inline-block size-1.5 rounded-full" style={{ background: s.dot }} />
        <span className="font-medium">{n.source}</span>
        <span className="tabular ml-auto">{fmtDate(n.date)}</span>
      </div>
      <p className="mt-1 text-sm leading-snug text-ink">{n.headline}</p>
      <div className="mt-1 flex items-center gap-2 text-[10px]">
        <span className={`font-medium uppercase tracking-wide ${s.cls}`}>{s.label}</span>
        {n.url ? (
          <a href={n.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-teal-hover hover:underline">
            open <ExternalLink className="size-3" />
          </a>
        ) : null}
      </div>
    </div>
  );
}

export function NewsPanel({ data }: { data: CustomerCase }) {
  const company: NewsItem[] = [...data.events]
    .sort((a, b) => toEpoch(b.published_at) - toEpoch(a.published_at))
    .map((e) => ({
      source: e.source,
      headline: e.summary,
      date: e.published_at,
      sentiment: sentimentForEvent(e),
      url: e.source_url,
      simulated: !e.source_url,
    }));

  const extra = EXTRA[data.customer.customer_id] ?? { shareholders: [], context: [] };

  return (
    <aside className="flex flex-col overflow-hidden rounded-card border border-surface-line bg-white shadow-card">
      <div className="flex items-center gap-2 border-b border-surface-line bg-brand px-4 py-3 text-white">
        <Radar className="size-4 text-teal-bright" />
        <div className="flex-1">
          <div className="text-sm font-semibold">News &amp; Social radar</div>
          <div className="text-[10px] text-white/55">company · shareholders · sector context</div>
        </div>
        <RefreshCw className="size-3.5 text-white/50" />
      </div>

      <Tabs defaultValue="company" className="flex min-h-0 flex-1 flex-col">
        <TabsList className="m-2 grid grid-cols-3">
          <TabsTrigger value="company" className="text-xs">Company</TabsTrigger>
          <TabsTrigger value="holders" className="text-xs">Owners</TabsTrigger>
          <TabsTrigger value="context" className="text-xs">Sector</TabsTrigger>
        </TabsList>
        <div className="max-h-[560px] overflow-y-auto">
          <TabsContent value="company" className="m-0">
            {company.map((n, i) => <Item key={i} n={n} />)}
          </TabsContent>
          <TabsContent value="holders" className="m-0">
            {extra.shareholders.map((n, i) => <Item key={i} n={n} />)}
          </TabsContent>
          <TabsContent value="context" className="m-0">
            {extra.context.map((n, i) => <Item key={i} n={n} />)}
          </TabsContent>
        </div>
      </Tabs>
    </aside>
  );
}
