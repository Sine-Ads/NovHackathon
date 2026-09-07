import type { Urgency } from "@/lib/types";
import { cn } from "@/lib/utils";

const STYLES: Record<Urgency, { dot: string; text: string; label: string }> = {
  HIGH: { dot: "bg-high", text: "text-high", label: "High" },
  MEDIUM: { dot: "bg-medium", text: "text-medium", label: "Medium" },
  LOW: { dot: "bg-low", text: "text-low", label: "Low" },
};

export function UrgencyFlag({ urgency, score }: { urgency: Urgency; score?: number }) {
  const style = STYLES[urgency];
  return (
    <span
      className={cn("inline-flex items-center gap-1.5 text-xs font-medium", style.text)}
      title={
        score === undefined
          ? undefined
          : `Score ${score.toFixed(2)} — completeness x recency x change x verdict`
      }
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", style.dot)} />
      {style.label}
    </span>
  );
}

export const URGENCY_BAR: Record<Urgency, string> = {
  HIGH: "bg-high",
  MEDIUM: "bg-medium",
  LOW: "bg-low",
};
