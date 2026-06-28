"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CopilotKit } from "@copilotkit/react-core";
import { CopilotChat } from "@copilotkit/react-ui";
import "@copilotkit/react-ui/styles.css";

const BACKEND = process.env.NEXT_PUBLIC_AGUI_HTTP ?? "http://localhost:8000";

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
  return (
    <CopilotKit
      runtimeUrl="/api/copilotkit"
      agent="seller"
      showDevConsole={false}
      enableInspector={false}
    >
      <main className="shell">
        <div className="head">
          <Link href="/" className="back">← Run history</Link>
          <span className="tag live">live · MiniMax M3 · learned PolicyStore</span>
          <h1>Haggle the self-taught negotiator</h1>
          <p>
            You’re the <strong>buyer</strong>. The seller is Gambit’s trained agent — the same
            policy that improves through the offline gate. It won’t sell below its secret floor.
          </p>
        </div>
        <Catalogue />
        <div className="chat-wrap">
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
