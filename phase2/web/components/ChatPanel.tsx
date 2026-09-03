"use client";

import { useEffect, useRef, useState } from "react";
import { streamChat } from "@/lib/api";
import type { ChatMessage, Evidence } from "@/lib/types";
import { ConfidenceBadge } from "./ConfidenceBadge";
import { EvidenceList } from "./EvidenceList";

/**
 * One chat surface, used for both assistants. The only differences are the
 * endpoint it posts to and its suggested openers — the scope boundary itself is
 * enforced on the backend, not here.
 */
export function ChatPanel({
  endpoint,
  body,
  placeholder,
  suggestions = [],
  onCitationClick,
}: {
  endpoint: string;
  body?: Record<string, unknown>;
  placeholder: string;
  suggestions?: string[];
  onCitationClick?: (itemId: string) => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [messages]);

  async function send(text: string) {
    const question = text.trim();
    if (!question || busy) return;
    setInput("");
    setBusy(true);
    setMessages((prev) => [
      ...prev,
      { role: "user", content: question },
      { role: "assistant", content: "", pending: true },
    ]);

    const patch = (fn: (m: ChatMessage) => ChatMessage) =>
      setMessages((prev) => {
        const next = [...prev];
        const last = next.length - 1;
        if (last >= 0) next[last] = fn(next[last]);
        return next;
      });

    await streamChat(
      endpoint,
      { ...(body ?? {}), message: question },
      {
        onEvidence: (evidence: Evidence[], route, facts) =>
          patch((m) => ({ ...m, evidence, route, facts })),
        onFacts: (facts) => patch((m) => ({ ...m, facts })),
        onDelta: (chunk) =>
          patch((m) => ({ ...m, content: m.content + chunk, pending: false })),
        onDone: (confidence) =>
          patch((m) => ({
            ...m,
            confidence: confidence as ChatMessage["confidence"],
            pending: false,
          })),
        onError: (message) =>
          patch((m) => ({
            ...m,
            content: m.content || message,
            confidence: "insufficient",
            pending: false,
          })),
      }
    );
    setBusy(false);
  }

  return (
    <div className="chat">
      <div className="chat-log" ref={logRef}>
        {messages.length === 0 && (
          <p className="muted" style={{ margin: 0, fontSize: 12.5 }}>
            Answers are grounded in the monitored corpus. Every reply shows what
            it was based on, and says so when the evidence will not support one.
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            {m.role === "assistant" ? (
              <>
                {m.pending && !m.content && (
                  <span className="spinner">Searching the corpus…</span>
                )}
                {m.facts && <div className="facts-block">{m.facts}</div>}
                <div className="msg-body">{m.content}</div>
                {m.confidence && (
                  <div style={{ marginTop: 6 }}>
                    <ConfidenceBadge level={m.confidence} />
                  </div>
                )}
                {m.evidence && m.evidence.length > 0 && (
                  <EvidenceList
                    evidence={m.evidence}
                    onSelect={onCitationClick}
                  />
                )}
              </>
            ) : (
              <div className="msg-body">{m.content}</div>
            )}
          </div>
        ))}
      </div>

      {messages.length === 0 && suggestions.length > 0 && (
        <div className="suggestions">
          {suggestions.map((s) => (
            <button key={s} onClick={() => send(s)} disabled={busy}>
              {s}
            </button>
          ))}
        </div>
      )}

      <form
        className="chat-input"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <input
          value={input}
          placeholder={placeholder}
          onChange={(e) => setInput(e.target.value)}
          disabled={busy}
        />
        <button type="submit" disabled={busy || !input.trim()}>
          {busy ? "…" : "Ask"}
        </button>
      </form>
    </div>
  );
}
