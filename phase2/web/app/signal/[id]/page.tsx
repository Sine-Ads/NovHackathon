"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Check } from "lucide-react";
import { useReviewToggle, useSignal } from "@/hooks/useSignals";
import { userMessage } from "@/lib/errors";
import { CategoryTag } from "@/components/CategoryTag";
import { DiffPanel } from "@/components/DiffPanel";
import { ExpandedPanel } from "@/components/ExpandedPanel";
import { ScoreBreakdown } from "@/components/ScoreBreakdown";
import { SignalEvidence } from "@/components/SignalEvidence";
import { UrgencyFlag } from "@/components/UrgencyFlag";
import { VerdictBadge } from "@/components/VerdictBadge";
import { cn } from "@/lib/utils";

export default function SignalDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = decodeURIComponent(params.id);
  const { data: signal, isPending, error } = useSignal(id);
  const review = useReviewToggle();

  if (isPending) {
    return <p className="p-6 text-sm text-ink-muted">Loading signal…</p>;
  }

  if (error || !signal) {
    return (
      <div className="p-6">
        <p className="text-sm text-high">{userMessage("feed", error)}</p>
        <Link href="/" className="mt-2 inline-block text-xs text-accent hover:underline">
          Back to the radar feed
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl p-6">
      <Link
        href="/"
        className="mb-4 inline-flex items-center gap-1.5 text-xs text-ink-muted hover:text-accent"
      >
        <ArrowLeft size={13} />
        Radar feed
      </Link>

      <div className="mb-2 flex flex-wrap items-center gap-2">
        <UrgencyFlag urgency={signal.urgency} score={signal.score} />
        <CategoryTag category={signal.category} />
        <span className="text-[11px] text-ink-muted">
          {signal.indication ?? "Indication unstated"}
        </span>
        <VerdictBadge classification={signal.classification} />
        <button
          className={cn(
            "ml-auto flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] transition-colors",
            signal.reviewed
              ? "border-accent-soft bg-accent-soft text-accent"
              : "border-border text-ink-muted hover:border-accent hover:text-accent"
          )}
          disabled={review.isPending}
          onClick={() => review.mutate({ id: signal.id, reviewed: !signal.reviewed })}
        >
          <Check size={11} />
          {signal.reviewed ? "Reviewed" : "Mark reviewed"}
        </button>
      </div>

      <h2 className="text-lg font-semibold leading-snug text-ink">
        {signal.title ?? "Untitled record"}
      </h2>
      <p className="mt-1 text-xs text-ink-muted">
        {signal.source_name} · {signal.source_id} · {signal.date_label}:{" "}
        {signal.date_published?.slice(0, 10) ?? "unknown"} · {signal.detected_label}{" "}
        {signal.detected_date.slice(0, 10)}
      </p>

      <div className="mt-5 space-y-4">
        <ScoreBreakdown items={signal.score_breakdown} score={signal.score} />
        <DiffPanel changes={signal.changes} />
        <SignalEvidence evidence={signal.evidence} />

        <div className="overflow-hidden rounded-md border border-border bg-surface">
          <ExpandedPanel
            item={signal}
            onOpenItem={(itemId) => router.push(`/signal/${encodeURIComponent(itemId)}`)}
          />
        </div>
      </div>
    </div>
  );
}
