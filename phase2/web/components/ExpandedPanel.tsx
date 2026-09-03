"use client";

import { useEffect, useState } from "react";
import { fetchSimilar, fetchSummary } from "@/lib/api";
import type { Evidence, FeedItem, Summary } from "@/lib/types";
import { ChatPanel } from "./ChatPanel";
import { VerdictBadge } from "./VerdictBadge";

export function ExpandedPanel({
  item,
  onOpenItem,
}: {
  item: FeedItem;
  onOpenItem?: (itemId: string) => void;
}) {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [similar, setSimilar] = useState<Evidence[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [showChat, setShowChat] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setSummary(null);
    setError(null);

    // Summaries are generated on first expansion and cached thereafter, so a
    // second open of the same card is instant.
    fetchSummary(item.item_id)
      .then((s) => !cancelled && setSummary(s))
      .catch((e) => !cancelled && setError(String(e)));
    fetchSimilar(item.item_id, 5)
      .then((r) => !cancelled && setSimilar(r.similar))
      .catch(() => undefined);

    return () => {
      cancelled = true;
    };
  }, [item.item_id]);

  const abstained = summary?.confidence === "abstain";

  const verdict = item.classification;

  return (
    <div className="expanded">
      {verdict && (
        <div className="section">
          <h4>Classifier verdict</h4>
          <VerdictBadge classification={verdict} />
          {verdict.status === "failed" ? (
            <div className="verdict-note">
              The classifier could not process this record
              {verdict.reason ? `: ${verdict.reason}` : "."} It is unclassified
              — that is not a negative verdict.
            </div>
          ) : (
            <div className="verdict-note">
              {verdict.justification ? (
                <span className="q">&ldquo;{verdict.justification}&rdquo;</span>
              ) : (
                "Assigned deterministically from publication type, retraction status and citation count."
              )}
              {verdict.method && (
                <> &middot; assigned by {verdict.method === "llm" ? "the model" : "a rule"}</>
              )}
            </div>
          )}
        </div>
      )}

      <div className="section">
        <h4>
          Summary
          {summary?.cached ? " · cached" : ""}
          {abstained ? " · insufficient content" : ""}
        </h4>
        {!summary && !error && <p className="spinner">Generating summary…</p>}
        {error && <p className="error">{error}</p>}
        {summary?.error && (
          <p className="error">
            Summary model unavailable: {summary.error}. The structured facts
            below come straight from the source.
          </p>
        )}
        {summary?.summary && <p style={{ margin: 0 }}>{summary.summary}</p>}
        {summary?.why_matters && (
          <p style={{ marginTop: 8 }}>
            <strong>Why it matters. </strong>
            {summary.why_matters}
          </p>
        )}
      </div>

      {summary && summary.key_facts.length > 0 && (
        <div className="section">
          <h4>Key facts</h4>
          <ul className="facts">
            {summary.key_facts.map((f, i) => (
              <li key={i}>{f}</li>
            ))}
          </ul>
        </div>
      )}

      {summary && summary.functions.length > 0 && (
        <div className="section">
          <h4>Who should review this</h4>
          {summary.functions.map((f) => (
            <span className="fn" key={f}>
              {f}
            </span>
          ))}
        </div>
      )}

      {similar.length > 0 && (
        <div className="section">
          <h4>Related coverage</h4>
          <div className="related">
            {similar.map((s) => (
              <button key={s.item_id} onClick={() => onOpenItem?.(s.item_id)}>
                <div>
                  <span className="badge src">{s.source_name}</span>{" "}
                  <VerdictBadge classification={s.classification} />{" "}
                  {s.title ?? "Untitled"}
                </div>
                <div className="r-why">{s.reason}</div>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="section">
        <h4>Provenance</h4>
        <ul className="facts">
          <li>
            {item.source_name} · {item.source_id}
          </li>
          <li>
            {item.date_label}:{" "}
            {item.date_published ? item.date_published.slice(0, 10) : "unknown"}
          </li>
          {item.source_url && (
            <li>
              <a href={item.source_url} target="_blank" rel="noreferrer">
                Read the original at the source →
              </a>
            </li>
          )}
        </ul>
      </div>

      <div className="section" style={{ marginBottom: 0 }}>
        <h4>Ask about this record</h4>
        {!showChat ? (
          <button className="btn" onClick={() => setShowChat(true)}>
            Start a conversation
          </button>
        ) : (
          <ChatPanel
            endpoint={`/api/chat/item/${encodeURIComponent(item.item_id)}`}
            placeholder="Ask about this record and its neighbours…"
            suggestions={[
              "What does this record actually show?",
              "How does this compare with the related records?",
              "What would my team need to decide here?",
            ]}
            onCitationClick={onOpenItem}
          />
        )}
      </div>
    </div>
  );
}
