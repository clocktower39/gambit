# Dev Handoff — Gambit Selling Copilot

Start here. This is the curated handoff set for the dev team. Read in order.

> **MVP scope:** general items · simulated buyer · hybrid autonomy · the 6-step loop.
> **The one-sentence bet:** a *bounded, learning* copilot (never sells below the seller's walkaway) produces **better outcomes than a naive seller** by applying negotiation technique — and proves that lift in simulation.
> **Source of truth for all conventions:** [CONVENTIONS.md](CONVENTIONS.md). If any doc conflicts with it, CONVENTIONS wins.

## Reading order

| # | Doc | What it gives the dev team |
|---|-----|----------------------------|
| 1 | [00-PRD.md](00-PRD.md) | Problem, users, the 6-step thesis, scope/non-goals, user flows, numbered functional + non-functional requirements |
| 2 | [SECTION-3-marketplace-playbook.md](SECTION-3-marketplace-playbook.md) | The negotiation playbook — listing-review/approval flow → intent routing → negotiation → close → learn, with templates |
| 3 | [SECTION-4-decision-framework.md](SECTION-4-decision-framework.md) | The runtime decision tree: terminal actions, three-price model, hybrid auto-send/hold/escalate routing, self-check gate |
| 4 | [EVAL-PLAN.md](EVAL-PLAN.md) | How we prove it: simulated-buyer harness, per-capability evals (a–f), technique-lift A/B, regression + guardrail suites, scorecard |
| 5 | [SECTION-5-self-improving-system.md](SECTION-5-self-improving-system.md) | The learning loop: inputs, learning outputs, the edits+outcomes-are-teacher correction, MVP build |
| 6 | [SECTION-6-metrics.md](SECTION-6-metrics.md) | Success metrics relative to the seller's stated objective, technique-lift, hard floors |

**Reference / appendix:** [README.md](README.md) · source audit ([S1](SECTION-1-source-audit.md)) · cross-source synthesis ([S2](SECTION-2-cross-source-synthesis.md)) · reusable assets ([S7](SECTION-7-reusable-assets.md)) · gaps ([S8](SECTION-8-gaps.md)) · final synthesis ([S9](SECTION-9-final-synthesis.md)) · the drop-in config in [`assets/`](assets/) (PRIN/INTENT/OBJ/CONC/COACH, JSON + CSV).

## The 6-step loop (architecture spine)
1. **Understand constraints** — seller input schema (3-price model + urgency + objective) + voice.
2. **Classify buyer intent** — INTENT-xxx + behavioral signals + confidence.
3. **Pick strategy** — PRIN-xxx + CONC-xxx, conditioned on intent + objective + urgency; **persisted as conversation state**.
4. **Generate grounded reply** — OBJ-xxx handlers + voice layer; no fabrication.
5. **Self-check** — pre-send **gate** (bounds/voice/rule/honesty). *Not* the learning signal.
6. **Learn** — seller **edits** + buyer **outcomes** are ground truth; self-score tracked only for calibration.

## Deferred (separate tracks — NOT in this handoff)
- **Scam/safety taxonomy** — its own research track. The books don't cover it, and their "golden bridge" logic is *wrong* for scammers. The decision framework still escalates off-platform/payment-change today; the full taxonomy comes later.
- **Real marketplace integration** — Depop/Vinted/Poshmark have **no messaging/offer APIs** (ToS/ban risk). **eBay** (Best Offer + Negotiation APIs + sold comps) is the only real-integration candidate, post-MVP. MVP runs against the simulated buyer.
- **Payments, cross-listing, the demo script.**

## Open questions for dev (decisions not yet made)
These came out of writing the docs — flagged here so they don't get lost.

| # | Question | Where it bites |
|---|----------|----------------|
| 1 | **Edit-diff → weight update:** how does the diff between an AI draft and the seller's sent message become a playbook weight change? Biggest "how" gap in the learning loop. | SECTION-5 |
| 2 | **Intent-confidence threshold** value for the ESCALATE tier (CONVENTIONS §B says "below threshold" but no number). | SECTION-4 |
| 3 | **Category granularity** for tuning CONC-xxx magnitudes ("category-dependent" asserted, not defined). | SECTION-5 / assets |
| 4 | **Chat latency target** for reply generation (no number sourced). | PRD NFR |
| 5 | **AUTO-SEND timing / anti-bot delay** — instant AI replies may read as a bot and annoy buyers. | SECTION-4 / CONVENTIONS §B |
| 6 | **Eval circularity:** the simulated buyer is built from the same INTENT/CONC taxonomy the agent uses, so lift may be partly self-fulfilling. Label all MVP numbers "lift in simulation"; only real buyers (post-MVP eBay) settle it. | EVAL-PLAN |

## The honest caveat that survives all of this
Bounding by walkaway gives **financial safety**, not **proof of value**. The product's foundational bet is that the *techniques* add lift — that's what the technique-lift A/B in the eval plan exists to measure. Don't let "it never sells below floor" be mistaken for "it works."
