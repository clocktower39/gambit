"use client";

import Link from "next/link";
import { CopilotKit } from "@copilotkit/react-core";
import { CopilotChat } from "@copilotkit/react-ui";
import "@copilotkit/react-ui/styles.css";

export default function ChatPage() {
  return (
    <CopilotKit runtimeUrl="/api/copilotkit" agent="seller">
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
