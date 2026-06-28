# Gambit — North Star

**A self-improving auto-negotiator.** It lists an item, haggles with buyers to get the
best price in a reasonable time, and **gets better from its own past negotiations — with
zero human labeling.**

> AI Engineer World's Fair Hackathon 2026 · Theme: **Continual Learning** · ~18 hours · play-it-safe (a reliable live demo over max ambition).

---

## 1. What success looks like

Three concrete levels — we are done when all three are true.

1. **Functional** — the negotiator runs live on **MiniMax M3** and, across a few generations
   with *no human labeling*, its **verifiable surplus measurably climbs**, while the integrity
   guard reports `viol=0%` so the gains are trustworthy (not reward-hacked).
2. **Demo / the money shot** — in 3 minutes a judge watches **gen-0 vs gen-N on the same
   buyer**: the naive agent closes low, the self-taught agent extracts more. Plus the climbing
   curve. It is *obviously self-improving* and *obviously real* (live LLM, verifiable reward).
3. **Hackathon** — nails **Continual Learning**; scores on **technicality (40%)** (verifiable-reward
   loop + reward-integrity guard), **creativity (25%)** (a negotiator that trains itself),
   **live demo (20%)** (it works), **future potential (15%)** (self-improvement in production).
   Deployed on **DigitalOcean**.

**3-minute demo script (the target):**
1. "This agent has never been told how to negotiate." Show gen-0 close a buyer low.
2. "It negotiated against simulated buyers and graded itself — no human labels." Show the curve climb.
3. "Same buyer, same hidden budget — here's the agent after self-training." Show gen-N extract more.
4. "How do we know it didn't just game its own score?" Show the integrity audit (`viol=0%`, binary checklist).
5. "And it generalizes to buyers it never trained on." Show the held-out number.

---

## 2. The simplest version (the MVP spine)

> A seller agent negotiates against simulated buyers (both **MiniMax M3 via Pydantic AI**), the
> loop scores each negotiation with the **deterministic surplus reward**, reflects to improve its
> strategy, and repeats — output is the **climbing curve + the gen-0-vs-gen-N head-to-head**, run
> live from the CLI.

**In the MVP:** the self-improvement loop, on real MiniMax calls, shown via CLI.
**NOT in the MVP:** eBay, voice, image-gen, fine-tuning, opponent modeling, web UI, deployment.

We already have ~90% of the engine built and offline-tested — **the MVP is mostly an
integration + validation task** (swap inference to MiniMax, confirm it climbs on real calls).

---

## 3. Tech stack (decided)

| Layer | Choice | Notes |
|---|---|---|
| **LLM** | **MiniMax M3** | We have an API key; MiniMax is a hackathon sponsor. |
| **LLM framework** | **Pydantic AI** | Typed, validated structured outputs — replaces hand-rolled JSON parsing. |
| **Language** | Python | |
| **Deployment + data** | **DigitalOcean** | App Platform (deploy) · Managed Postgres + pgvector (memory) · Spaces (images). |
| **Demo surface** | **CLI first (Tier 0)** → web (Tier 1) | Fastest path to "it works live." |

**Trade-off (named, accepted):** inference moved from DO Serverless Inference → MiniMax. The
**Best-DO** case now rests on *deployment + data layer* (still strong — the whole app runs on DO).
The **Gemini $5k** hooks are dropped unless re-added in Tier 3.

---

## 4. How the core loop works

```
 Strategy ─► SellerAgent ⇄ BuyerSimulator ─► Episodes ─► Score ─► Optimizer ─► A/B select ─┐
 (policy)    (MiniMax)     (MiniMax,            (transcripts)  (verifiable    (reflect →     │
     ▲                      hidden budgets)                     surplus +      lessons)       │
     │                                                          Tier-1 audit)                 │
     └──────────────────────  keep the better strategy, next generation  ◄───────────────────┘
        held-out early-stop (anti-collapse)        Tier-2 verifier audits integrity (binary checklist)
```

- **Reward = deterministic verifiable surplus** from the secret floor: `(price − floor)/(list − floor)`.
  Terminal shaping: below-floor / format → −1; no-deal / walk-away → 0; deal → surplus. **No LLM judge in the selector.**
- **Reward-integrity guard** so the curve is defensible: Tier-1 deterministic audit (done), Tier-2
  binary-question verifier on a *different model* (done), Tier-3 held-out buyers (done).
- **Anti-bloat:** the optimizer extracts *lessons* (not rewrites), dedups + caps the tactics prompt,
  and the loop early-stops on a held-out plateau.

---

## 5. Components & status

✅ done (offline-tested) · 🟡 partial · ⬜ to-do

| Component | Role | Status |
|---|---|---|
| `models.py` / `personas.py` | Item, Strategy, Episode, buyer personas (hidden budgets) | ✅ |
| `negotiation.py` | run one episode (terminal outcome) | ✅ |
| `metrics.py` | verifiable surplus reward + terminal shaping + Tier-1 audit + panel | ✅ |
| `seller_agent.py` / `buyer_sim.py` | the negotiator + adversarial buyer (LLM + offline heuristics) | 🟡 LLM path **untested** |
| `optimizer.py` | reflection → lessons, anti-bloat dedup/cap, verifier-rubric feedback | 🟡 LLM path **untested** |
| `improve_loop.py` | generational loop + held-out early-stop | ✅ |
| `verifier.py` | Tier-2 binary-question integrity checklist | 🟡 LLM path **untested** |
| `storage.py` | in-memory ↔ DO Postgres + pgvector | ✅ (PG path needs a DB) |
| `inference.py` | DO OpenAI-compatible client | ⬜ **replace with `llm.py` (Pydantic AI + MiniMax)** |
| `scripts/run_demo.py` | CLI: curve + head-to-head + audit | ✅ |
| `opponent.py` *(parallel)* | opponent modeling / belief calibration | 🟡 not integrated |
| Web UI | live curve + head-to-head for stage | ⬜ Tier 1 |
| DO deploy | App Platform | ⬜ Tier 1 |
| eBay / LiveKit / image-gen / Gemma | real marketplace / voice / images / fine-tune | ⬜ Tier 2–3 |

---

## 6. Roadmap (MVP → complexity)

### 🟢 Tier 0 — MVP (the only thing that MUST work)
**Goal:** the self-improvement loop climbs **live on MiniMax M3**, shown via CLI.
- [ ] Confirm `pydantic-ai` installed; pin in `requirements.txt`.
- [ ] New `gambit/llm.py`: Pydantic AI model pointed at MiniMax (OpenAI-compatible, key from env) + typed
      output models (`SellerMove`, `BuyerMove`, `OptimizerProposal`, `AuditVerdict`).
- [ ] Refactor `seller_agent`, `buyer_sim`, `optimizer.propose_llm`, `verifier._verify_llm` to the
      Pydantic AI agents; keep offline heuristics as the fallback. Delete `inference.py`'s JSON parsing.
- [ ] Config: `MINIMAX_API_KEY`, `MINIMAX_BASE_URL`, `MINIMAX_MODEL`; keep `OFFLINE`.
- [ ] Run `run_demo.py` (LLM mode) on a small batch (1 item × 3–4 personas × ~4 gens); tune for cost/latency.
- **Done when:** live MiniMax run shows surplus climbing across generations with `viol=0%`, and we
  capture real (non-heuristic) head-to-head numbers.

### 🟡 Tier 1 — Make the demo land + go live on DO
**Goal:** a stage-ready demo, deployed.
- [ ] Tier-2 verifier running live on MiniMax (already built; just LLM mode).
- [ ] Minimal **web view**: climbing curve + gen-0-vs-gen-N + the integrity audit.
- [ ] Deploy on **DO App Platform** (port 8080, gunicorn `--timeout 120`); local fallback for the live demo.

### 🟠 Tier 2 — Depth / "it's real" (prize-stacking)
- [ ] **DO Postgres + pgvector** memory retrieval (storage layer already built).
- [ ] **eBay Sandbox** connector — real-marketplace proof (runbook in `docs/ebay.md`).
- [ ] **Opponent modeling** (`opponent.py`) wired in as a sophistication / eval dimension.

### 🔴 Tier 3 — Stretch (only if ahead; re-opens prize hooks)
- [ ] LiveKit voice intake · Gemini computer-use auto-post · Gemma 4 LoRA fine-tune.

---

## 7. Current status snapshot (2026-06-27)

- **Committed & offline-verified:** Phase 1 (core loop, verifiable reward, head-to-head) and Phase 1.5
  (Tier-2 verifier, anti-bloat guardrails). The offline demo climbs 0.13 → 0.25, head-to-head +$23,
  held-out 0.16 → 0.36, `viol=0%`. The integrity guard provably catches below-floor + hallucinated-price cheating.
- **Untested:** every **LLM-mode path** — they compile with offline fallbacks but have never run against a
  real model. **Tier 0 closes this gap.**
- **Parallel / uncommitted:** `gambit/opponent.py`, `docs/self-learning.md`.
- **Repo:** https://github.com/clocktower39/gambit (public). Branch `phase-1-core`.

---

## 8. To start Tier 0 — needed from the team
- MiniMax **API key** in `.env` (`MINIMAX_API_KEY`).
- MiniMax **base URL** + exact **model id** for "M3" (or we look it up and confirm).
- Confirm `pydantic-ai` is installed in the env.

---

## 9. Risks & guardrails
- **Call volume / cost / latency** — each generation = many negotiations × turns × 2 agents (+ verifier).
  Keep the MVP batch small; scale once it works.
- **Demo reliability** — venue WiFi is a risk; keep the **offline heuristic mode** as a stage fallback and
  pre-bake a recorded golden run.
- **Reward integrity** — never let an LLM judge into the *selector*; keep the deterministic surplus reward
  as the source of truth (the integrity guard is the trust story).
- **Scope creep** — Tier 0 is the line. Everything else waits until the live curve climbs.
