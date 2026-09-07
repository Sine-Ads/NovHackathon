"use client";

import { useRouter } from "next/navigation";
import { ChatPanel } from "@/components/ChatPanel";

export default function AssistantPage() {
  const router = useRouter();

  return (
    <div className="mx-auto max-w-3xl p-6">
      <h2 className="text-sm font-semibold text-ink">Radar assistant</h2>
      <p className="mb-4 mt-1 text-xs text-ink-muted">
        Scoped to every monitored record. Answers cite the excerpts they stand on
        and say so when the corpus will not support one.
      </p>
      <ChatPanel
        endpoint="/api/chat/global"
        body={{ thread_id: "global" }}
        placeholder="Ask across every monitored record…"
        suggestions={[
          "How many trials are currently recruiting?",
          "Which sponsors are most active?",
          "What gene therapy work should we be watching?",
        ]}
        onCitationClick={(id) => router.push(`/signal/${encodeURIComponent(id)}`)}
      />
    </div>
  );
}
