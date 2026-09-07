"use client";

import { useState } from "react";
import { ArrowDown, ArrowUp, ChevronDown, Minus } from "lucide-react";
import type { ScoreFeature } from "@/lib/types";

const ICON = { up: ArrowUp, down: ArrowDown, neutral: Minus };
const COLOR = { up: "text-accent", down: "text-ink-muted", neutral: "text-ink-muted" };

/**
 * The urgency calculation, printed. These are the exact multipliers the backend
 * used — not a summary of them — so a reader can multiply the column and get
 * the score back.
 */
export function ScoreBreakdown({ items, score }: { items: ScoreFeature[]; score: number }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-md border border-border bg-surface">
      <button
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center justify-between px-4 py-3 text-left"
      >
        <span className="text-xs font-medium text-ink-muted">
          Why this urgency
          <span className="ml-2 font-mono text-ink">{score.toFixed(2)}</span>
        </span>
        <ChevronDown
          size={14}
          className={`text-ink-muted transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && (
        <div className="space-y-2 border-t border-border px-4 py-3">
          {items.map((feature) => {
            const Icon = ICON[feature.direction];
            return (
              <div key={feature.feature} className="flex items-center justify-between gap-4 text-xs">
                <span className="text-ink">{feature.feature}</span>
                <span className={`flex items-center gap-1 font-mono ${COLOR[feature.direction]}`}>
                  <Icon size={11} />
                  {feature.weight.toFixed(2)}
                </span>
              </div>
            );
          })}
          <p className="border-t border-border pt-2 text-[11px] leading-relaxed text-ink-muted">
            Multiplied together. Completeness and recency are the same factors
            evidence ranking uses, so a record cannot be urgent here and
            unremarkable in search.
          </p>
        </div>
      )}
    </div>
  );
}
