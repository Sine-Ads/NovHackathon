"use client";

import type { Evidence } from "@/lib/types";

/**
 * Provenance chips. The `reason` shown on hover is generated deterministically
 * by the backend from the scoring fields, so it cannot be fabricated.
 */
export function EvidenceList({
  evidence,
  onSelect,
}: {
  evidence: Evidence[];
  onSelect?: (itemId: string) => void;
}) {
  if (!evidence.length) return null;
  return (
    <div className="evidence">
      {evidence.map((e) => (
        <span
          key={e.chunk_id}
          className="ev-chip"
          title={`${e.title ?? "Untitled"}\n${e.source_name} ${e.source_id}\n${e.date_label}: ${
            e.date_published?.slice(0, 10) ?? "unknown"
          }\n\nWhy surfaced: ${e.reason}`}
          onClick={() => onSelect?.(e.item_id)}
          style={{ cursor: onSelect ? "pointer" : "help" }}
        >
          {e.source_name} · {e.source_id.slice(0, 18)}
          {e.is_thin ? " · stub" : ""}
        </span>
      ))}
    </div>
  );
}
