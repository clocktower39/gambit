"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { CopilotKit } from "@copilotkit/react-core";
import { CopilotChat } from "@copilotkit/react-ui";
import "@copilotkit/react-ui/styles.css";
import VoiceConsole from "./VoiceConsole";
import ThemeToggle from "../ThemeToggle";

const BACKEND = process.env.NEXT_PUBLIC_AGUI_HTTP ?? "http://localhost:8000";

// The seller can walk away from a bad-faith chat (abuse/spam/manipulation). When it does, the backend
// records the close and this poll flips `closed`, so we hard-lock the composer — the buyer can't keep
// haggling a seller who already ended it. We control the threadId so we know which run to poll.
function useChatClosed(threadId: string) {
  const [closed, setClosed] = useState(false);
  const stop = useRef(false);
  useEffect(() => {
    stop.current = false;
    const tick = async () => {
      if (stop.current) return;
      try {
        const r = await fetch(`/api/chat-status?run_id=${encodeURIComponent(threadId)}`, { cache: "no-store" });
        const j = await r.json();
        if (j?.closed) { setClosed(true); stop.current = true; return; }
      } catch { /* transient — keep polling */ }
      if (!stop.current) timer = setTimeout(tick, 3000);
    };
    let timer = setTimeout(tick, 3000);
    return () => { stop.current = true; clearTimeout(timer); };
  }, [threadId]);
  return closed;
}

// Public catalogue fields only — the secret floor/target never leave the server (see gambit/agui.py).
type CatalogueItem = { id: number; name: string; condition: string; description: string; list_price: number };

const money = (v: number) => `$${Number.isInteger(v) ? v : v.toFixed(2)}`;

// What the seller has listed — so the buyer immediately sees what's haggleable and the asking prices.
function Catalogue() {
  const [items, setItems] = useState<CatalogueItem[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    fetch(`${BACKEND}/items`)
      .then((r) => r.json())
      .then((j) => { if (live) setItems(j.items ?? []); })
      .catch(() => { if (live) setFailed(true); });
    return () => { live = false; };
  }, []);

  if (failed) return null;                       // backend not up yet — stay quiet, the chat still works
  return (
    <section className="catalogue" aria-label="Items the seller has listed">
      <div className="catHead">
        <span className="catLabel">Listed for sale</span>
        <span className="catHint">the asking price is the seller's anchor — your job is to talk it down</span>
      </div>
      <div className="catList">
        {items == null
          ? [0, 1, 2].map((i) => <div key={i} className="catCard skel" aria-hidden />)
          : items.map((it) => (
              <div key={it.id} className="catCard">
                <div className="catCardTop">
                  <span className="catName">{it.name}</span>
                  <span className="catCond">{it.condition}</span>
                </div>
                <p className="catDesc">{it.description}</p>
                <div className="catPrice">
                  <span className="catPriceLabel">listed</span>
                  <span className="catPriceVal">{money(it.list_price)}</span>
                </div>
              </div>
            ))}
      </div>
    </section>
  );
}

export default function ChatPage() {
  // A stable per-session id we control, so the backend groups the run under it and we can poll its
  // closed-state. (CopilotKit would otherwise generate one we can't see.)
  const [threadId] = useState(() =>
    (typeof crypto !== "undefined" && crypto.randomUUID) ? crypto.randomUUID() : `chat-${Math.random().toString(36).slice(2)}`);
  const closed = useChatClosed(threadId);
  return (
    <CopilotKit
      runtimeUrl="/api/copilotkit"
      agent="seller"
      threadId={threadId}
      showDevConsole={false}
      enableInspector={false}
    >
      <main className="shell">
        <div className="head">
          <ThemeToggle />
          <Link href="/" className="back">← Run history</Link>
          <span className="tag live">live · MiniMax M3 · learned PolicyStore</span>
          <h1>Haggle the self-taught negotiator</h1>
          <p>
            You’re the <strong>buyer</strong>. The seller is Gambit’s trained agent — the same
            policy that improves through the offline gate. It won’t sell below its secret floor.
          </p>
        </div>
        <Catalogue />
        <VoiceConsole />
        <div className={`chat-wrap${closed ? " ended" : ""}`}>
          {closed && (
            <div className="chatEndedBanner" role="status">
              🔒 The seller ended this conversation. They’ve walked away — refresh to start a new one.
            </div>
          )}
          <CopilotChat
            labels={{
              title: "Gambit seller",
              initial:
                "Hey — thanks for looking. I’ve got a few things listed. What are you interested in, and what’s your offer?",
              placeholder: "e.g. “is the iPhone still available? I can do $420 cash”",
            }}
          />
        </div>
      </main>
    </CopilotKit>
  );
}
