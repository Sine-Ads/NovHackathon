"use client";

import type { FeedItem } from "@/lib/types";
import { ExpandedPanel } from "./ExpandedPanel";
import { VerdictBadge } from "./VerdictBadge";

/** A trial start date in the future is a plan, not news. Label it as such. */
function isPlanned(item: FeedItem): boolean {
  if (item.date_class !== "trial_start" || !item.date_published) return false;
  return item.date_published.slice(0, 10) > new Date().toISOString().slice(0, 10);
}

export function FeedCard({
  item,
  open,
  onToggle,
  onOpenItem,
}: {
  item: FeedItem;
  open: boolean;
  onToggle: () => void;
  onOpenItem?: (itemId: string) => void;
}) {
  const subtitle = item.sponsor ?? item.journal ?? null;

  return (
    <article className={`card ${open ? "open" : ""}`} id={`item-${item.item_id}`}>
      <div className="card-head" onClick={onToggle}>
        <div className="card-meta">
          <span className="badge src">{item.source_name}</span>
          {item.openfda_type && (
            <span className="badge">
              {item.openfda_type === "drug_recall" ? "Drug recall" : "Adverse event"}
            </span>
          )}
          {item.status && <span className="badge">{item.status}</span>}
          <VerdictBadge classification={item.classification} />
          {isPlanned(item) && <span className="badge planned">Planned start</span>}
          {item.is_thin && (
            <span className="badge stub" title="Stored without body text — summaries abstain">
              Stub
            </span>
          )}
          <span>
            {item.date_published
              ? `${item.date_label}: ${item.date_published.slice(0, 10)}`
              : "Date unknown"}
          </span>
          {subtitle && <span>· {subtitle}</span>}
        </div>
        <h3 className="card-title">{item.title ?? "Untitled record"}</h3>
        {!open && item.snippet && <p className="card-snip">{item.snippet}…</p>}
        {item.match_reason && <div className="why">{item.match_reason}</div>}
      </div>
      {open && <ExpandedPanel item={item} onOpenItem={onOpenItem} />}
    </article>
  );
}
