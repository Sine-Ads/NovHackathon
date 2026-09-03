"use client";

import type { LandscapeStats } from "@/lib/types";

export function LandscapeStrip({ stats }: { stats: LandscapeStats | null }) {
  if (!stats) return null;
  const recruiting = stats.trial_status?.RECRUITING ?? 0;
  const completed = stats.trial_status?.COMPLETED ?? 0;
  const terminated = stats.trial_status?.TERMINATED ?? 0;

  const verdicts = stats.classifications;

  return (
    <>
      <div className="strip">
        <div className="stat">
          <div className="n">{stats.total_items.toLocaleString()}</div>
          <div className="k">Records monitored</div>
        </div>
        <div className="stat">
          <div className="n">{recruiting}</div>
          <div className="k">Recruiting</div>
        </div>
        <div className="stat">
          <div className="n">{completed}</div>
          <div className="k">Completed</div>
        </div>
        <div className="stat">
          <div className="n">{terminated}</div>
          <div className="k">Terminated</div>
        </div>
        <div className="stat">
          <div className="n">{Object.keys(stats.by_source).length}</div>
          <div className="k">Live sources</div>
        </div>
        {verdicts?.available && (
          <div
            className="stat"
            title={`${verdicts.unclassified} records not yet classified${
              verdicts.failed ? `, ${verdicts.failed} failed` : ""
            }`}
          >
            <div className="n">{verdicts.classified}</div>
            <div className="k">Classified</div>
          </div>
        )}
      </div>
      <details className="caveats">
        <summary>What this corpus does and does not cover</summary>
        <ul>
          {stats.caveats.map((c, i) => (
            <li key={i}>{c}</li>
          ))}
        </ul>
      </details>
    </>
  );
}
