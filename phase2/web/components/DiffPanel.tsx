import type { SignalChange } from "@/lib/types";

/**
 * What moved, and when it was noticed.
 *
 * Phase 1 keeps no revision history, so a change here means Phase 2 observed
 * two different values across two index builds. The panel says that plainly
 * rather than implying the source published a diff.
 */
export function DiffPanel({ changes }: { changes: SignalChange[] }) {
  const moves = changes.filter((change) => !change.is_first_seen);
  const firstSeen = changes.find((change) => change.is_first_seen);

  return (
    <div className="rounded-md border border-border bg-surface p-4">
      <h3 className="mb-3 text-xs font-medium text-ink-muted">Observation history</h3>

      {moves.length === 0 && (
        <p className="text-xs text-ink-muted">
          Nothing has moved since this record entered the corpus. A change can
          only appear after a later ingestion run sees a different value.
        </p>
      )}

      <div className="space-y-3">
        {moves.map((change) => (
          <div key={`${change.field}-${change.detected_at}`}>
            <p className="mb-1.5 text-xs text-ink-muted">
              {change.field_label}
              <span className="ml-2 font-mono text-[11px]">
                {change.detected_at.slice(0, 10)}
              </span>
            </p>
            <div className="flex flex-wrap items-center gap-3">
              <span className="rounded-md bg-low-soft px-3 py-1.5 font-mono text-xs text-ink">
                {change.before ?? "not recorded"}
              </span>
              <span className="text-ink-muted">to</span>
              <span className="rounded-md bg-accent-soft px-3 py-1.5 font-mono text-xs text-accent">
                {change.after ?? "removed"}
              </span>
            </div>
          </div>
        ))}
      </div>

      {firstSeen && (
        <p className="mt-3 border-t border-border pt-3 text-[11px] text-ink-muted">
          First seen in the corpus on {firstSeen.detected_at.slice(0, 10)}.
        </p>
      )}
    </div>
  );
}
