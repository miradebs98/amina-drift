"use client";

import { useRef, useState } from "react";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Input } from "@/components/ui/input";
import { Sparkles, Send, ExternalLink, ShieldCheck } from "lucide-react";
import type { CustomerCase } from "@/lib/types";
import { askData, SUGGESTED, type Citation } from "@/lib/ask";

type Msg = { role: "user" | "assistant"; text: string; citations?: Citation[]; coverage?: string };

function CitationChip({ c }: { c: Citation }) {
  const body = (
    <>
      <span className="font-medium">{c.label}</span>
      <span className="text-ink-muted">· {c.date}</span>
      {c.simulated ? null : <ExternalLink className="size-3" />}
    </>
  );
  const cls =
    "inline-flex items-center gap-1 rounded-pill border border-surface-line bg-white px-2 py-0.5 text-[10px] text-teal-hover hover:border-teal hover:bg-teal-wash";
  return c.url ? (
    <a href={c.url} target="_blank" rel="noreferrer" className={cls} title={c.source}>
      {body}
    </a>
  ) : (
    <span className={cls} title={c.source}>
      {body}
    </span>
  );
}

export function AskChat({ data }: { data: CustomerCase }) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  function send(q: string) {
    const question = q.trim();
    if (!question) return;
    const a = askData(question, data);
    setMessages((m) => [
      ...m,
      { role: "user", text: question },
      { role: "assistant", text: a.text, citations: a.citations, coverage: a.coverage },
    ]);
    setInput("");
    requestAnimationFrame(() => scrollRef.current?.scrollTo({ top: 9e9, behavior: "smooth" }));
  }

  return (
    <>
      {/* FAB — always visible, bottom-right */}
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-6 right-6 z-50 inline-flex items-center gap-2 rounded-pill bg-brand px-4 py-3 text-sm font-semibold text-white shadow-card transition-transform hover:scale-[1.03] hover:bg-brand-deep"
      >
        <Sparkles className="size-4 text-teal-bright" /> Ask AMINA
      </button>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="right" className="flex w-full flex-col gap-0 p-0 sm:max-w-[420px]">
          <SheetHeader className="border-b border-surface-line bg-brand px-4 py-3 text-white">
            <SheetTitle className="flex items-center gap-2 text-white">
              <Sparkles className="size-4 text-teal-bright" /> AMINA Intelligence
            </SheetTitle>
            <p className="text-[11px] text-white/60">
              {data.customer.legal_name} · read-only · answers cited from this client&apos;s evidence
            </p>
          </SheetHeader>

          {/* messages */}
          <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto p-4">
            {messages.length === 0 && (
              <div className="space-y-3">
                <div className="flex items-start gap-2 rounded-md bg-teal-wash p-3 text-sm text-ink-body">
                  <ShieldCheck className="mt-0.5 size-4 shrink-0 text-teal-hover" />
                  Ask anything about this client&apos;s drift. Every answer is grounded in the evidence on
                  file — no claim without a source. It explains; it never decides.
                </div>
                <div className="text-[11px] font-medium uppercase tracking-wide text-ink-muted">Try</div>
                <div className="flex flex-wrap gap-2">
                  {SUGGESTED.map((s) => (
                    <button
                      key={s}
                      onClick={() => send(s)}
                      className="rounded-pill border border-surface-line bg-white px-3 py-1.5 text-xs text-ink-body transition-colors hover:border-teal hover:bg-teal-wash"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((m, i) =>
              m.role === "user" ? (
                <div key={i} className="flex justify-end">
                  <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-brand px-3 py-2 text-sm text-white">
                    {m.text}
                  </div>
                </div>
              ) : (
                <div key={i} className="flex flex-col gap-2">
                  <div className="max-w-[92%] whitespace-pre-line rounded-2xl rounded-bl-sm bg-surface-card px-3 py-2 text-sm text-ink">
                    {m.text}
                  </div>
                  {m.citations && m.citations.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      <span className="text-[10px] uppercase tracking-wide text-ink-muted">
                        Sources ({m.citations.length})
                      </span>
                      {m.citations.map((c) => (
                        <CitationChip key={c.id} c={c} />
                      ))}
                    </div>
                  )}
                  {m.coverage === "insufficient" && (
                    <span className="text-[11px] text-risk-med">⚠ Limited evidence — not enough on file to answer fully.</span>
                  )}
                </div>
              ),
            )}
          </div>

          {/* input */}
          <div className="border-t border-surface-line p-3">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                send(input);
              }}
              className="flex items-center gap-2"
            >
              <Input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask about this client…"
                className="flex-1"
              />
              <button
                type="submit"
                className="inline-flex size-9 items-center justify-center rounded-md bg-teal text-white transition-colors hover:bg-teal-hover disabled:opacity-40"
                disabled={!input.trim()}
              >
                <Send className="size-4" />
              </button>
            </form>
            <p className="mt-1.5 text-center text-[10px] text-ink-muted">
              Grounded assistant · not a compliance decision
            </p>
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
