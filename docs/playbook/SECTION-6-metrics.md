# Section 6 — Metrics for Success (NOT just highest price)

## Changelog (v2)
- **New primary/north-star metric (§6.0):** "% of completed sales that meet the seller's *stated* objective" — measured **relative to the seller's per-listing objective**, not a global "highest price" (CONVENTIONS §G).
- **Added technique-lift** as a first-class validity metric (agent-with-techniques vs. naive-baseline seller on matched buyer seeds). See §6.0 and EVAL-PLAN.md.
- **Added self-score calibration** (step-5 self-check score vs. actual outcome) — guards the sycophantic-self-grading failure; ties to the loop fix in SECTION-5 / CONVENTIONS §D steps 5–6.
- **Added bound-compliance / guardrail metrics** (never-breach-walkaway %, guardrail catch-rate) as explicit hard floors (§6.0).
- Existing 14-metric table (§6.2) preserved unchanged; added an **objective_weight mapping** note (§6.2.1) so price-weighted vs. speed-weighted sellers read the right metrics.

## 6.0 Primary metric (north-star) and hard floors
**North-star — Stated-objective hit rate.** % of completed sales that meet the **seller's stated objective for that listing**:
- **Price-weighted sellers** (`objective_weight` high): sale closes **≥ `target_price`**.
- **Speed-weighted sellers** (`objective_weight` low): sale closes **within the `urgency` window** (`gone_today` / `this_week` / `no_rush`).
- **Always, for every seller:** **never below `walkaway_price`** (hard bound, CONVENTIONS §A).

> **Measured RELATIVE to the objective, not absolutely.** Because the objective is **seller-set per listing** (the price↔speed `objective_weight` slider, §E mapping), success is *not* a global "highest price." A fast close at `target` for a `gone_today` seller is a full win; the same outcome for a max-price seller may be a miss. This is the single number the §5 reward and the eval rubric optimize against — but it is reported *with* the §6.1 three-axis band, never alone.

**Technique-lift (validity, not just safety).** Outcome of **agent-with-techniques vs. naive-baseline seller on matched buyer seeds** (same simulated-buyer persona + hidden WTP + seed, CONVENTIONS §F). This is how we **prove the playbook actually works**, not merely that it stays safe: lift on stated-objective hit rate, final-price-vs-ask, and time-to-sale at equal-or-better trust metrics. Full A/B design and significance handling: **EVAL-PLAN.md**.

**Self-score calibration (anti-sycophancy).** Agreement between the **step-5 self-check score** (the pre-send FILTER, CONVENTIONS §D step 5) and the **actual outcome**. The self-score is a gate, **never** the learning signal; this metric exists to detect drift where the model grades its own drafts optimistically (the sycophantic-self-grading failure). Low calibration → distrust the self-score and lean on edits+outcomes (ties to the loop fix in SECTION-5, CONVENTIONS §D step 6). Measured as correlation / agreement between self-score and realized outcome on held-out transcripts.

**Bound-compliance & guardrails (hard floors — never trade-offs).**
- **Walkaway-compliance:** % of conversations that **never** breach `walkaway_price`. **Target ≈ 100%.** Any breach is a defect, not a tuning knob.
- **Guardrail catch-rate:** % of injected violations **caught and blocked** — off-platform/payment-change requests, fabricated scarcity/comps/authority, and below-floor accepts (CONVENTIONS §B ESCALATE, §D step 4–5). Target high catch-rate; watch false-positive rate on legit buyers as the only acceptable failure mode.

> **Source note:** The negotiation logic these metrics measure is source-supported. The specific metric set, formulas, and "failure mode if over-optimized" framing are **synthesized** for this product. Targets are placeholders to be tuned from real data (§8).

> The copilot's job is **not** to maximize sale price. A price-only optimizer learns to manipulate, burns trust, kills repeat business, and triggers disputes — all of which a casual seller pays for later. Success is a *balance* of three things the books care about: **profit**, **trust/relationship**, and **speed**, all in service of the seller's stated objective (§6.0). This dashboard makes that balance explicit and gives the §5 learning loop its reward terms.

## 6.1 The three axes
Every metric maps to one of three axes. A healthy seller is good on all three; over-optimizing any one degrades the others.

- **💰 Profit** — capture fair value (the books' "claiming value": PRIN-009 anchor, PRIN-007 ladder, PRIN-010 BATNA).
- **🤝 Trust / relationship** — preserve goodwill, ratings, repeat business (PRIN-024 generous close, PRIN-031 liking, GTY fairness, DC acknowledge).
- **⚡ Speed** — convert and clear inventory (PRIN-038 timing, PRIN-025 commitment, anti-ghosting PRIN-015).

## 6.2 Metric table

| # | Metric | Axis | Why it matters | How measured | Failure mode if over-optimized |
|---|---|---|---|---|---|
| 1 | **Sell-through rate** | ⚡/💰 | Unsold inventory is dead capital; the core casual-seller goal is *clearing closets*, not winning haggles | sold listings ÷ total active+sold over a window | Fire-sale everything: dump at any price, destroying margin and signalling weak BATNA (violates PRIN-010, COACH-002) |
| 2 | **Final-price-vs-ask ratio** | 💰 | Core margin-capture signal; feeds concession tuning (CONC-xxx) | mean(final paid ÷ list price) | Holding out for full ask → low sell-through, ghosting, aging listings; over-anchoring past the giggle test (PRIN-009 guardrail) |
| 3 | **Time-to-sale** | ⚡ | Faster turns = more velocity, fresher feed (PRIN-038); long tails tie up cash | first-contact (or list) → paid, median | Rushing every close → panic discounts, accepting first lowball, skipping the value-add (COACH-021) |
| 4 | **Margin-vs-floor (floor respected)** | 💰 | Did we stay above the seller's real walk-away? The single most important profit guardrail | (final price − floor) ÷ (goal − floor); count sub-floor sales | Treating floor as target → leaves money on table; OR if "never sell below floor" is rigid, kills sales of aging stock (CONC-008) |
| 5 | **Buyer-satisfaction / repeat-rate** | 🤝 | Repeat buyers and followers are the cheapest future sales; loyalty compounds (PRIN-027, INTENT-011) | rating left, % buyers who return / follow | Padding satisfaction by always caving → trains buyers to expect deep discounts (PRIN-045 accommodator trap) |
| 6 | **Dispute / return rate** | 🤝 | Disputes cost money, time, and rating; usually caused by expectation gaps, not price | cases opened ÷ sales | Avoiding disputes by panic-refunding everything → exploited by extortionists (COACH-018, COACH-024); or by over-disclosing into no-sale |
| 7 | **Ghosting-recovery rate** | ⚡/🤝 | Stalled buyers are recoverable revenue; tests PRIN-015 / OBJ-stalling-ghosting | re-engaged & closed ÷ ghosted threads | Nagging into reactance (COACH-014): more nudges, fewer sales, worse vibe — recovery via pressure backfires |
| 8 | **Discount discipline** | 💰 | How often the system stayed inside CONC guidance vs. over-conceded; proxy for "are we leaking margin?" | % moves within CONC thresholds; mean concession size vs. ladder | Rigid discipline → misses legitimate fair-range splits (CONC-002) and aging-stock flexibility (CONC-008); reads as inflexible |
| 9 | **Seller-edit rate** | (quality proxy) | How often the seller rewrote the suggestion = direct suggestion-quality signal feeding §5 | % suggestions sent with heavy edits / rejected; mean edit-distance | Optimizing for low edits → blandly safe, do-nothing suggestions the seller accepts but that don't actually advance the deal |
| 10 | **Escalation rate** | 🤝 | How often threads turn hostile / route to balcony (PRIN-019) or safety; rising = tone problems | threads hitting rude/aggressive/bully handling ÷ total | Suppressing escalation by always conceding to angry buyers → rewards bullying (CONC-010, COACH-018) |
| 11 | **Off-platform / scam-avoidance** | 🤝/safety | Hard safety metric: scam attempts must be *caught*, never negotiated (PRIN-044, INTENT-009) | scam/off-platform signals detected & declined ÷ detected; $ loss to scams (target 0) | None acceptable — this is a hard floor, not a tradeoff. Over-flagging legit buyers is the only failure mode to watch (false-positive rate) |
| 12 | **Message-to-sale conversion** | ⚡/💰 | Top-of-funnel efficiency: of buyers who message, how many buy? Tests reply quality end-to-end | sales ÷ unique buyers who opened a thread | Maximizing conversion → high-pressure closing, ignoring fit/trust, more returns downstream (the dispute rate is the counterweight) |
| 13 | **Bundle / pie-growth rate** | 💰/🤝 | Captures integrative value (PRIN-006, INTENT-006) — more units moved at better blended margin, win-win | % multi-item sales; mean items per sale | Forcing bundles on single-item buyers → friction, abandoned carts (PRIN-006 when_not_to_use) |
| 14 | **Trust-preserved composite** | 🤝 | The relationship counterweight in the §5 reward; rolls up disputes + reviews + repeats + non-ghosting | weighted index of #5–#7, #10 | If weighted too high vs. profit → the system becomes a pushover; the *balance* between this and #2/#4 is the product's core tuning knob |

### 6.2.1 Which metrics map to which `objective_weight`
The 14 metrics above are universal, but **price-weighted and speed-weighted sellers read different ones as primary** (the §E objective→behavior mapping in action). The north-star (§6.0) collapses these into one objective-relative number; this table is for diagnostics.

| `objective_weight` setting | Reads as primary | De-prioritized (still gated, never breached) |
|---|---|---|
| **Price-weighted** (high) | #2 final-price-vs-ask, #4 margin-vs-floor, #8 discount discipline, #13 bundle/pie-growth | #1 sell-through, #3 time-to-sale (tolerated longer) |
| **Speed-weighted** (low) | #1 sell-through, #3 time-to-sale, #7 ghosting-recovery, #12 message-to-sale | #2 final-price-vs-ask (accept lower % of list, per §E accept threshold) |
| **Both, always (hard floors)** | #4 sub-floor count (→ §6.0 walkaway-compliance), #11 off-platform/scam-avoidance (→ §6.0 guardrail catch-rate) | — never traded off for either objective |

Trust metrics (#5, #6, #10, #14) gate *both* settings — neither speed nor price may be bought by burning trust.

## 6.3 The balance, stated plainly
- **Never report a single number.** A "win" is a green band across all three axes, not a high price.
- **Profit metrics (#2, #4, #8, #13) are gated by trust metrics (#5, #6, #10, #14).** The §5 reward function encodes exactly this: margin terms are net of dispute/ghost/edit penalties.
- **Speed (#1, #3, #7, #12) is the tie-breaker, not the goal** — a casual seller wants their stuff *gone at a fair price with no drama*, which is all three axes at once.
- **The hard floors are never tradeoffs:** off-platform/scam-avoidance (#11 → §6.0 guardrail catch-rate) and never-below-floor (#4 sub-floor count → §6.0 walkaway-compliance, target ≈ 100%). Everything else is balanced; these are absolute.
- **The one knob that defines the product's personality** is the weight of #14 (trust composite) against #2/#4 (margin). Ship a sensible default; expose it to the seller as a "firm ↔ friendly" dial (PRIN-027 made tangible) rather than letting it drift inside the optimizer.
