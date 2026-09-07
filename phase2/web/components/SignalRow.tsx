"use client";

import Link from "next/link";
import { Check } from "lucide-react";
import type { Signal } from "@/lib/types";
import { useReviewToggle } from "@/hooks/useSignals";
import { cn } from "@/lib/utils";
import { CategoryTag } from "./CategoryTag";
import { URGENCY_BAR, UrgencyFlag } from "./UrgencyFlag";
import { VerdictBadge } from "./VerdictBadge";

export function SignalRow({ signal }: { signal: Signal }) {
  const review = useReviewToggle();
  const change = signal.what_changed;

  return (
    <div className="group relative flex gap-4 border-b border-border py-4 pl-4 pr-4 transition-colors hover:bg-surface">
      <span className={cn("w-1 shrink-0 rounded-full", URGENCY_BAR[signal.urgency])} aria-hidden />

      <div className="min-w-0 flex-1">
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <UrgencyFlag urgency={signal.urgency} score={signal.score} />
          <CategoryTag category={signal.category} />
          <span className="text-[11px] text-ink-muted">
            {signal.indication ?? "Indication unstated"}
          </span>
          <VerdictBadge classification={signal.classification} />
          {signal.is_thin && (
            <span
              className="rounded-sm border border-dashed border-border px-1 text-[11px] text-ink-muted"
              title="Stored without body text — summaries abstain on these"
            >
              STUB
            </span>
          )}
        </div>

        <h3 className="text-sm font-medium text-ink group-hover:text-accent">
          <Link href={`/signal/${encodeURIComponent(signal.id)}`} className="text-inherit no-underline">
            <span className="absolute inset-0" aria-hidden />
            {signal.title ?? "Untitled record"}
          </Link>
        </h3>

        {change ? (
          <p className="mt-0.5 text-xs text-ink-muted">
            {change.field_label}: {change.before ?? "not recorded"} → {change.after ?? "removed"}
          </p>
        ) : (
          <p className="mt-0.5 truncate text-xs text-ink-muted">
            {signal.source_name}
            {signal.sponsor ? ` · ${signal.sponsor}` : signal.journal ? ` · ${signal.journal}` : ""}
          </p>
        )}

        {signal.match_reason && (
          <p className="mt-1 text-[11px] italic text-accent">{signal.match_reason}</p>
        )}
      </div>

      <div className="flex shrink-0 flex-col items-end gap-1.5">
        <time
          className="font-mono text-[11px] text-ink-muted"
          title={`${signal.detected_label} · ${signal.date_label}: ${
            signal.date_published?.slice(0, 10) ?? "unknown"
          }`}
        >
          {signal.detected_date.slice(0, 10)}
        </time>
        <button
          // Sits above the row-covering link, so the row still navigates while
          // this stays clickable.
          className={cn(
            "relative z-10 flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] transition-colors",
            signal.reviewed
              ? "border-accent-soft bg-accent-soft text-accent"
              : "border-border text-ink-muted opacity-0 hover:border-accent hover:text-accent group-hover:opacity-100"
          )}
          disabled={review.isPending}
          onClick={() => review.mutate({ id: signal.id, reviewed: !signal.reviewed })}
        >
          <Check size={11} />
          {signal.reviewed ? "Reviewed" : "Mark reviewed"}
        </button>
      </div>
    </div>
  );
}
