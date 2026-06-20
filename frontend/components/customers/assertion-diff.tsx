"use client";

import { useState } from "react";
import type { CustomerCase, EvidenceEvent } from "@/lib/types";
import { getTwinDiff } from "@/lib/diff";
import { predicateLabel, formatAssertionValue } from "@/lib/format";
import { ArrowRight, Check, Lock, Globe } from "lucide-react";

export function AssertionDiff({
  data,
  onSelectEvent,
}: {
  data: CustomerCase;
  onSelectEvent?: (e: EvidenceEvent) => void;
}) {
  const [onlyChanged, setOnlyChanged] = useState(true);
  const { rows, changed, total } = getTwinDiff(data);
  const byId = new Map(data.events.map((e) => [e.id, e]));
  const shown = onlyChanged ? rows.filter((r) => r.changed) : rows;

  return (
    <div className="flex flex-col">
      {/* column legend */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-4 text-xs">
          <span className="inline-flex items-center gap-1.5 text-ink-muted">
            <Lock className="size-3.5" /> Internal · onboarding belief (Layer 2)
          </span>
          <ArrowRight className="size-3.5 text-ink-muted" />
          <span className="inline-flex items-center gap-1.5 text-ink-muted">
            <Globe className="size-3.5" /> Public · live evidence (Layer 1)
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="rounded-pill bg-risk-high-bg px-2.5 py-0.5 text-xs font-semibold text-risk-high">
            {changed} of {total} contradicted
          </span>
          <label className="flex cursor-pointer items-center gap-1.5 text-xs text-ink-muted">
            <input
              type="checkbox"
              checked={onlyChanged}
              onChange={(e) => setOnlyChanged(e.target.checked)}
              className="size-3.5 accent-teal"
            />
            only changed
          </label>
        </div>
      </div>

      <div className="overflow-hidden rounded-md border border-surface-line">
        {shown.map((r, i) => (
          <div
            key={r.assertionId}
            className={`grid grid-cols-[150px_1fr_1fr] items-start gap-3 px-3 py-2.5 text-sm ${
              i > 0 ? "border-t border-surface-line" : ""
            } ${r.changed ? "bg-risk-high-bg/40" : "bg-white"}`}
          >
            {/* predicate */}
            <div className="flex items-center gap-1.5 pt-0.5">
              <span
                className={`inline-block size-1.5 rounded-full ${r.changed ? "bg-risk-high" : "bg-risk-low"}`}
              />
              <span className="text-xs font-medium text-ink">{predicateLabel(r.predicate)}</span>
            </div>

            {/* THEN */}
            <div className="min-w-0 text-ink-body">
              <span className={r.changed ? "line-through decoration-risk-high/40" : ""}>
                {formatAssertionValue(r.then)}
              </span>
            </div>

            {/* NOW */}
            <div className="min-w-0">
              {r.changed ? (
                <>
                  <div className="font-medium text-risk-high">{r.now}</div>
                  {r.evidenceIds.length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-1">
                      {r.evidenceIds.map((id) => {
                        const ev = byId.get(id);
                        const sim = ev && !ev.source_url;
                        return (
                          <button
                            key={id}
                            onClick={() => ev && onSelectEvent?.(ev)}
                            title={ev?.summary}
                            className="inline-flex items-center gap-1 rounded-pill border border-surface-line bg-white px-2 py-0.5 text-[10px] text-teal-hover hover:border-teal hover:bg-teal-wash"
                          >
                            {sim ? "cited (sim)" : "cited"}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </>
              ) : (
                <span className="inline-flex items-center gap-1.5 text-ink-muted">
                  <Check className="size-3.5 text-risk-low" /> {r.now}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
