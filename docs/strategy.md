# Gambit — negotiation strategy & rules of engagement

> **The "what the agent does" spec.** `architecture.md` is *how it learns*; this is *how it
> negotiates*. Distilled from the 7-book research in [`playbook/`](./playbook/) (see especially
> [`SECTION-9-final-synthesis.md`](./playbook/SECTION-9-final-synthesis.md) and the
> [concession table](./playbook/assets/json/concession-table.json)). It is also the **cold-start
> prior** for the hybrid `PolicyStore` — seed the `KnobPolicy` and the per-bucket lessons from here,
> then let the learning loop refine it. The strong claim is "improves *past expert strategy*," not
> "past a pushover."

---

## 1. The doctrine in one breath

Seven negotiation books reach one conclusion: **you win the deal by making the buyer feel safe,
understood, and fairly treated — and by setting up a strong position *before* the haggle — not by
out-arguing or manipulating them.** Every book independently found the *honest* version of a tactic
works as well as the dishonest one, and a buyer who feels cheated reneges, disputes, and never
returns. Four nested beliefs:

> **Setup beats tactics. Empathy beats argument. Fairness beats winning. Honesty beats cleverness.**

Everything below is the operational form of that.

---

## 2. The three prices and the one scoreboard

The agent always negotiates inside a fixed envelope (`Item`): **list (public anchor) ≥ target
(aspiration) ≥ floor (the secret wall)**.

- **Anchor on the *target*, never the floor.** Anchoring on the floor and relaxing the moment an offer
  clears it is the #1 seller mistake (playbook COACH-002).
- **The floor is a wall, not a goal.** Never sell below it; the reward enforces this (`reward.py`
  penalizes below-floor, the seller `output_validator` rejects it). No deal beats a bad deal — judge
  every offer against the **BATNA** (relist / hold).
- **The scoreboard is `skill`, not price.** Success = how much of the *buyer's true willingness to pay*
  you extracted (`skill` = surplus vs. the hidden budget), not the sticker number. A high price against
  a buyer who'd have paid more is a mediocre negotiation.

---

## 3. How the agent plays a hand (the move sequence)

Six steps, in order. Each maps to a lever the engine actually has.

| # | Doctrine | Engine lever |
|---|----------|--------------|
| 1 | **Set up before you haggle** — anchor on target, justify with real comps, reasoning *before* the number | `opening_anchor_ratio`; the listing |
| 2 | **Read the buyer before countering** — decode the interest behind the number; classify the type | `opponent.infer` → `buyer_type` (after `K_OFFERS`) |
| 3 | **Probe, don't disclose** — never name your lowest; bounce "what's your lowest?" with a calibrated question | lesson channel (per-bucket text) |
| 4 | **Hold price, add value, then concede on a shrinking conditional ladder** — never free, never equal steps, stops at floor | `concession_rate` shrinking with `turns_elapsed` |
| 5 | **Know your walk line** — BATNA = relist/hold; floor is the wall | `walkaway_patience`; floor |
| 6 | **Close for commitment, then be generous** — lock it, then give the last small crumb | `accept_ratio`; the final move |

---

## 4. Rules of engagement — what the agent MUST and MUST NOT do

This is the part that was never written down. The **NEVERs are hard lines** — they are (or should be)
enforced by the reward + the Tier-1/Tier-2 verifier, not left to the policy's discretion.

**ALWAYS**
- Anchor on **target**; justify with **real comps**, reasoning before the figure.
- **Probe before disclosing** — bounce the "lowest?" question with a calibrated one.
- **Hold price and add value** before any price cut.
- **Concede on a shrinking, conditional ladder** to the floor — never free, never equal steps.
- **Lead with empathy** (label the feeling / acknowledge) before talking price.
- **Be generous on the very last move.**
- **Close on-platform, confirmed, immediately.**

**NEVER (red lines)**
- ❌ **Sell below the floor.** Ever. *(reward wall + seller `output_validator`)*
- ❌ **Reveal or hint at the floor.** *(verifier `floor_leak`)*
- ❌ **Fabricate** a comp, a watcher count, scarcity, or authenticity — even though it "works." *(verifier `honest`)*
- ❌ **Reflexively split the difference** of two arbitrary numbers. A split is OK only if it lands *inside the comp range and above floor* (the Voss-vs-Fisher reconciliation).
- ❌ **Cave to pressure, threats, or review-extortion** — 0% to a bully; offer only the same fair terms you'd give anyone.
- ❌ **React instantly** to a rude/ambiguous message — pause, then respond calmly.
- ❌ **Go off-platform / accept odd payment** — safety stop, not a negotiation. Never ship before confirmed on-platform payment.

---

## 5. The knob doctrine (how the parametric `KnobPolicy` should behave)

The global `KnobPolicy` resolves the 5 scalars from continuous `Features`. This is the *expected
shape* of that function — the seed and the sanity check for what the learner converges toward.

| Feature rises → | `opening_anchor` | `concession_rate` | `accept_ratio` | `walkaway_patience` |
|---|---|---|---|---|
| **margin_ratio ↑** (fat: lots of room above floor) | stay high | slightly higher (room exists) — but make them *work* for it | slightly lower (room to take less than list) | normal |
| **margin_ratio ↓** (thin) | high | **low** — protect the wall, add value instead | **high** (only near-list closes) | shorter (walk sooner) |
| **reservation_gap ↑** (ask far above the est. reservation) | — | concede *toward the estimate*, never below floor; if est. < floor → hold/walk | — | shorter |
| **reservation_gap ≈ 0 / negative** (buyer at/over your ask) | — | small move or none | accept | — |
| **urgency ↑** (seller time pressure) | — | **faster, larger** steps | **lower** (accept sooner) | **shorter** (close, don't grind) |
| **turns_elapsed ↑** | — | **shrinking increments** (Ackerman ladder); smallest near the floor | drift toward accept | approaching the wall |

Two doctrines encoded here: **opponent-aware pricing** (when `reservation_gap` says the buyer is
eager, *stop conceding* — hold near their estimated reservation) and the **shrinking ladder** (each
concession smaller than the last, conditional on closing now).

---

## 6. The situational lessons (cold-start prior for the buckets)

Per-bucket text lessons keyed by `(margin_band, buyer_type)` — seed `PolicyStore.buckets` with these,
then let the gate validate/demote them. `buyer_type` is `unknown` until `K_OFFERS` offers exist.

| buyer_type → | **thin margin** | **mid margin** | **fat margin** |
|---|---|---|---|
| **unknown** (t < K) | open at anchor on target; probe; never reveal the floor; wait for 2 offers before routing | same | same |
| **lowballer** (opens far below) | calibrated question + comps; decline-with-reason, ~0% off; hold/relist | counter *near list* (not midpoint), one conditional move; slow ladder | room exists, but still make them justify — counter near list, don't telegraph the room |
| **measured** (concedes rationally) | small move only; add value (shipping) over price; close inside comps | shrinking conditional ladder; meet inside the comp range; end generous | ladder with normal steps; land on an odd/precise number to signal the real limit |
| **eager** (high urgency to buy) | hold near target; they'll meet you — don't over-give | hold near the estimated reservation; concede little | **do not give away the room** just because it exists — eagerness is leverage *for you* |

*(Concrete concession ceilings — first lowball 0–10%, reasonable ~10–12%, shipping if <~15% of value,
bundle 10–20%, pressure 0% — are in the [concession table](./playbook/assets/json/concession-table.json).
They are synthesized starting defaults; the learning loop tunes them.)*

---

## 7. The full marketplace doctrine (beyond the price core)

The playbook covers the whole sale, not just the price haggle. These rules are doctrine for the real
product but **are NOT exercised by the current price-only self-play engine** (§8) — they apply once
the agent negotiates a real listing.

| Situation | Doctrine | Ceiling (CONC) |
|---|---|---|
| **Asks free shipping** | Absorb shipping *instead of* a price cut — one, not both | < ~15% of value (CONC-005) |
| **Bundle (2+ items)** | Grow the pie: blended discount + combined shipping, conditional ("if you take both") | ~10–20% off singles (CONC-006) |
| **Ghosting / staller** | One "No"-oriented re-engagement that restates the standing offer; then stop | — (PRIN-015) |
| **Stuck on a public low stand** | Build a golden bridge — a *real* face-saving cover (bundle, launch sale) so their move up is a win | framing only (CONC-007) |
| **Aging listing, weak BATNA** | Be honest the walk-away is weak; flex more, but still extract a reciprocal move; relist/refresh first | toward floor (CONC-008) |
| **Loyal / repeat / local buyer** | Small genuine courtesy for relationship value; don't let it become a standing expectation | ~5–15% (CONC-009) |
| **Hostile / extortion** | Balcony; one fair offer; refuse calmly; document & report | **0% to pressure** (CONC-010) |
| **Post-sale dispute / refund** | Acknowledge feeling → own real fault → two options anchored to platform policy; no panic refund | platform-norm partials (CONC-011) |
| **Off-platform / scam pattern** | Hard stop — decline, stay on-platform, never ship first, report | **N/A — do not negotiate** (CONC-012) |
| **"Why isn't this selling?"** | Diagnose the *setup* (photos / comps / audience / timing) before any price cut | — (PRIN-034) |

---

## 8. What the MVP engine actually exercises (honest coverage map)

The current self-play engine is a **price negotiation over a hidden reservation**. It exercises the
*spine* of the doctrine, not the whole thing. Don't mistake a clean curve for "the doctrine works."

| Doctrine element | In the current engine? |
|---|---|
| Anchor on target, shrinking conditional ladder, accept threshold, walk line | ✅ yes — the `KnobPolicy` |
| Probe-don't-disclose, buyer-type tactics | 🟡 partial — the lesson channel, if seeded |
| Never below floor, never leak floor | ✅ yes — reward + verifier |
| Never fabricate, never cave to pressure | 🟡 partial — verifier `honest`; pressure has no analog in the price sim |
| Bundles, shipping, loyalty, golden bridge | ❌ no — needs a real listing / multi-item state |
| Ghosting, disputes/refunds, off-platform scam | ❌ no — needs real async + payment + post-sale |
| "Why isn't it selling" / listing-quality | ❌ no — needs listing + comp data |

---

## 9. How this plugs into the learning machinery

- **Cold-start prior:** §5 seeds the `KnobPolicy` default shape; §6 seeds `PolicyStore.buckets`. The
  gate then validates each lesson on locked held-out and **demotes** what doesn't hold.
- **The red lines (§4 NEVERs) are guardrails, not learnable behavior:** the floor is the reward wall;
  floor-leak / fabrication are verifier checks. The learner tunes *how to win within* the lines; it
  must never learn to cross them — that's what `viol=0` protects.
- **`skill` is the scoreboard** (§2): the doctrine optimizes for extracting true willingness, which is
  exactly what the held-out `skill` curve measures.
- **The honest line:** the agent never invents facts, so "justify with comps" only works when real
  comps are supplied. In the sim there are no comps — that part of the doctrine activates with the eBay
  connector. Until then, the price-core doctrine (§5) is what's live.
