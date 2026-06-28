# Gambit's self-learning loop — standing on the 2026 negotiation-RL frontier

> This is the **research grounding** (which paper buys what). The engineering design that
> implements it — typed agents, Pydantic everywhere, Logfire — is in [`architecture.md`](./architecture.md).
> Module/type names below refer to that rebuild target.

The 2026 shift is from *prompted haggling bots* to *trained agents in verifiable
bargaining environments*. Gambit is built on that thesis: a constrained economic
game with **structured actions, private information, a verifiable-outcome reward,
and integrity rails** — not a better chat prompt.

## What each paper buys us, and where it lives in the code

| Source | Lesson we adopted | In Gambit (typed rebuild) |
|---|---|---|
| **RLVR** — *Instructing LLMs to Negotiate w/ Verifiable Rewards* (arXiv:2604.09855) | Reward = programmatic surplus, **not** an LLM judge; terminal shaping; reservation-enforced sim; `<reasoning>/<dialogue>/<action>` schema | `reward.reward` (surplus from secret floor, −1 integrity / 0 walk / surplus); the schema is a Pydantic `NegotiationMove` (`reasoning · text · action: Literal · offer`), reasoning excluded from `Episode.transcript()` |
| **Bilateral Trade w/ Private Info** (arXiv:2604.16472) | Separate **binding structured offers** from the NL channel; surplus↔deal-rate tension | `NegotiationMove.offer` + `action` (binding channel) ⊥ `.text` (dialogue); deal-rate implicit in the reward (no-deal = 0) |
| **BINEVAL** (arXiv:2606.27226) | Decompose fuzzy quality into **atomic binary checks**; prompt-opt gains collapse after 1–2 iters | `agents/verifier.py` → `AuditVerdict` schema (one `AuditAnswer{answer, reason}` per question — the checklist *is* the type); anti-bloat is a schema constraint: `OptimizerProposal.lessons = Field(max_length=3)` |
| **TERMS-Bench** (arXiv:2605.13909) / **AgenticPay** (arXiv:2602.06008) | Go beyond deal-rate: **infer counterparty type/reservation**, calibrate beliefs | `opponent.py` — reservation estimation + belief-calibration metric (95% offline); `Belief` is a `BaseModel` |
| hud-trace-explorer (patterns only) | Adversarial reward-integrity guard so the curve is defensible | `reward.audit_episode` (Tier-1 deterministic) + `agents/verifier.py` (Tier-2); plus per-agent `output_validator`s that reject below-floor / over-budget moves before they ever enter a transcript |

**Reward philosophy (the load-bearing nuance):** binary/LLM evaluators give *dense
qualitative feedback* to the optimizer, but **never select**. Money-moving selection
stays on the deterministic verifiable surplus. This is the best anti-reward-hacking
defense — the judge would be the hackable component.

## Proven in scaffolding → carried into the typed rebuild

These mechanisms were validated end-to-end in the throwaway scaffolding; the rebuild keeps the
behavior and expresses it through the typed contract (see [`architecture.md`](./architecture.md)).

- ✅ Verifiable surplus reward + Tier-1 deterministic integrity audit (`reward.py`)
- ✅ Tier-2 BINEVAL binary-question verifier on a stronger model (`agents/verifier.py` → `AuditVerdict`)
- ✅ **Verifier → optimizer dense feedback**: the optimizer audits the worst transcripts and turns
  each flag into a targeted lesson (shapes proposals, never selects)
- ✅ Anti-bloat: lessons capped at the schema level (`OptimizerProposal.lessons = Field(max_length=3)`) + dedup validator
- ✅ Held-out personas + early-stop when held-out plateaus (`improve_loop`)
- ✅ Opponent modeling + belief-calibration eval (`opponent.py`; `Belief` is a `BaseModel`)
- ➕ New in the rebuild: per-agent `output_validator`s as hard integrity rails (below-floor /
  over-budget moves trigger a `ModelRetry` instead of reaching the transcript)
- ➕ New (feature layer): the optimizer can run as a **Gemini Antigravity managed agent** that
  rewrites its own tactics `SKILL.md` generation over generation in a stateful sandbox — a model
  editing the instructions that drive it (recursive self-improvement). It is a *stronger proposer*
  only: the deterministic verifiable surplus + held-out promotion gate still select. The
  reward-philosophy invariant below is unchanged. See [`architecture.md`](./architecture.md#self-improving-optimizer--gemini-antigravity-managed-agent).

## Remaining refinements (prioritized menu — none are blockers)

1. **Opponent-aware pricing (highest demo value).** Wire `opponent.infer` into
   `agents/seller.py`: estimate the buyer's reservation from their offers and hold near it.
   `opponent.recommend_ask(belief, item)` already returns the target ask. Effort: ~30
   lines in `agents/seller.py` + a `read_opponent: bool` knob on `Strategy`. Story:
   *"it figures out you're eager and stops conceding."*
2. **Belief calibration on the panel (TERMS-Bench).** Add `opponent.calibration_report`'s
   accuracy to the metric panel so eval shows *type inference*, not just deal-rate.
3. **Surplus↔deal-rate dial (bilateral-trade lesson).** Expose `α` in `reward.reward`
   (`α·surplus + (1−α)·closed`) and sweep it for a small Pareto curve — *"dial from
   closer to maximizer."* Effort: tiny; keep `α=1` as default so nothing regresses.
4. **Strategic-phase labels (RLVR narrative).** Classify each generation from existing
   panel metrics (`first_offer_ratio`, `overshoot_rate`, `close_rate`) into
   naive → aggressive-anchor → deadlock → rational-concession. Pure storytelling, ~20 lines.
5. **Held-out promotion gate.** Today held-out only *early-stops*; optionally also refuse
   to *promote* a candidate that regresses held-out (stricter anti-overfit).

## Explicitly out of scope for the 18h core (cite as scale-up)

GRPO/weight-level RL on a 30B (the RLVR recipe) → the scale-up "weight-level RSI" stretch
(LoRA on winning transcripts, DO GPU droplet). **Gemma 4 on-device specifically is out of
scope.** Agentic-commerce protocol rails (LLM-X, Universal Commerce Protocol),
device-native privacy, and full authorization layers → future-work framing, not built.
