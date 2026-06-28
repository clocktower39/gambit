# Gambit — North Star

**A self-improving seller agent.** It lists an item, negotiates to the best price in a
reasonable time, and **gets better from its own negotiations — with zero human labeling.**
The current offline loop improves a seller policy against reproducible buyer families; the
target loop learns from a ladder of realistic exercises: deterministic buyer panels, stronger
LLM buyers with their own objective, human pressure tests, and eventually live marketplace
offers. Self-play is useful as one adversarial drill, but it is not the product truth. The
counterparty is **pluggable** — a human can step in as the buyer at any moment, and real buyers
drop in unchanged when a marketplace is wired. The objective is singular: **a real seller agent
that never stops improving.**

> Originated at the AI Engineer World's Fair 2026 (theme: Continual Learning). We are not
> building a demo — we are building the real thing, and continual improvement is the whole
> point. Everything below is in service of *real and improving*, not *impressive on a stage*.

---

## 1. What "done" means

Done is not a date — it's three properties that have to hold and keep holding.

1. **It's real.** Live structured negotiation on **MiniMax M3**: typed moves, private
   information (secret floor / hidden reservation), a binding offer channel separate from the
   chat. The seller is the product. Counterparties may be deterministic fixtures, LLM buyers,
   humans, or live market buyers, but they all enter through the same typed interface. The same
   seller policy that trains offline plugs into a **human buyer** or a **live marketplace** with
   nothing in the seller loop changed.
2. **It keeps improving.** Across generations, with no human labels, **verifiable surplus
   measurably climbs** — and it climbs on **held-out counterparties it never trained against**,
   not just the ones it practiced on. Improvement that doesn't transfer isn't improvement; the
   held-out signal is the truth.
3. **The gains are trustworthy.** The integrity guard reports `viol=0%` — the agent is winning
   by negotiating better, not by leaking its floor, hallucinating a close, or (under self-play)
   colluding with itself. The reward can't be gamed because the thing that *selects* is
   deterministic, and an independent verifier audits every gain.

When all three hold and the curve is still climbing, we've built the thing. The more it
negotiates, the better it gets — that's the product. How each property is measured (safety vs.
transferable validity, the held-out curve, the substrate ablation) is in [`docs/eval-plan.md`](docs/eval-plan.md).

---

## 2. The counterparty is pluggable (the load-bearing idea)

The negotiation loop is a **referee over two policies**. It does not know or care what is on
the other side of the table — it only exchanges typed moves and scores the outcome. That one
decision is what makes this real instead of a simulator:

| Counterparty | What it is | When |
|---|---|---|
| **Deterministic buyer families** | Reproducible reservation-respecting counterparties used by the current offline gate. | Now — the implemented training/eval substrate. |
| **LLM buyer panel** | Reward-seeking buyer agents with hidden budgets and different tactics. These are harder, more varied exercises than the deterministic families. | Next realism step — after the buyer hat is wired. |
| **Self-play / checkpoint league** | The seller's current or past policy wearing a buyer hat with a separate buyer objective. Useful adversarial pressure, not the definition of reality. | A drill inside the panel, not the only target. |
| **Human** | A person types **or speaks** the buyer's messages. Same interface, same typed moves — voice is a **LiveKit + Gemini Live** shell (real-time, cross-language Live Translate) that emits the same `BuyerMove`. | Any time — drop in to feel it out, pressure-test it, or sanity-check a generation. |
| **Live market** | A real buyer via a connector (eBay Best Offer first, **via the eBay API**). The seller's moves become real offers; the reward becomes the real sale. | When a marketplace is wired — the engine is unchanged. |

We use synthetic buyers because they are cheap, repeatable, and let us run paired A/B gates before
live traffic exists. But realism comes from **varied counterparties and held-out transfer**, not from
pretending a fake market is the market. Swapping in a human or a real marketplace is a policy swap,
not a rewrite.

The seller side is **one policy managing many listings and many buyer threads**. That should inform
the seller's move, but only from truthful seller-visible state. Parallel buyers and active inventory
are the seller's real BATNA: if three buyers are actually alive on one listing, hold firmer; if a stale
listing has one serious buyer, flex; if a buyer wants multiple active items, grow the deal. The useful
exercise is not a giant fake marketplace; it is a seller agent learning to use realistic context
without inventing leverage.

### Where self-play helps, and where it doesn't

A scripted buyer caps how good the seller can get — you can't out-negotiate your own heuristics.
Reward-seeking LLM buyers and self-play raise the bar because the buyer can adapt and fight for its
own surplus. That makes them valuable drills. They are not, by themselves, proof that the agent will
work in a real marketplace.

The realistic shape is a **counterparty panel**:
- deterministic buyers for reproducible gates;
- LLM buyers and checkpoint self-play for adversarial pressure;
- humans for taste, weirdness, and failure discovery;
- live marketplace threads for the final distribution.

The selector should promote a change only when it wins on held-out panels and does not violate the
integrity rails. The product claim is seller improvement that transfers, not "it beat a clone of
itself."

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
 Strategy ─► seller ⇄ counterparty panel ─► Episodes ─► Score ─► Optimizer ─► A/B select ─┐
 (policy)      (typed buyers: fixtures,       (transcripts)  (verifiable   (reflect →      │
     ▲          LLM, human, market)                       surplus +        lessons)        │
     │                                                    Tier-1 audit)                    │
     └──────────────  promote the better seller policy, next generation  ◄──────────────────┘
        held-out early-stop (anti-overfit)   Tier-2 verifier audits integrity (binary checklist)
        checkpoint/self-play drills are optional panel members, not the whole proof
```

- **Reward = deterministic verifiable surplus** from the secret floor: `(price − floor)/(list − floor)`.
  Terminal shaping: below-floor / format → −1; no-deal / walk-away → 0; deal → surplus.
  **No LLM judge in the selector.** In buyer-agent drills, each side optimizes its *own* surplus
  (seller `price − floor`, buyer `budget − price`) so the pressure is adversarial instead of scripted.
- **Reward-integrity guard** so the curve is defensible: Tier-1 deterministic audit (done), Tier-2
  binary-question verifier on a *different model* (done), Tier-3 held-out counterparties (done).
- **What's learned is a policy, not a prompt blob** (see below): the optimizer proposes *one atomic
  change*, and a paired held-out A/B gate keeps it or drops it. The loop early-stops on a held-out plateau.

### What actually gets learned (a frozen model still learns)

**MiniMax M3's weights never change — it's a frozen actuator.** So everything Gambit learns lives in
*data it reads at inference time*. The learned artifact is a **hybrid** — a global *parametric knob
policy* plus a *per-bucket text-lesson table* — **not** a single global tactics prompt (and not a pure
27-bin table, which starves on a small episode budget):

- **Numeric channel — pooled, parametric.** The 5 knobs are the output of a small function of
  *continuous, scale-free* features (margin ratio, reservation gap, urgency); its parameters are
  **global**, so one thin-margin episode sharpens the concession curve *everywhere*. Sample-efficient.
- **Text channel — per-bucket, interpretable.** Short lessons keyed by a **coarse** tuple
  `(margin_band, buyer_type)` — `price_band` dropped (the reward is scale-invariant, so it added bins,
  not signal); `buyer_type` is `unknown` until a few offers exist (don't route on a t=0 guess). This is
  the diffable, Antigravity-editable channel.
- **Why not one global `SKILL.md` + 5 knobs:** fixed capacity (BINEVAL — which we cite — shows prompt-opt
  plateaus after 1–2 iters), FIFO forgetting, and one knob-set can't be "hard on a thin-margin lowballer"
  *and* "soft on an eager fat-margin buyer."
- **How it improves without weights today:** generate deterministic episodes → propose one atomic knob
  change → **promote only if a paired A/B on gating seeds raises surplus with `viol=0` and clears
  `min_support`**. The locked, structurally-different held-out is measured after tuning, not used for
  selection. FDR, global non-regression, demotion, and text-lesson promotion are the next guardrails.
- **Retrieval is a table lookup, not vectors.** Structured key → a `dict` / `WHERE bucket=…`, no
  embeddings. pgvector is reserved for *one optional* job (semantic few-shot of past buyer *messages*)
  and only if it beats structured-key exemplars in an A/B.
- **Honest ceiling:** each bucket plateaus at what the frozen model can execute — you can't prompt past
  the base model. The claim is **monotonic + coverage-growing + attributable + locked-held-out-verified,
  not unbounded.** Weight-level RL (*Later*) lifts the per-bucket ceiling. The truthful "never stops improving."

---

## 4. Tech stack (decided)

**Core — the high-volume inner loop.** A generation is thousands of structured calls
(seller move × buyer move × turns, + the Tier-2 verifier). Cost and latency dominate here, so
the inner loop stays on a fast, cheap structured model. **Gemini lives on the feature layer
below, never per move.**

| Layer | Choice | Notes |
|---|---|---|
| **Inner-loop LLM** | **MiniMax M3** | The seller/buyer/verifier structured calls. OpenAI-compatible; the provider lives in one place (`llm.py`) and is swappable. |
| **LLM framework** | **Pydantic AI** | Typed, validated structured outputs — replaces hand-rolled JSON parsing; retries on validation failure. |
| **Models / types** | **Pydantic** (`BaseModel`, `pydantic-settings`) | One typed contract end-to-end — no dataclasses. Validators are the integrity rails. |
| **Observability** | **Logfire** | `instrument_pydantic_ai()` — every agent run + the improvement curve in one dashboard; debugs the never-tested LLM paths. |
| **Language** | Python (≥ 3.11) | |
| **Packaging** | **uv** | `pyproject.toml` + `uv.lock`; `uv run` / `uv add` (not pip). |
| **Deployment + data** | **DigitalOcean** | App Platform (deploy) · Managed Postgres + pgvector (memory) · Spaces (images). |

**Gemini 3.5 feature layer.** Three bleeding-edge Gemini surfaces, each mapped to the one place
in the architecture where it genuinely belongs — not bolted on. Each is a *second backend behind
an interface we already have*, so the core loop, the reward, and the integrity rails are unchanged.

| Surface | Where it plugs in | What it buys |
|---|---|---|
| **Managed agent — Gemini Antigravity** (`antigravity-preview-05-2026` via the **Interactions API**) | The **optimizer** (a *second backend* behind the existing proposal interface). | A hosted agent reads one weak bucket's scored transcripts + verifier flags in an ephemeral sandbox, runs the eval harness, and **rewrites that bucket's skill fragment in the situation-keyed `PolicyStore` — the policy improving its own skill files**, carried across generations via the stateful `environment_id`. The agent *proposes*; the per-bucket held-out A/B over deterministic surplus still *selects*. This is the "models build themselves" story made literal. |
| **Gemini Live / Live Translate** (`gemini-3.5-live-translate-preview`) **over LiveKit** | The **human buyer seat** (existing counterparty) as a voice shell. | A person haggles by voice, in their own language, against the seller — continuous low-latency speech-to-speech. The shell just turns audio → a typed `BuyerMove`; the referee never knows it wasn't text. |
| **Nano Banana** (Gemini image gen) | The eBay listing pipeline. | Generates the listing photo + precise text-in-image for the post we put on the real marketplace. |

> **The integrity wall is untouched.** No Gemini surface touches the *selector*. The Antigravity
> optimizer is one more proposer (§3: "evaluators give the optimizer dense feedback but never
> select"); the verifiable surplus reward remains the sole source of truth.
>
> **Where Gemini is *not* used (decided):** the live-market connector uses the **eBay API**
> (Trading/Best-Offer), **not** Computer Use — scraping a UI with no API is generally a ToS
> violation, and eBay's API covers listing + offers directly. **Gemma 4 on-device** is out of scope.

---

## 5. Components & status

✅ done (offline-verified) · 🟡 partial · ⬜ to-do

| Component | Role | Status |
|---|---|---|
| `models.py` / `personas.py` | Item, Strategy, Episode, counterparty reservations (hidden budgets) | ✅ |
| `negotiation.py` | referee one episode over two policies → terminal outcome | ✅ |
| `metrics.py` → `reward.py` | verifiable surplus reward + terminal shaping + Tier-1 audit + panel | ✅ |
| seller policy / buyer policies | the product seller + a panel of typed counterparties | 🟡 current buyers are deterministic/passive — add reward-seeking LLM buyers; LLM path **untested** |
| `optimizer.py` | reflection → lessons, anti-bloat dedup/cap, verifier-rubric feedback | 🟡 LLM path **untested** |
| `policy.py` (the learned artifact) | hybrid `PolicyStore`: global parametric `KnobPolicy` + per-bucket text lessons; current loop promotes knob changes by paired gating A/B; FDR/global non-regression/demotion are not wired yet | 🟡 |
| `market.py` / portfolio state | one seller, multiple listings, parallel buyer threads, first-firm-commitment guard | 🟡 typed state seam + feature tests |
| optimizer (Antigravity backend) | Gemini managed agent — multi-step sandbox loop improving **one bucket's** lesson fragment per call (stateful env); proposes, never selects (deferred post-MVP) | ⬜ |
| voice buyer shell | LiveKit room + Gemini Live/Translate → typed `BuyerMove` in the human seat | ⬜ |
| listing media | Nano Banana listing image/text-in-image for the eBay post | ⬜ |
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

> **MVP build order (decided).** M0 de-risk + typed foundation → M1 hybrid `PolicyStore` (offline) →
> M2 a structurally-different held-out family → **M3 the substrate ablation = the headline** → M4 typed
> agents live on MiniMax + reward-seeking buyer → M5 live anti-collusion verifier. Deferred for the MVP:
> Antigravity, voice, eBay, Nano Banana, pgvector, checkpoint league, deploy. Full per-milestone
> done-criteria + eval gates in [`docs/eval-plan.md`](docs/eval-plan.md).

### Now — de-risk + the engine real and improving live
- [x] uv project (`pyproject.toml` + `uv.lock`); `pydantic-ai` installed.
- [ ] **M0 spike (gate, first):** prove `OpenAIChatModel(minimax) + output_type=SellerMove` returns
      schema-valid output + `response_format` enforcement on M3; **measure $/call + latency → per-generation
      cost**; fill `MINIMAX_BASE_URL`/`MODEL` (TBD). *Runs in parallel with the no-LLM foundation below.*
- [ ] `gambit/llm.py`: Pydantic AI model on MiniMax + typed outputs
      (`SellerMove`, `BuyerMove`, `OptimizerProposal`, `AuditVerdict`).
- [ ] Refactor seller/buyer/`optimizer.propose_llm`/`verifier._verify_llm` to typed agents;
      keep the deterministic policy as a first-class offline path. Delete `inference.py`'s JSON parsing.
- [ ] Config via `pydantic-settings`: `MINIMAX_API_KEY`/`_BASE_URL`/`_MODEL`, keep `OFFLINE`.
- [ ] Logfire at the entry point — every agent run + the curve traced.
- **Real when:** a live MiniMax run shows surplus climbing across generations with `viol=0%`,
      and the gains hold on a **locked, structurally-different** held-out set.

### Next — make the exercises more realistic
- [ ] **Hybrid `PolicyStore` (the learned artifact):** a global *parametric* knob policy (pooled
      strength) + per-bucket *text lessons*, keyed by a coarse `(margin_band, buyer_type)` (no
      `price_band`; `buyer_type` after K offers). Promote **one atomic change** per generation via a
      paired single-toggle A/B on a gating held-out, keep the **locked, structurally-different** held-out
      for headline measurement only, and add **FDR + global non-regression + a demotion path** before
      claiming the full statistical guardrail.
- [ ] **Portfolio-context training slice:** teach the seller to use truthful seller-visible state:
      active buyer count, best real competing offer, listing age, inventory pressure, bundle
      opportunity, and first-firm-commitment wins. Start with one primary thread plus honest background
      state/replay before building a full marketplace simulator.
- [ ] **Reward-seeking buyer:** the buyer-hat optimizes its own surplus (today it's a passive
      reservation-respecting heuristic). This turns buyer agents into useful adversarial drills.
- [ ] **Structurally-different held-out:** make the held-out promotion gate run against a different
      buyer-policy family (LLM buyer / human), not the same simulator with new params — otherwise
      "held-out" is in-distribution and the transfer claim is hollow.
- [ ] **Checkpoint league:** include past selves in the counterparty panel, but treat the league as
      one held-out pressure source, not proof by itself.
- [ ] **Anti-collusion audit:** lean on the Tier-2 verifier to catch a shared-policy handshake;
      add held-out *promotion* gate (refuse to promote a candidate that regresses held-out).
- [ ] **Opponent-aware pricing:** wire `opponent.infer` into the seller — hold near the
      estimated reservation instead of folding.
- [ ] **Self-improving optimizer (Gemini Antigravity):** the optimizer becomes a hosted managed
      agent that, between generations, reads **one weak bucket's** scored transcripts + verifier flags
      in its sandbox and **rewrites that bucket's lesson fragment** (`PolicyStore.buckets[target_bucket]`),
      persisted across generations via the `environment_id`. The local Pydantic-AI optimizer stays the
      default/offline backend; this is a second backend behind the same proposal interface. **Still
      proposes, never selects** — the per-bucket held-out A/B gate decides.

### Then — real counterparties
- [ ] **Human-in-the-buyer-seat:** the same interface, a person on the other side — try it, break it.
- [ ] **Voice buyer (LiveKit + Gemini Live/Translate):** the human seat, by voice, cross-language —
      a LiveKit room + Gemini Live shell turns audio into the same typed `BuyerMove`. Core loop unchanged.
- [ ] **eBay connector (eBay API):** real list → Best Offer → counter → accept (`docs/ebay.md`),
      with the listing image generated by **Nano Banana**.
- [ ] **Memory:** persist the `PolicyStore` to DO Postgres (plain indexed rows — the spine).
      pgvector is *optional* Tier-C semantic exemplar retrieval, gated behind an A/B vs structured-key
      exemplars — not the learning substrate.
- [ ] **Deploy:** DO App Platform + a live view of the climbing curve.

### Later — scale-up (only when the core is unshakable)
- [ ] Weight-level RL on winning transcripts (GRPO/LoRA). *(Gemma 4 on-device: out of scope.)*

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
- **Reference today; an optional cold-start *prior* tomorrow.** The 7-book negotiation playbook lives
  in `docs/playbook/` — literature we read *around* the system. "Zero human labeling" is a property of
  the **reward signal** (verifiable surplus, no labeled transcripts), **not** of the initialization —
  so seeding a bucket's starter lessons from the playbook is a *prior*, like giving AlphaZero the rules,
  not a label. The distilled doctrine + the per-bucket starter lessons + the red lines are written up in
  [`docs/strategy.md`](docs/strategy.md). The stronger claim is "it improves *past a strong prior*," not "past a deliberate
  pushover." Optional, off by default; the reward + held-out gate still decide what survives, so the
  integrity wall is untouched.
- **Repo:** https://github.com/clocktower39/gambit (public).

---

## 8. Risks & guardrails
- **Self-play collapse / collusion** — the central risk of a shared policy on both sides. Guard:
  Tier-2 verifier (anti-handshake), checkpoint league, held-out promotion gate. Never relax these.
- **Reward integrity** — never let an LLM judge into the *selector*; the deterministic surplus
  reward is the source of truth. Evaluators give the optimizer dense feedback but never select.
  **This holds for the Antigravity optimizer too:** it rewrites tactics and proposes knobs, but the
  verifiable surplus + held-out promotion gate decide what survives. A managed agent that "evaluates"
  must never become the reward.
- **Managed-agent cost/blast radius** — Antigravity spins an ephemeral Linux sandbox per call, so it
  runs **once per generation** (the optimizer step), never per move. The inner loop stays on MiniMax.
  Sandbox the agent's eval harness; treat its file edits as proposals gated by the deterministic check.
- **Voice shell is I/O only** — LiveKit + Gemini Live transcribes/translates audio into the *same*
  typed `BuyerMove`; it adds no new integrity surface and changes nothing in the referee or reward.
  Treat transcribed audio as untrusted input, never as instructions.
- **Call volume / cost / latency** — a generation = many negotiations × turns × 2 agents (+ verifier).
  Keep batches small while iterating; scale once it holds.
- **Overfitting to self** — train and judge on held-out counterparties, not just the practiced ones.
- **Gate leakage (the deepest learning risk)** — the held-out set is *consumed* by the promotion gate,
  so a curve can climb by overfitting the gate, not by transfer. Guard: a **three-way split** — train ·
  a *gating* held-out (the gate may overfit it) · a **LOCKED final test set touched once** for the
  headline. The headline number comes only from the locked set.
- **Promoting noise / never forgetting** — hundreds of per-bucket A/Bs ⇒ false positives; "never evict"
  locks them in forever. Guard: **min-support** before a bucket is targeted/promoted, **FDR control**
  across a generation's candidates, **one atomic change per A/B** (so gains attribute), and a **demotion
  path** (re-audit promoted entries on fresh seeds; evict dead effects). "Monotonic" = performance under
  a guard, not a hoard.
- **Easy-held-out illusion** — if held-out climbs *faster/higher* than train, the held-out is easier,
  not sterner. Guard: held-out is a **different, frozen policy family** (not the same sim with a new
  `budget_ratio`), report **skill** (vs hidden budget) not just surplus, and treat held-out Δ > train Δ
  as a red flag. No real frozen-LLM number exists yet — offline figures are labeled illustrative.

---

## 9. Prize alignment (a byproduct, not the point)

We build the real thing first; the feature layer above happens to map cleanly onto the hackathon
criteria. Nothing here is bolted on for a stage — each surface earns its place in the architecture.

| Criterion | How Gambit qualifies |
|---|---|
| **Theme: Continual Learning** *(required)* | The whole product — a seller policy improving with zero human labels, verifiable surplus climbing across generations, and gains holding on held-out counterparties. |
| **Theme: Self-Improvement Stack / Recursive Intelligence** | The agent learns a **situation-keyed policy it edits itself** — the Antigravity optimizer improves one weak bucket's lesson fragment generation over generation (stateful env) under a deterministic, gameable-proof reward, promoted only by a per-bucket held-out A/B. A model improving the structured policy that drives it, with the integrity wall intact. |
| **Best Gemini 3.5** | **Managed Agents** (Antigravity via the Interactions API, `AGENTS.md` + per-bucket skill fragments, stateful `environment_id`) **+ Gemini Live / Live Translate** for the voice buyer **+ Nano Banana** for listing media — three new surfaces combined, not a wrapper chatbot. |
| **Best LiveKit** | The human buyer seat negotiates by **voice over LiveKit**, cross-language via Gemini Live Translate — the pluggable counterparty made tangible. |
| **Best DigitalOcean** | The app runs on DO — App Platform (deploy + live curve), Managed Postgres + pgvector (memory), Spaces (images). |
