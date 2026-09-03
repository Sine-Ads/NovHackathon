"use client";

import { useState } from "react";
import { ChatPanel } from "./ChatPanel";

export function GlobalChatDock({ onOpenItem }: { onOpenItem?: (id: string) => void }) {
  const [open, setOpen] = useState(false);

  if (!open) {
    return (
      <button className="dock-btn" onClick={() => setOpen(true)}>
        Ask the radar
      </button>
    );
  }

  return (
    <aside className="dock">
      <div className="dock-head">
        <h3>Radar assistant</h3>
        <button onClick={() => setOpen(false)} aria-label="Close">
          ×
        </button>
      </div>
      <ChatPanel
        endpoint="/api/chat/global"
        body={{ thread_id: "global" }}
        placeholder="Ask across every monitored record…"
        suggestions={[
          "How many trials are currently recruiting?",
          "Which sponsors are most active?",
          "What gene therapy work should we be watching?",
        ]}
        onCitationClick={onOpenItem}
      />
    </aside>
  );
}
