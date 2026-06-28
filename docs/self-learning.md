# Gambit's self-learning loop — standing on the 2026 negotiation-RL frontier

The 2026 shift is from *prompted haggling bots* to *trained agents in verifiable
bargaining environments*. Gambit is built on that thesis: a constrained economic
game with **structured actions, private information, a verifiable-outcome reward,
and integrity rails** — not a better chat prompt.

## What each paper buys us, and where it lives in the code

| Source | Lesson we adopted | In Gambit |
|---|---|---|
| **RLVR** — *Instructing LLMs to Negotiate w/ Verifiable Rewards* (arXiv:2604.09855) | Reward = programmatic surplus, **not** an LLM judge; terminal shaping; reservation-enforced sim; `<reasoning>/<dialogue>/<action>` schema | `metrics.reward` (surplus from secret floor, −1 integrity / 0 walk / surplus), `Message.reasoning|text|offer`, hidden reasoning excluded from `transcript()` |
| **Bilateral Trade w/ Private Info** (arXiv:2604.16472) | Separate **binding structured offers** from the NL channel; surplus↔deal-rate tension | `Message.offer` (binding) ⊥ `Message.text` (dialogue); deal-rate is implicit in the reward (no-deal = 0) |
| **BINEVAL** (arXiv:2606.27226) | Decompose fuzzy quality into **atomic binary checks**; prompt-opt gains collapse after 1–2 iters | `verifier.py` (binary checklist on a stronger model), `optimizer.merge_tactics` (dedup + length cap) |
| **TERMS-Bench** (arXiv:2605.13909) / **AgenticPay** (arXiv:2602.06008) | Go beyond deal-rate: **infer counterparty type/reservation**, calibrate beliefs | `opponent.py` — reservation estimation + belief-calibration metric (95% offline) |
| hud-trace-explorer (patterns only) | Adversarial reward-integrity guard so the curve is defensible | `metrics.audit_episode` (Tier-1 deterministic) + `verifier.audit_run` (Tier-2) |

**Reward philosophy (the load-bearing nuance):** binary/LLM evaluators give *dense
qualitative feedback* to the optimizer, but **never select**. Money-moving selection
stays on the deterministic verifiable surplus. This is the best anti-reward-hacking
defense — the judge would be the hackable component.

## Done

- ✅ Verifiable surplus reward + Tier-1 deterministic integrity audit (`metrics.py`)
- ✅ Tier-2 BINEVAL binary-question verifier on a stronger model (`verifier.py`)
- ✅ **Verifier → optimizer dense feedback**: `propose_llm` audits the worst transcripts
  and turns each flag into a targeted lesson (shapes proposals, never selects)
- ✅ Anti-bloat: lessons merged with dedup + hard length cap (`optimizer.merge_tactics`)
- ✅ Held-out personas + early-stop when held-out plateaus (`improve_loop.improve`)
- ✅ Opponent modeling + belief-calibration eval (`opponent.py`)

## Remaining refinements (prioritized menu — none are blockers)

1. **Opponent-aware pricing (highest demo value).** Wire `opponent.infer` into
   `SellerAgent`: estimate the buyer's reservation from their offers and hold near it.
   `opponent.recommend_ask(belief, item)` already returns the target ask. Effort: ~30
   lines in `seller_agent.py` + a `read_opponent: bool` knob on `Strategy`. Story:
   *"it figures out you're eager and stops conceding."*
2. **Belief calibration on the panel (TERMS-Bench).** Add `opponent.calibration_report`'s
   accuracy to the metric panel so eval shows *type inference*, not just deal-rate.
3. **Surplus↔deal-rate dial (bilateral-trade lesson).** Expose `α` in `metrics.reward`
   (`α·surplus + (1−α)·closed`) and sweep it for a small Pareto curve — *"dial from
   closer to maximizer."* Effort: tiny; keep `α=1` as default so nothing regresses.
4. **Strategic-phase labels (RLVR narrative).** Classify each generation from existing
   panel metrics (`first_offer_ratio`, `overshoot_rate`, `close_rate`) into
   naive → aggressive-anchor → deadlock → rational-concession. Pure storytelling, ~20 lines.
5. **Held-out promotion gate.** Today held-out only *early-stops*; optionally also refuse
   to *promote* a candidate that regresses held-out (stricter anti-overfit).

## Explicitly out of scope for the 18h core (cite as scale-up)

GRPO/weight-level RL on a 30B (the RLVR recipe) → maps only to the optional Gemma-4
LoRA stretch. Agentic-commerce protocol rails (LLM-X, Universal Commerce Protocol),
device-native privacy, and full authorization layers → future-work framing, not built.
