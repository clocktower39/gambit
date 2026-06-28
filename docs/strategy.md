# Gambit — negotiation strategy & rules of engagement

> **The "what the agent does" spec.** `architecture.md` is *how it learns*; this is *how it
> negotiates*. Distilled from the 7-book research in [`playbook/`](./playbook/) (see especially
> [`SECTION-9-final-synthesis.md`](./playbook/SECTION-9-final-synthesis.md) and the
> [concession table](./playbook/assets/json/concession-table.json)). It is also the **cold-start
> prior** for the hybrid `PolicyStore` — seed the `KnobPolicy` base knobs, feature coefficients, and
> per-bucket lessons from here, then let the learning loop refine them. The strong claim is "improves
> *past expert strategy*," not "past a pushover."

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
| 4 | **Hold price, add value, then concede on a shrinking conditional ladder** — never free, never equal steps, stops at floor | `concession_rate` shaped by `turn_frac` |
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
- **Keep real buyers parallel** — live interest is BATNA; do not negotiate one buyer to exhaustion while
  other threads go cold.
- **Be generous on the very last move.**
- **Close on-platform, confirmed, immediately.**

**NEVER (red lines)**
- ❌ **Sell below the floor.** Ever. *(reward wall + seller `output_validator`)*
- ❌ **Reveal or hint at the floor.** *(verifier `floor_leak`)*
- ❌ **Fabricate** a comp, a watcher count, scarcity, or authenticity — even though it "works." *(verifier `honest`)*
- ❌ **Invent competing buyers.** Parallel interest is leverage only when it exists in seller-visible state.
- ❌ **Reflexively split the difference** of two arbitrary numbers. A split is OK only if it lands *inside the comp range and above floor* (the Voss-vs-Fisher reconciliation).
- ❌ **Cave to pressure, threats, or review-extortion** — 0% to a bully; offer only the same fair terms you'd give anyone.
- ❌ **React instantly** to a rude/ambiguous message — pause, then respond calmly.
- ❌ **Go off-platform / accept odd payment** — safety stop, not a negotiation. Never ship before confirmed on-platform payment.

### 4.1 The walk-away — bluff or real (and how to handle one)

A walk-away is the most common pressure move, and usually a **bluff, not the end**. The target
runtime should treat "forget it / I'm out / 350 or I walk" as a *tactic*, not a terminal event:

- **The wall doesn't move because someone stood up.** Never let a threatened or actual walk push you
  below the floor or into a panic concession — extracting exactly that is the bluff's whole purpose.
- **Call it or bridge it — once.** On a walk the agent gets one calm response: either let them go (the
  BATNA/relist stands), or make **one** final *conditional* offer with a small face-saving crumb
  ("$465, today, and I'll include the case") — never a capitulation, never below floor.
- **Don't chase.** One bridge, then stop. Chasing a walker with escalating cuts just trains them to
  walk again.
- **The agent's own walk is real, not theater.** A calm, BATNA-backed walk is its strongest lever
  against a stuck lowballer (use it when the estimated reservation < floor, or the ladder has stalled) —
  but it only walks when it would genuinely relist, never as a stunt.
- **Integrity (self-play):** a *staged* mutual walk that resolves into a cozy split is collusion, not
  negotiation — the Tier-2 verifier (`buyer_in_character`) must flag a concession that follows a walk
  for no legitimate reason.

**Mechanical requirement (implemented).** For the bluff to exist at all, a walk must be **non-terminal** —
the referee gives the other side one rebuttal turn, and no-deal is reached only on a re-confirmed/second
walk or timeout. This now lives in `run_episode` (a per-side `walked` set; see `architecture.md` and
`tests/test_foundation.py`). It is currently **latent** in the offline loop — the deterministic buyers
rarely walk — and becomes load-bearing once a *tactical* policy (the typed LLM seller, slice 5, or a
dedicated bluffing-buyer family) actually uses the walk as a lever.

### 4.2 One seller, many buyers

The real agent is **one seller policy managing a portfolio**, not one isolated negotiator per thread.
That is the only way BATNA becomes operational. A live backup buyer, a stale listing, a bundle-capable
buyer, and other active listings should all change the seller's move:

- **Parallel interest strengthens the wall.** More live buyers on the same listing means slower
  concession, higher accept threshold, and more patience — but only if those buyers really exist.
- **Stale inventory weakens the wall.** Days live, no competing offers, and explicit inventory pressure
  should make the seller more flexible while still respecting the floor.
- **First firm commitment wins.** The seller can keep threads warm, but once one buyer commits
  on-platform, the listing closes and competing threads are shut down. No double-selling.
- **Bundles grow the pie.** A buyer interested in multiple active listings can justify a real blended
  discount; a single-item buyer should not be pushed into fake complexity.

Mechanically this starts in `MarketplaceState`: seller-visible listings and buyer threads feed portfolio
features (`active_buyers`, `best_offer_gap`, `listing_age`, `inventory_pressure`, `bundle_opportunity`)
into the same `KnobPolicy`. Each buyer still has a walled-off context; only the seller sees the portfolio.
For the learning loop, this should start as **truthful context over the active negotiation**, not a
giant synthetic marketplace. A background buyer only counts when there is a real thread, a recorded
replay, or an explicit fixture with its own hidden budget and behavior. Fake pressure is worse than
no pressure because it trains the seller to use leverage the product cannot honestly claim.

---

## 5. The knob doctrine (how the parametric `KnobPolicy` should behave)

The global `KnobPolicy` is the numeric strategy spine, not a bag of fixed constants. It keeps a
`base` knob set plus learned feature coefficients; each seller turn computes scale-free `Features`
and `resolve()` returns clamped per-turn `Knobs`.

| Feature rises → | `opening_anchor` | `concession_rate` | `accept_ratio` | `walkaway_patience` |
|---|---|---|---|---|
| **thin_margin** (little room above floor) | high | **low** — protect the wall, add value instead | **high** (only near-list closes) | shorter (walk sooner) |
| **fat_margin** (lots of room above floor) | stay high | slightly higher (room exists) — but make them *work* for it | slightly lower (room to take less than list) | normal |
| **reservation_gap ↑** (ask far above the observed buyer offer) | — | concede *toward the estimate*, never below floor; if est. < floor → hold/walk | — | shorter |
| **reservation_gap ≈ 0 / negative** (buyer at/over your ask) | — | small move or none | accept | — |
| **urgency ↑** (seller time pressure) | — | **faster, larger** steps | **lower** (accept sooner) | **shorter** (close, don't grind) |
| **turn_frac ↑** (later in the negotiation) | — | **shrinking increments** (Ackerman ladder); smallest near the floor | drift toward accept | approaching the wall |
| **active_buyers ↑** (same listing has parallel interest) | — | **lower** — do not bid against yourself | **higher** | longer |
| **best_offer_gap ↑** (best competing offer is still far below ask) | — | higher — weak backup interest is weaker BATNA than a near-ask backup | — | normal |
| **listing_age / inventory_pressure ↑** | — | **higher** — clear stale stock rationally | **lower** | shorter |
| **bundle_opportunity ↑** | — | modestly higher on blended terms | lower for the package | normal |

The implementation maps this directly: margin becomes `thin_margin` / `fat_margin`, the buyer's last
offer creates `reservation_gap`, the turn index creates `turn_frac`, and portfolio state contributes
parallel-buyer / inventory / bundle features. This is less hard-coded because the learner can move both
the base knobs and the coefficients that say when a feature should make the seller firmer or looser.

That still is not a full LLM planner. It is a bounded affine policy over a few doctrine-approved
levers. The language layer can sound human, but the offline learning claim is narrower: learn better
feature-conditioned prices, acceptance thresholds, and walk timing without crossing the red lines.

---

## 6. The situational lessons (cold-start prior for the buckets)

Per-bucket text lessons keyed by `(margin_band, buyer_type)` — seed `PolicyStore.buckets` with these
once the text channel is live, then let future lesson gates validate/demote them. `buyer_type` is
`unknown` until `K_OFFERS` offers exist.

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
product but **are NOT exercised by the current price-only engine** (§8) — they apply once
the agent negotiates a real listing.

| Situation | Doctrine | Ceiling (CONC) |
|---|---|---|
| **Asks free shipping** | Absorb shipping *instead of* a price cut — one, not both | < ~15% of value (CONC-005) |
| **Bundle (2+ items)** | Grow the pie: blended discount + combined shipping, conditional ("if you take both") | ~10–20% off singles (CONC-006) |
| **Parallel buyers / unpaid holds** | Keep live buyers warm; avoid open-ended unpaid holds; first firm commitment wins | no fake scarcity; no double-sale |
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

The current learning engine is a **price negotiation over a hidden reservation**. It exercises the
*spine* of the doctrine, not the whole thing. Don't mistake a clean curve for "the doctrine works."

| Doctrine element | In the current engine? |
|---|---|
| Anchor on target, shrinking conditional ladder, accept threshold, walk line | ✅ yes — `KnobPolicy.resolve(Features)` |
| Parallel-buyer / portfolio features | 🟡 scaffolded — `MarketplaceState` builds features and `scripts/play_multiple.py` exercises one listing with background buyer threads; next step is truthful context/replay in the main gate, not a fake full-market simulator |
| Probe-don't-disclose, buyer-type tactics | 🟡 partial — the lesson channel, if seeded |
| Never below floor, never leak floor | ✅ yes — reward + verifier |
| Never fabricate, never cave to pressure | 🟡 partial — verifier `honest`; pressure's analog is the **walk-away (§4.1)**; non-terminal walk mechanics are live, but tactical bluff handling still needs richer policies/verifier coverage |
| Bundles, shipping, loyalty, golden bridge | 🟡 partial — bundle feature exists; needs a real marketplace domain / multi-item policy |
| Ghosting, disputes/refunds, off-platform scam | ❌ no — needs real async + payment + post-sale |
| "Why isn't it selling" / listing-quality | ❌ no — needs listing + comp data |

---

## 9. How this plugs into the learning machinery

- **Cold-start prior:** §5 seeds `KnobPolicy.base` and the default coefficient signs; §6 is the intended
  seed for `PolicyStore.buckets` once text lessons are live. Today the offline gate validates numeric
  policy changes on held-out gate panels, then reports locked held-out transfer; lesson
  validation/demotion is future machinery.
- **Counterparty realism:** deterministic buyer families are the reproducible starting panel, not the
  final distribution. Reward-seeking LLM buyers, checkpoint/self-play drills, human games, and live
  marketplace threads should be added as separate evidence sources. A candidate should be considered
  stronger only when it transfers across that panel, not merely because it beat its current training
  opponent.
- **What learns offline:** proposal generation can nudge one base knob, one feature coefficient, or
  the urgency toggle at a time. The report shows final base knobs and `learned coeffs`, so coefficient
  drift is visible instead of hidden inside "the strategy got better."
- **The red lines (§4 NEVERs) are guardrails, not learnable behavior:** the floor is the reward wall;
  floor-leak / fabrication are verifier checks. The learner tunes *how to win within* the lines; it
  must never learn to cross them — that's what `viol=0` protects.
- **`skill` is the scoreboard** (§2): the doctrine optimizes for extracting true willingness, which is
  exactly what the held-out `skill` curve measures.
- **The honest line:** the agent never invents facts, so "justify with comps" only works when real
  comps are supplied. In the sim there are no comps — that part of the doctrine activates with the eBay
  connector. Until then, the price-core doctrine (§5) is what's live.

---

## 10. Operational prompts (the doctrine, compressed for the agents)

The seller/buyer **target system prompts** are this doctrine in miniature — short enough to ride on
every turn, with situational depth eventually coming from per-bucket lessons (§6) injected via
`@agent.instructions`. The current offline engine does not read lesson text, and the live harness only
uses a slimmer prompt/context path. Keep the structured output minimal (a spoken line + an optional
price + accept/walk); the *tactics* live in the language the model generates, governed by these.

**Seller (system prompt):**
> You are a sharp, warm marketplace seller in a multi-turn negotiation. Close at the highest price the
> buyer will truly pay, in reasonable time — and walk rather than take a bad deal.
> - You have a SECRET FLOOR: never sell below it, never reveal or hint at it.
> - Anchor on your target with a real reason; hold price and add value before conceding; concede on a
>   shrinking, conditional ladder — never equal steps, never for free.
> - A buyer's walk-away is usually a bluff: don't panic-concede or cross your floor to save the deal.
>   Stay calm — either let them go (you can relist) or make ONE final conditional offer with a small
>   face-saving extra, then stop chasing.
> - Lead with empathy, keep replies short and human, never fabricate comps or scarcity, and don't cave
>   to pressure or threats.

**Buyer (system prompt — the self-play counterparty):**
> You are a shrewd, friendly buyer in a multi-turn negotiation. Pay as little as possible — and walk
> rather than overpay.
> - You have a HIDDEN MAX BUDGET: never offer or accept above it, never reveal it.
> - Open below budget with a reason; concede slowly and conditionally; make the seller justify every
>   dollar.
> - Use pressure honestly — a credible walk-away, a deadline, take-it-or-leave-it — but a real walk is
>   your strongest lever; don't bluff yourself into a deal you'd regret.
> - Keep replies short and human, never fabricate, and concede only for legitimate reasons.

In the target runtime, each turn also gets the **live context** (the standing price, the other side's
last move, the public transcript, and this bucket's promoted lessons) via `@agent.instructions`. The
system prompt is the constant doctrine; the instructions are the situation.
