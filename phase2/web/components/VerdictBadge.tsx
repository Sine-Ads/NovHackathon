"use client";

import type { Classification } from "@/lib/types";

/**
 * The classifier's verdict on a record.
 *
 * A failed attempt renders as "unclassified", never as a fifth category —
 * FRONTEND_INTEGRATION.md asks for failures to stay visible to operators
 * without being presented as a classification result.
 */
const MEANING: Record<string, string> = {
  proven_right:
    "Independently confirmed — meta-analysis, replication, or a strong RCT.",
  proven_false:
    "Contradicted, retracted, or the trial failed or was terminated.",
  proven_false_but_useful:
    "Retracted or failed, but the data has been cited or reused elsewhere.",
  still_working_on:
    "Preprint, early-phase, or recruiting — no established result yet.",
};

export function VerdictBadge({
  classification,
}: {
  classification?: Classification | null;
}) {
  if (!classification) return null;

  if (classification.status === "failed") {
    return (
      <span
        className="badge verdict failed"
        title={`The classifier could not process this record${
          classification.reason ? `: ${classification.reason}` : "."
        } It is unclassified, not disproven.`}
      >
        Unclassified
      </span>
    );
  }

  const { category, category_label, method, justification } = classification;
  if (!category) return null;

  const tip = [
    MEANING[category],
    method ? `Assigned by ${method === "llm" ? "the model" : "a rule"}.` : "",
    justification ? `\n\n"${justification}"` : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <span className={`badge verdict ${category}`} title={tip}>
      {category_label ?? category}
    </span>
  );
}
