import type { Confidence } from "@/lib/types";

const LABELS: Record<string, { text: string; hint: string }> = {
  supported: {
    text: "Supported",
    hint: "Every claim traces to a retrieved excerpt or an exact database count.",
  },
  inferred: {
    text: "Inferred",
    hint: "Combined from more than one record; no single excerpt states this outright.",
  },
  insufficient: {
    text: "Insufficient evidence",
    hint: "The corpus does not support an answer. Nothing was generated.",
  },
};

export function ConfidenceBadge({ level }: { level: Confidence | string }) {
  const meta = LABELS[level];
  if (!meta) return null;
  return (
    <span className={`conf ${level}`} title={meta.hint}>
      {meta.text}
    </span>
  );
}
