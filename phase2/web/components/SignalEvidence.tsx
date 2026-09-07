"use client";

import { useState } from "react";
import { Quote } from "lucide-react";
import type { Evidence } from "@/lib/types";

/**
 * The excerpts behind a signal, each with the deterministic reason it is here.
 * The first entry is the record itself; the rest are its nearest neighbours.
 */
export function SignalEvidence({ evidence }: { evidence: Evidence[] }) {
  const [openIndex, setOpenIndex] = useState<number | null>(0);

  if (evidence.length === 0) return null;

  return (
    <div className="rounded-md border border-border bg-surface">
      <div className="border-b border-border px-4 py-3">
        <span className="text-xs font-medium text-ink-muted">
          Evidence
          <span className="ml-2 font-mono text-[11px]">{evidence.length}</span>
        </span>
      </div>
      <div className="divide-y divide-border">
        {evidence.map((item, index) => (
          <div key={item.chunk_id}>
            <button
              onClick={() => setOpenIndex(openIndex === index ? null : index)}
              className="flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left"
            >
              <span className="flex min-w-0 items-center gap-2 text-xs text-ink">
                <Quote size={12} className="shrink-0 text-ink-muted" />
                <span className="truncate">{item.title ?? item.source_name}</span>
              </span>
              <span className="shrink-0 text-[11px] text-ink-muted">
                {item.matched_by.includes("record") ? "this record" : item.source_name}
              </span>
            </button>
            {openIndex === index && (
              <div className="px-4 pb-3">
                {item.text ? (
                  <blockquote className="border-l-2 border-accent-soft pl-3 text-xs italic leading-relaxed text-ink-muted">
                    {item.text.slice(0, 600)}
                    {item.text.length > 600 ? "…" : ""}
                  </blockquote>
                ) : (
                  <p className="text-xs text-ink-muted">No stored excerpt for this record.</p>
                )}
                <p className="mt-2 text-[11px] text-ink-muted">
                  {item.date_label}: {item.date_published?.slice(0, 10) ?? "unknown"} · why it is
                  here: {item.reason}
                </p>
                {item.source_url && (
                  <a
                    href={item.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-1.5 inline-block text-[11px] text-accent hover:underline"
                  >
                    View source
                  </a>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
