import type { SignalCategory } from "@/lib/types";

/** What kind of event this is, decided by the source that supplied the record. */
const ORIGIN: Record<SignalCategory, string> = {
  Trial: "From ClinicalTrials.gov",
  Publication: "From PubMed or arXiv",
  Corporate: "From SEC EDGAR filings",
  Other: "Source not mapped to a category",
};

export function CategoryTag({ category }: { category: SignalCategory }) {
  return (
    <span
      title={ORIGIN[category]}
      className="inline-flex items-center rounded-sm border border-border px-1.5 py-0.5 text-[11px] text-ink-muted"
    >
      {category}
    </span>
  );
}
