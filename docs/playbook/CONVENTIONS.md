# Handoff Conventions (v2) — single source of truth

> All handoff docs (PRD, playbook, decision framework, eval plan, self-improving system, metrics) MUST conform to this file. If a doc conflicts with this, this wins. Cite stable asset IDs (PRIN/INTENT/OBJ/CONC/COACH) from `assets/`.

## Product in one line
A self-improving **selling copilot** for P2P marketplaces. MVP scope: **general items**, **simulated buyer**, **hybrid autonomy**. The differentiator vs. a chatbot wrapper is the **6-step loop** (below).

## A. Seller input schema — captured at the listing-review step, BEFORE the AI posts
The seller reviews the AI-drafted listing and supplies constraints; nothing goes live until the seller approves. This is step 1 of the loop ("understands the seller's constraints").

| Field | Meaning | Notes |
|---|---|---|
| `list_price` | **Public anchor.** Set high-but-justifiable. | AI proposes from comps; seller approves. **THREE-PRICE MODEL.** |
| `target_price` | Ideal outcome the AI steers toward. | |
| `walkaway_price` | Reservation / floor. **AI never goes below. Hard bound.** | |
| `urgency` | `gone_today` \| `this_week` \| `no_rush` | Pins the speed weight; compresses concession/relist timelines. |
| `objective_weight` | Price ↔ Speed slider (0 = fastest sale … 100 = max price). | The seller's objective. Drives concession aggressiveness (§E). |
| `will_ship`, `ship_pays`, `returns` | Logistics. | |
| `bundle_ok` + rules | Secondary for general items. | |
| `condition_notes` | Known flaws for honest disclosure. | Feeds accusation-audit / trust plays. |
**Invariant the AI enforces:** `walkaway_price ≤ target_price ≤ list_price`. If the seller sets `list = target`, warn — they've pre-conceded the entire range (anchoring principle PRIN-009).

## B. Hybrid autonomy policy (MVP)
Every outbound is AI-drafted. The branch decides whether it auto-sends or waits for seller approval. **Seller edits to held drafts are the primary training signal.**

| Tier | Branches | Behavior |
|---|---|---|
| **AUTO-SEND** (within bounds) | greeting/rapport; "is it available?" (low signal, INTENT-010); factual Q answerable from listing (measurements/condition); **accept offer ≥ target** (auto-lock); confirm already-approved logistics | Sent automatically. Logged. |
| **HOLD FOR APPROVAL** | any counteroffer / price move; **any concession (any discount)**; objection handling (OBJ-*); ghosting re-engagement; high-touch tactics (accusation audit, "that's right" summary) | AI drafts → seller edits/approves → sent. |
| **ESCALATE (never auto-send)** | off-platform / payment-change request; accusation / dispute / refund; **offer < walkaway**; intent-confidence below threshold | Handed to seller; AI may draft a safe holding reply but does not send. |

## C. Brand voice spec
**Friendly, respectful, gen-z, still professional.** Sounds like a real person: warm, lightly casual, contractions, at most one emoji where natural. No corporate stiffness, no forced slang/cringe, no over-apologizing.
- **Re-skin rule:** *tactics decide WHAT to say; voice decides HOW it reads.* Every template passes through the voice layer without losing the move.
  - Accusation audit, stiff: *"You're probably going to think I'm being stubborn..."*
  - Accusation audit, brand voice: *"you're prob thinking i'm being stubborn lol — fair. honestly i've already got it priced under what these go for, so i can't do $15. but tell me what works for you?"*
- **Override:** when the buyer is rude/accusatory, the Difficult-Conversations calm layer outranks casualness (stay warm + steady, drop the jokes). Never manipulate, even in casual tone (Influence guardrails hold).
- **MVP:** one consistent voice. Buyer/category-adaptive voice is v2.

## D. The 6-step agent loop (architecture spine — this is "system, not wrapper")
1. **Understand constraints** — load seller input schema (§A) + voice (§C).
2. **Classify buyer intent** — INTENT-xxx from message + behavioral signals; emit a **confidence score**.
3. **Pick strategy** — select principles (PRIN-xxx) + concession plan (CONC-xxx) conditioned on intent + objective_weight + urgency. **Persist as conversation-level strategy state** — strategy is NOT re-rolled every message.
4. **Generate grounded reply** — apply objection handlers (OBJ-xxx) + voice layer; grounded strictly in seller constraints + comps. No fabricated scarcity/comps/authority.
5. **Self-check = pre-send FILTER, not the teacher** — gate the draft on: within bounds? on-voice? rule/guardrail violation? honesty? If fail → regenerate or escalate. **Self-score is a gate, never the learning signal** (LLM self-grading is unreliable/sycophantic).
6. **Learn** — log outcome + seller edits + buyer response. **Edits + outcomes are ground truth** that update playbook weights. Self-score is recorded only to track its *calibration* against outcomes.

## E. Objective → behavior mapping (so urgency/objective actually do something)
`objective_weight` and `urgency` modulate the CONC-xxx defaults (which are otherwise static synthesized guesses):
- **Opening counter:** price-weighted → counter near `list`; speed-weighted → counter near `target`.
- **Concession increments/cadence:** price-weighted → small shrinking steps, hold longer; speed-weighted → larger, faster steps toward `walkaway`.
- **Accept threshold:** **auto-accept is always gated at ≥ `target`** (the §B AUTO-SEND rule, regardless of objective). Speed-weighting does NOT lower the auto-accept bar; instead it makes the agent *counter lower and concede faster toward `walkaway`*. Accepting an offer **below target but above walkaway** is a concession decision → **HOLD for seller approval** (never auto-sent). This reconciles §B and §E.
- **Relist / price-drop cadence:** `urgency=gone_today` → immediate drops, accept faster.

## F. Simulated buyer harness (eval substrate)
LLM-driven buyer with: a configurable **persona** (maps to INTENT-xxx — lowballer, anchor-shopper, hesitant, ghoster, bundler, rude, serious…), a **hidden willingness-to-pay**, and a behavior policy. **Deterministic via seeds** for regression. Produces full transcripts scored against the eval rubric. Enables **technique-lift A/B** (same buyer seed: agent-with-techniques vs. naive-baseline seller). No real platform; the platform adapter is an interface for later.

## G. North-star metric
**% of completed sales that meet the seller's stated objective** — i.e., hit ≥ `target` when price-weighted, or sold within the urgency window when speed-weighted — *never* below `walkaway`. Supplemented by **technique-lift** (vs. naive baseline) and **self-score calibration** (step-5 score vs. actual outcome).

## H. Scope / non-goals (for the PRD)
- **In:** general items; simulated buyer; hybrid autonomy; the 6-step loop; learning from edits+outcomes.
- **Deferred (separate tracks):** scam/safety taxonomy (own research track); real marketplace integration; payments.
- **Feasibility constraints dev must know:** Depop/Vinted/Poshmark have **no messaging/offer APIs** → automating them risks ToS/bans. **eBay** is the only real-integration candidate (Best Offer + Negotiation APIs + sold comps) and is the natural post-MVP target for general items. Comps are an external data dependency.
