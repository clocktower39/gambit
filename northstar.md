# Gambit — North Star

**A self-improving auto-negotiator.** It lists an item, negotiates to the best price in a
reasonable time, and **gets better from its own negotiations — with zero human labeling.**
It learns by negotiating against *itself* (self-play): one shared policy plays both the
seller and the buyer, each side fighting for its own surplus, refereed by a verifiable
reward. The counterparty is **pluggable** — self-play is how it trains today, a human can
step in as the buyer at any moment, and real buyers drop in unchanged when a marketplace is
wired. The objective is singular: **a real negotiator that never stops improving.**

> Originated at the AI Engineer World's Fair 2026 (theme: Continual Learning). We are not
> building a demo — we are building the real thing, and continual improvement is the whole
> point. Everything below is in service of *real and improving*, not *impressive on a stage*.

---

## 1. What "done" means

Done is not a date — it's three properties that have to hold and keep holding.

1. **It's real.** Live structured negotiation on **MiniMax M3**: typed moves, private
   information (secret floor / hidden reservation), a binding offer channel separate from the
   chat. No scripted puppet on either side — both seller and buyer are the same reasoning
   policy under different context. The same engine that trains against itself plugs into a
   **human buyer** or a **live marketplace** through one interface, with nothing in the loop
   changed.
2. **It keeps improving.** Across generations, with no human labels, **verifiable surplus
   measurably climbs** — and it climbs on **held-out counterparties it never trained against**,
   not just the ones it practiced on. Improvement that doesn't transfer isn't improvement; the
   held-out signal is the truth.
3. **The gains are trustworthy.** The integrity guard reports `viol=0%` — the agent is winning
   by negotiating better, not by leaking its floor, hallucinating a close, or (under self-play)
   colluding with itself. The reward can't be gamed because the thing that *selects* is
   deterministic, and an independent verifier audits every gain.

When all three hold and the curve is still climbing, we've built the thing. The more it
negotiates, the better it gets — that's the product.

---

## 2. The counterparty is pluggable (the load-bearing idea)

The negotiation loop is a **referee over two policies**. It does not know or care what is on
the other side of the table — it only exchanges typed moves and scores the outcome. That one
decision is what makes this real instead of a simulator:

| Counterparty | What it is | When |
|---|---|---|
| **Self-play** *(default)* | The **same shared policy** wearing the buyer's hat, with a hidden reservation, rewarded for the buyer's own surplus. The agent improves by negotiating against itself. | Now — the training engine. No buyers required, no human labels. |
| **Human** | A person types the buyer's messages. Same interface, same typed moves. | Any time — drop in to feel it out, pressure-test it, or sanity-check a generation. |
| **Live market** | A real buyer via a connector (eBay Best Offer first). The seller's moves become real offers; the reward becomes the real sale. | When a marketplace is wired — the engine is unchanged. |

We self-play **because it's the strongest way to improve and because we don't have live
buyers yet** — not because the buyer is fake. The buyer is the same intelligence as the
seller. Swapping in a human or a real marketplace is a policy swap, not a rewrite.

### Why self-play (the AlphaZero move)

A scripted buyer caps how good the seller can get — you can't out-negotiate your own
heuristics. A **shared policy playing both sides** scales with you: as the seller sharpens,
so does the buyer it faces, so the pressure never relaxes. The agent generates its own
training signal by playing itself — the cleanest possible continual-learning story, and no
human ever labels a transcript.

**The three traps, and the guards we already have:**
1. **Collusion / a private handshake** — same model on both sides could learn a tell that
   hands the seller an easy win. The **Tier-2 verifier** (`floor_leak`, "buyer conceded only
   for legitimate reasons") is the defense, and it matters *more* here, not less.
2. **Self-play overfitting** — only ever facing your current self breeds quirks. Fix: a
   **checkpoint league** — train against gen-0…gen-N, not just the latest self.
3. **Where ground truth comes from** — the seller's reward needs a defined hidden budget, so
   the buyer-hat is *assigned* a reservation drawn from a distribution (the personas) and told
   to pay as little as possible, never above it. We keep the hidden-budget concept and the
   held-out generalization check; we drop only the scripted *behavior*.

---

## 3. How the core loop works

```
 Strategy ─► seller ⇄ buyer ─► Episodes ─► Score ─► Optimizer ─► A/B select ─┐
 (policy)   (one shared policy,  (transcripts)  (verifiable   (reflect →      │
     ▲       walled-off private              surplus +        lessons)        │
     │       info on each side)              Tier-1 audit)                    │
     └────────────────  keep the better strategy, next generation  ◄──────────┘
        held-out early-stop (anti-overfit)   Tier-2 verifier audits integrity (binary checklist)
        checkpoint league (anti-self-play-collapse)
```

- **Reward = deterministic verifiable surplus** from the secret floor: `(price − floor)/(list − floor)`.
  Terminal shaping: below-floor / format → −1; no-deal / walk-away → 0; deal → surplus.
  **No LLM judge in the selector.** Each side optimizes its *own* surplus (seller `price − floor`,
  buyer `budget − price`) — opposing objectives over shared weights make self-play genuinely adversarial.
- **Reward-integrity guard** so the curve is defensible: Tier-1 deterministic audit (done), Tier-2
  binary-question verifier on a *different model* (done), Tier-3 held-out counterparties (done).
- **Anti-bloat:** the optimizer extracts *lessons* (not rewrites), dedups + caps the tactics prompt,
  and the loop early-stops on a held-out plateau.

---

## 4. Tech stack (decided)

| Layer | Choice | Notes |
|---|---|---|
| **LLM** | **MiniMax M3** | OpenAI-compatible endpoint; the provider lives in one place (`llm.py`) and is swappable. |
| **LLM framework** | **Pydantic AI** | Typed, validated structured outputs — replaces hand-rolled JSON parsing; retries on validation failure. |
| **Models / types** | **Pydantic** (`BaseModel`, `pydantic-settings`) | One typed contract end-to-end — no dataclasses. Validators are the integrity rails. |
| **Observability** | **Logfire** | `instrument_pydantic_ai()` — every agent run + the improvement curve in one dashboard; debugs the never-tested LLM paths. |
| **Language** | Python (≥ 3.11) | |
| **Packaging** | **uv** | `pyproject.toml` + `uv.lock`; `uv run` / `uv add` (not pip). |
| **Deployment + data** | **DigitalOcean** | App Platform (deploy) · Managed Postgres + pgvector (memory) · Spaces (images). |

---

## 5. Components & status

✅ done (offline-verified) · 🟡 partial · ⬜ to-do

| Component | Role | Status |
|---|---|---|
| `models.py` / `personas.py` | Item, Strategy, Episode, counterparty reservations (hidden budgets) | ✅ |
| `negotiation.py` | referee one episode over two policies → terminal outcome | ✅ |
| `metrics.py` → `reward.py` | verifiable surplus reward + terminal shaping + Tier-1 audit + panel | ✅ |
| seller policy / buyer policy | the negotiator + the self-play buyer (one shared policy, two contexts) | 🟡 buyer is a passive heuristic today — make it reward-seeking; LLM path **untested** |
| `optimizer.py` | reflection → lessons, anti-bloat dedup/cap, verifier-rubric feedback | 🟡 LLM path **untested** |
| `improve_loop.py` | generational loop + held-out early-stop | ✅ (⬜ checkpoint league) |
| `verifier.py` | Tier-2 binary-question integrity checklist (incl. anti-collusion) | 🟡 LLM path **untested** |
| `opponent.py` | belief calibration — both sides model the other | 🟡 not wired into the live policy |
| `storage.py` | in-memory ↔ DO Postgres + pgvector | ✅ (PG path needs a DB) |
| `inference.py` | OpenAI-compatible client | ⬜ **replace with `llm.py` (Pydantic AI + MiniMax)** |
| `scripts/run_demo.py` | CLI: curve + head-to-head + audit | ✅ |
| Human-buyer entry | drop a person in as the buyer through the same policy interface | ⬜ |
| eBay connector | live buyers via Best Offer (`docs/ebay.md`) | ⬜ |
| DO deploy / web view | App Platform + live curve | ⬜ |

---

## 6. Roadmap (real capability, in order)

Milestones are capabilities, not stage tricks. Each one makes it *more real* or *better at
improving*.

### Now — the engine is real and improving live
- [x] uv project (`pyproject.toml` + `uv.lock`); `pydantic-ai` installed.
- [ ] `gambit/llm.py`: Pydantic AI model on MiniMax + typed outputs
      (`SellerMove`, `BuyerMove`, `OptimizerProposal`, `AuditVerdict`).
- [ ] Refactor seller/buyer/`optimizer.propose_llm`/`verifier._verify_llm` to typed agents;
      keep the deterministic policy as a first-class offline path. Delete `inference.py`'s JSON parsing.
- [ ] Config via `pydantic-settings`: `MINIMAX_API_KEY`/`_BASE_URL`/`_MODEL`, keep `OFFLINE`.
- [ ] Logfire at the entry point — every agent run + the curve traced.
- **Real when:** a live MiniMax run shows surplus climbing across generations with `viol=0%`,
      and the gains hold on held-out counterparties.

### Next — make self-play genuinely adversarial
- [ ] **Reward-seeking buyer:** the buyer-hat optimizes its own surplus (today it's a passive
      reservation-respecting heuristic). This is what turns "two agents" into real self-play.
- [ ] **Checkpoint league:** train against a pool of past selves, not just the latest — anti-collapse.
- [ ] **Anti-collusion audit:** lean on the Tier-2 verifier to catch a shared-policy handshake;
      add held-out *promotion* gate (refuse to promote a candidate that regresses held-out).
- [ ] **Opponent-aware pricing:** wire `opponent.infer` into the seller — hold near the
      estimated reservation instead of folding.

### Then — real counterparties
- [ ] **Human-in-the-buyer-seat:** the same interface, a person on the other side — try it, break it.
- [ ] **eBay Sandbox connector** — real list → Best Offer → counter → accept (`docs/ebay.md`).
- [ ] **Memory:** DO Postgres + pgvector case retrieval (storage layer already built).
- [ ] **Deploy:** DO App Platform + a live view of the climbing curve.

### Later — scale-up (only when the core is unshakable)
- [ ] Weight-level RL (Gemma LoRA on winning transcripts) · voice intake · listing-image gen
      · computer-use auto-post where no API exists.

---

## 7. Current status snapshot (2026-06-27)

- **Built & offline-verified:** the core loop, verifiable surplus reward, Tier-1 + Tier-2
  integrity guard, held-out early-stop, anti-bloat lessons, opponent modeling + belief
  calibration, verifier→optimizer dense feedback. Offline, surplus climbs ~0.13 → 0.25,
  head-to-head +$23, held-out 0.16 → 0.36, `viol=0%`; the guard provably catches below-floor
  and hallucinated-price cheating.
- **Not yet real:** every **LLM-mode path** compiles with deterministic fallbacks but has never
  run against a live model. The buyer is still a passive heuristic, not a reward-seeking
  self-play agent.
- **Reference, not code:** the 7-book negotiation playbook lives in `docs/playbook/` — literature
  we read *around* the system, never seeded into the seller (that would contradict "zero human
  labeling").
- **Repo:** https://github.com/clocktower39/gambit (public).

---

## 8. Risks & guardrails
- **Self-play collapse / collusion** — the central risk of a shared policy on both sides. Guard:
  Tier-2 verifier (anti-handshake), checkpoint league, held-out promotion gate. Never relax these.
- **Reward integrity** — never let an LLM judge into the *selector*; the deterministic surplus
  reward is the source of truth. Evaluators give the optimizer dense feedback but never select.
- **Call volume / cost / latency** — a generation = many negotiations × turns × 2 agents (+ verifier).
  Keep batches small while iterating; scale once it holds.
- **Overfitting to self** — train and judge on held-out counterparties, not just the practiced ones.
