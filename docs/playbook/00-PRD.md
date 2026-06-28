# 00 — Product Requirements Document: "Gambit"

> **Doc type:** Lead handoff PRD for the dev team. **Status:** v1, ready to build against.
> **Conforms to:** [`CONVENTIONS.md`](CONVENTIONS.md) (v2) — the single source of truth. If anything here conflicts with CONVENTIONS, **CONVENTIONS wins.**
> **Asset IDs** (`PRIN-` / `INTENT-` / `OBJ-` / `CONC-` / `COACH-`) are stable keys from [`assets/json/`](assets/json/). Cite them; do not invent new ones.
> **Product in one line:** Gambit is a *self-improving selling copilot* for P2P marketplaces. MVP = **general items**, **simulated buyer**, **hybrid autonomy**. The differentiator vs. a chatbot wrapper is the **6-step loop** (§3).

---

## 1. Problem & opportunity

Casual sellers on peer-to-peer marketplaces (Depop, Vinted, Poshmark, eBay) are not negotiators. They list an item to get it out of the closet, and then one of three things goes wrong the moment a buyer messages:

1. **They under-negotiate.** They name their lowest price first, over-explain, and have no floor in mind — so any offer that "feels okay" gets accepted (COACH-001, COACH-005).
2. **They over-discount.** Conflict-averse by default, they cave to avoid confrontation, reflexively split the difference, or panic-drop the price when the *listing* — not the price — was the real problem (COACH-003, COACH-004, COACH-006).
3. **They ghost / get ghosted.** Threads stall, the seller doesn't know how to re-engage without sounding desperate, and the item ages out (COACH-021, COACH-022; INTENT-005).

The underlying truth (Section 8): **the user often hates haggling, wants it over, and will over-cave.** No source book models this seller — they all assume a motivated negotiator who wants to get good. That gap is the opportunity.

**The opportunity:** a *bounded, learning* copilot that does the negotiating the seller dreads — anchored on real comps, never going below a seller-set floor, conceding on a disciplined ladder — and gets better at it per category over time. "Bounded" is the trust unlock (the AI can never sell below your floor); "learning" is the moat (it tunes to outcomes, not vibes). This is the stance the whole corpus converges on (Section 9.a): **win the deal by making the buyer feel safe, understood, and fairly treated — and by setting up well before the haggle — never by manipulating.**

---

## 2. Users

### 2.1 Primary user — the casual seller

| Attribute | Description |
|---|---|
| **Who** | A non-professional reseller clearing a closet/shelf. Lists general items (clothing, electronics, homeware, collectibles). Low-dollar, mostly one-shot deals. |
| **Mindset** | "I just want this gone." Conflict-averse, time-poor, not trying to become a negotiator. The time cost of a haggle can exceed the gap being haggled over (Section 8.6). |
| **Core jobs** | (1) Get a defensible listing up fast. (2) Not get walked over on price. (3) Not have to think about every buyer reply. (4) Actually close. |
| **Pain we remove** | The dread of the negotiation itself — and the silent leakage from caving, mis-splitting, and mistimed markdowns. |
| **Explicitly NOT our user (MVP)** | Power-resellers / boutiques with their own pricing ops; buyers (we build a *seller's* copilot). |

### 2.2 Voice / brand persona (CONVENTIONS §C)

**Friendly, respectful, gen-z, still professional.** Sounds like a real person — warm, lightly casual, contractions, at most one emoji where natural. No corporate stiffness, no forced slang/cringe, no over-apologizing.

- **Re-skin rule (load-bearing):** *tactics decide WHAT to say; voice decides HOW it reads.* Every template passes through the voice layer **without losing the move.**
  - Accusation audit, stiff: *"You're probably going to think I'm being stubborn..."*
  - Accusation audit, brand voice: *"you're prob thinking i'm being stubborn lol — fair. honestly i've already got it priced under what these go for, so i can't do $15. but tell me what works for you?"*
- **Override:** when the buyer is rude/accusatory, the Difficult-Conversations calm layer **outranks** casualness — stay warm + steady, drop the jokes. Never manipulate, even in casual tone (Influence guardrails hold).
- **MVP:** one consistent voice. Buyer/category-adaptive voice is **v2.**

---

## 3. Product thesis — the 6-step loop (the centerpiece)

A chatbot wrapper takes a buyer message and emits a reply. That's a function call. **Gambit is a system, not a wrapper** because it carries *state*, *constraints*, and a *learning signal* across the whole conversation. The difference lives in the 6-step loop (CONVENTIONS §D), which is the architecture spine of the product.

The two structural facts that make it a system rather than a wrapper:

- **Strategy is conversation-level state, not a per-message reroll** (step 3). The copilot commits to a strategy and executes it across turns; it does not re-decide who the buyer is on every message.
- **The learning signal is ground truth (edits + outcomes), not the model's own self-grade** (steps 5 & 6). The self-check is a *gate*, never the teacher — LLM self-grading is unreliable and sycophantic.

```
                          GAMBIT 6-STEP AGENT LOOP
                       (system, not wrapper — carries state)

  ┌──────────────────────────────────────────────────────────────────────┐
  │  PER-CONVERSATION STATE  (set once, persists across turns)             │
  │  • Seller input schema §A: list / target / walkaway, urgency, weight   │
  │  • Brand voice §C                                                      │
  │  • Committed strategy (PRIN + CONC plan)  ◄── written in step 3, reused │
  └──────────────────────────────────────────────────────────────────────┘
                                    │
   buyer message ───────────────────┘
        │
        ▼
  ┌─ 1. UNDERSTAND CONSTRAINTS ───────────────────────────────────────────┐
  │   load seller schema (§A) + voice (§C). [done at listing-approval time] │
  └────────────────────────────────────────────────────────────────────────┘
        │
        ▼
  ┌─ 2. CLASSIFY INTENT ──────────────────────────────────────────────────┐
  │   INTENT-xxx from message + behavioral signals → emit CONFIDENCE score  │
  └────────────────────────────────────────────────────────────────────────┘
        │
        ▼
  ┌─ 3. PICK STRATEGY  (the "system" move) ───────────────────────────────┐
  │   select PRIN-xxx + CONC-xxx plan, conditioned on intent ×              │
  │   objective_weight × urgency (§E).                                      │
  │   *** PERSIST as conversation-level strategy state — NOT re-rolled. *** │
  └────────────────────────────────────────────────────────────────────────┘
        │
        ▼
  ┌─ 4. GENERATE GROUNDED REPLY ──────────────────────────────────────────┐
  │   apply OBJ-xxx handlers + voice layer. Grounded strictly in seller     │
  │   constraints + comps. NO fabricated scarcity / comps / authority.      │
  └────────────────────────────────────────────────────────────────────────┘
        │
        ▼
  ┌─ 5. SELF-CHECK = PRE-SEND FILTER (a gate, NOT the teacher) ────────────┐
  │   within bounds? on-voice? rule/guardrail violation? honest?           │
  │   fail → regenerate or ESCALATE.  self-score is logged for calibration  │
  │   only — it is NEVER the learning signal.                               │
  └────────────────────────────────────────────────────────────────────────┘
        │  pass
        ▼
   ┌────────────────────┐   AUTO-SEND (in bounds)
   │ HYBRID ROUTING §B  │── HOLD (seller edits → approve → send)  ◄─┐
   └────────────────────┘   ESCALATE (never auto-send)              │
        │                                                           │
        ▼                                          seller EDITS = primary training signal
  ┌─ 6. LEARN ────────────────────────────────────────────────────────────┐
  │   log outcome + seller edits + buyer response.                          │
  │   EDITS + OUTCOMES are ground truth → update playbook weights.          │
  │   self-score recorded ONLY to track its calibration vs. outcomes.  ─────┘
  └────────────────────────────────────────────────────────────────────────┘
```

> A wrapper would stop at step 4. Gambit's value is in 1, 3, 5, and 6 — the parts that hold state and close the loop.

---

## 4. Scope & non-goals (CONVENTIONS §H)

### 4.1 In scope (MVP)

| In | Note |
|---|---|
| **General items** | Not fashion-only; clothing, electronics, homeware, collectibles. |
| **Simulated buyer** | LLM-driven buyer harness is the eval substrate (CONVENTIONS §F). No real platform in MVP. |
| **Hybrid autonomy** | Auto-send / hold / escalate routing (§B). |
| **The 6-step loop** | The full spine (§3). |
| **Learning from edits + outcomes** | Closed loop; edits are the primary signal. |

### 4.2 Deferred (separate tracks — do not build in MVP)

| Deferred | Why / where it goes |
|---|---|
| **Scam / safety taxonomy** | Off-book synthesized overlay (INTENT-009, OBJ-off-platform-request, PRIN-044). The books' "golden bridge" logic is *actively wrong* for scammers — this needs its own research track, not MVP shipping. In MVP, scam-shaped signals **escalate** (never negotiated), but we do not claim a precision/recall-validated detector. |
| **Real marketplace integration** | See feasibility constraint below. |
| **Payments** | Out of scope entirely for MVP. |

### 4.3 Feasibility constraint (dev must know this before designing the adapter)

- **Depop / Vinted / Poshmark have no public messaging or offer APIs.** Automating outbound messages or offers on them means scraping or driving the UI → **ToS violation and ban risk.** Do **not** build against them.
- **eBay is the only real-integration candidate.** It exposes Best Offer + Negotiation APIs and a sold-comps feed, and is the natural **post-MVP** target for general items.
- **The platform adapter is an *interface*, not an implementation, in MVP.** The simulated buyer (CONVENTIONS §F) sits behind that interface so the real eBay adapter drops in later.
- **Comps are an external data dependency** (Section 8.b). Where no comp feed exists, the copilot must pivot to interests/options rather than fabricate (PRIN-003 `when_not_to_use`).

---

## 5. Core user flows

### 5.1 Listing-review & approval flow (three-price model — CONVENTIONS §A)

This is **step 1 of the loop** (understand constraints). Nothing goes live until the seller approves.

1. Seller starts a listing (title, photos, condition).
2. AI proposes a draft listing + a **three-price model** from comps:
   - `list_price` — **public anchor**, set high-but-justifiable (PRIN-009).
   - `target_price` — ideal outcome the AI steers toward.
   - `walkaway_price` — reservation / floor. **AI never goes below. Hard bound.**
3. Seller supplies constraints (the **seller input schema**):

   | Field | Meaning | Notes |
   |---|---|---|
   | `list_price` | Public anchor (high-but-justifiable) | AI proposes from comps; seller approves |
   | `target_price` | Ideal outcome AI steers toward | |
   | `walkaway_price` | Floor — **hard bound, never crossed** | |
   | `urgency` | `gone_today` \| `this_week` \| `no_rush` | Pins the speed weight; compresses concession/relist timelines |
   | `objective_weight` | Price ↔ Speed slider (0 = fastest … 100 = max price) | Drives concession aggressiveness (§E) |
   | `will_ship`, `ship_pays`, `returns` | Logistics | |
   | `bundle_ok` + rules | Secondary for general items | |
   | `condition_notes` | Known flaws for honest disclosure | Feeds accusation-audit / trust plays |

4. AI enforces the **invariant** `walkaway_price ≤ target_price ≤ list_price`. If the seller sets `list = target`, it **warns**: they've pre-conceded the whole range (anchoring principle PRIN-009).
5. Seller approves → listing goes live (against the simulated-buyer harness in MVP).

### 5.2 Negotiation flow under hybrid autonomy (CONVENTIONS §B)

Every outbound is AI-drafted. The branch decides whether it auto-sends, holds, or escalates. **Seller edits to held drafts are the primary training signal.**

1. Buyer message arrives.
2. Loop runs steps 2→5 (classify → strategy → generate → self-check).
3. Routing tier is selected:

   | Tier | Triggers (examples) | Behavior |
   |---|---|---|
   | **AUTO-SEND** (within bounds) | greeting/rapport; "is it available?" (low-signal, INTENT-010); factual Q answerable from listing; **accept offer ≥ target** (auto-lock); confirm already-approved logistics | Sent automatically. Logged. |
   | **HOLD FOR APPROVAL** | any counteroffer / price move; **any concession (any discount)**; objection handling (OBJ-*); ghosting re-engagement; high-touch tactics (accusation audit, "that's right" summary) | AI drafts → seller edits/approves → sent. |
   | **ESCALATE** (never auto-send) | off-platform / payment-change; accusation / dispute / refund; **offer < walkaway**; intent-confidence below threshold | Handed to seller; AI may draft a *safe holding reply* but does **not** send. |

4. Sent (or approved-then-sent, or escalated) → outcome + buyer response logged for step 6.

### 5.3 Learning flow (steps 5 & 6)

1. Every draft gets a self-check **self-score** (gate result + numeric).
2. On HOLD: the seller's **edit diff** (original draft vs. what they actually sent) is captured.
3. On any tier: **outcome** (sold / price-vs-target / time-to-sale / ghosted / disputed) + buyer response are logged.
4. **Edits + outcomes update playbook weights** (which PRIN/CONC/OBJ fire, and the synthesized concession magnitudes per category).
5. The self-score is recorded **only** to track its *calibration* against outcomes — never as the learning signal.

---

## 6. Functional requirements

Numbered, concrete, testable. Each maps to a loop step and/or asset IDs.

### Listing generation & three-price capture (loop step 1)

| ID | Requirement | Refs |
|---|---|---|
| **FR-1** | The system SHALL generate a draft listing (title, description, condition framing) grounded only in seller-provided facts + comps, and SHALL surface it for seller approval before anything is published. | PRIN-037, COACH-023 |
| **FR-2** | The system SHALL propose `list_price`, `target_price`, `walkaway_price` from comps, with `list_price` set high-but-defensible. Each proposed price SHALL be accompanied by its comp justification. | PRIN-003, PRIN-009 |
| **FR-3** | The system SHALL capture the full seller input schema (§A): the three prices, `urgency`, `objective_weight`, `will_ship`/`ship_pays`/`returns`, `bundle_ok`+rules, `condition_notes`. | CONVENTIONS §A |
| **FR-4** | The system SHALL enforce the invariant `walkaway_price ≤ target_price ≤ list_price` and SHALL reject saves that violate it. | CONVENTIONS §A |
| **FR-5** | If `list_price == target_price`, the system SHALL warn the seller that they have pre-conceded the entire range (no hard block). | PRIN-009, COACH-002 |
| **FR-6** | If no comp data is available for the item, the system SHALL NOT fabricate a comp range; it SHALL prompt the seller for a price and pivot price-justification to interests/options. | PRIN-003 (`when_not_to_use`), COACH-013 |

### Intent classification with confidence (loop step 2)

| ID | Requirement | Refs |
|---|---|---|
| **FR-7** | On each inbound buyer message, the system SHALL classify intent to one INTENT-xxx label using message text + available behavioral signals, and SHALL emit a numeric **confidence score** with the label. | INTENT-001…014 |
| **FR-8** | When confidence is below the configured threshold, the system SHALL route to ESCALATE (never auto-send) and surface the ambiguity to the seller. | CONVENTIONS §B; INTENT-014 |
| **FR-9** | The system SHALL only use behavioral signals (likes/saves/watchers, days-on-market, latency, repeat-buyer status) when it can actually read them; it SHALL NOT assert a count it cannot verify. | PRIN-011, PRIN-029, COACH-013; Section 8.b |

### Strategy selection with conversation state (loop step 3)

| ID | Requirement | Refs |
|---|---|---|
| **FR-10** | The system SHALL select a strategy — a set of PRIN-xxx + a CONC-xxx concession plan — conditioned on `intent × objective_weight × urgency`. | CONVENTIONS §D.3, §E |
| **FR-11** | The selected strategy SHALL be **persisted as conversation-level state** and reused across turns. The system SHALL NOT re-roll strategy on every message; it MAY revise strategy only on a material intent change (with confidence above threshold). | CONVENTIONS §D.3 |
| **FR-12** | `objective_weight` and `urgency` SHALL modulate CONC defaults per §E: opening counter position, concession increment size/cadence, accept threshold, and relist/price-drop cadence. | CONVENTIONS §E; CONC-001…012 |

### Grounded reply generation + voice layer (loop step 4)

| ID | Requirement | Refs |
|---|---|---|
| **FR-13** | The system SHALL generate the reply by applying the matched OBJ-xxx handler(s) and selected principles, grounded strictly in seller constraints + comps. | OBJ-* ; PRIN-* |
| **FR-14** | Every reply SHALL pass through the **voice layer** (§C) without losing the underlying tactic (re-skin rule). One consistent voice in MVP. | CONVENTIONS §C |
| **FR-15** | The system SHALL NOT fabricate scarcity, social proof, comps, or authority/authenticity claims in any reply. | PRIN-029, PRIN-030, COACH-013 |
| **FR-16** | On rude/accusatory buyer messages, the system SHALL apply the calm (Difficult-Conversations) layer, overriding casualness while staying warm and non-manipulative. | PRIN-019, PRIN-020, COACH-008, COACH-009; OBJ-rude-aggressive |

### Hybrid routing — auto-send / hold / escalate (loop step 5 → action)

| ID | Requirement | Refs |
|---|---|---|
| **FR-17** | The system SHALL route every drafted outbound to exactly one of AUTO-SEND / HOLD / ESCALATE per the §B tier table. | CONVENTIONS §B |
| **FR-18** | The system SHALL auto-accept and lock an offer `≥ target_price`; it SHALL HOLD any concession or price move; it SHALL ESCALATE any offer `< walkaway_price`, off-platform/payment-change request, or dispute/refund/accusation. | CONVENTIONS §B; PRIN-044 |
| **FR-19** | On HOLD, the system SHALL present the draft for seller edit/approval and SHALL capture the **edit diff** (draft vs. sent) as the primary training signal. | CONVENTIONS §B, §D.6 |
| **FR-20** | On ESCALATE, the system MAY draft a safe holding reply but SHALL NOT send it automatically under any circumstance. | CONVENTIONS §B |

### Self-check gate (loop step 5)

| ID | Requirement | Refs |
|---|---|---|
| **FR-21** | Before any send/hold, the system SHALL run a self-check gate on the draft: (a) within bounds? (b) on-voice? (c) rule/guardrail violation? (d) honest/no fabrication? | CONVENTIONS §D.5 |
| **FR-22** | On gate failure, the system SHALL regenerate or ESCALATE; it SHALL NOT send a draft that fails the gate. | CONVENTIONS §D.5 |
| **FR-23** | The self-check self-score SHALL be used **only** as a pre-send filter and SHALL NOT be used as the learning signal. It SHALL be logged for calibration tracking against actual outcomes. | CONVENTIONS §D.5, §D.6, §G |

### Logging for learning (loop step 6)

| ID | Requirement | Refs |
|---|---|---|
| **FR-24** | The system SHALL log, per turn: classified intent + confidence, selected strategy (PRIN/CONC), generated draft, self-score, routing tier, seller edit diff (if HOLD), the sent message, and the subsequent buyer response. | CONVENTIONS §D.6 |
| **FR-25** | The system SHALL log per-conversation outcome: sold/not, final price vs. target/walkaway, time-to-sale, ghosted/disputed flags. | CONVENTIONS §G; Section 6 metrics |
| **FR-26** | Edits + outcomes SHALL be the inputs that update playbook weights (PRIN/CONC/OBJ selection + concession magnitudes per category). Self-score SHALL NOT update weights. | CONVENTIONS §D.6; Section 8.c #2 |

---

## 7. Non-functional requirements

| ID | Requirement | Refs |
|---|---|---|
| **NFR-1 (Honesty / no fabrication)** | No outbound may contain fabricated scarcity, social proof, comps, or authenticity/authority claims. This is a hard guardrail enforced at the self-check gate, not a stylistic preference. | Influence guardrails; COACH-013; PRIN-029/030 |
| **NFR-2 (Human-in-the-loop)** | The seller approves every HOLD and every ESCALATE. AUTO-SEND is permitted only strictly within the §B bounds. The seller can always intervene. | CONVENTIONS §B; Section 9.b guardrail #10 |
| **NFR-3 (Auditability)** | Every outbound SHALL be traceable to: the intent + confidence, the strategy that produced it, the self-score, the routing decision, and (if held) the seller edit. Logs are the audit trail and the training set. | FR-24 |
| **NFR-4 (Chat latency)** | Draft generation for a live haggle SHALL feel conversational — target a draft within a few seconds of the buyer message so AUTO-SEND replies don't read as suspiciously instant or laggy. (Set a concrete p95 target during build; see open question Q5.) | — |
| **NFR-5 (Cold-start behavior)** | Before per-category learning has data, the system SHALL run on the synthesized CONC defaults and labeled them as defaults, NOT as tuned values. It SHALL behave safely (never below walkaway, honesty gate on) from turn one and improve as edits/outcomes accumulate. | Section 8.a #4, 8.c #2 |
| **NFR-6 (Determinism for eval)** | The simulated-buyer harness SHALL be seed-deterministic so technique-lift A/B and regressions are reproducible. | CONVENTIONS §F |
| **NFR-7 (Calm-layer precedence)** | The Difficult-Conversations calm layer SHALL outrank brand casualness whenever the buyer is rude/accusatory. | CONVENTIONS §C; COACH-008/009 |

---

## 8. Success criteria / north-star

**North-star (CONVENTIONS §G):** **% of completed sales that meet the seller's stated objective** — i.e., hit ≥ `target_price` when price-weighted, or sold within the urgency window when speed-weighted — and **never** below `walkaway_price`.

Supplemented by two diagnostic metrics:
- **Technique-lift** — performance vs. a naive-baseline seller on the same buyer seed (CONVENTIONS §F).
- **Self-score calibration** — step-5 self-score vs. actual outcome (§D.6).

> Full metric definitions, instrumentation, and targets live in **[Section 6 — Metrics](SECTION-6-metrics.md)**. This PRD does not redefine them; it points at that doc as the source.

---

## 9. Risks & open questions

### 9.1 Lead risk — bounding ≠ value (the transfer-risk nuance)

Bounding the AI by `walkaway_price` guarantees **financial safety** (the seller cannot be sold below their floor). It is **NOT** evidence that the negotiation techniques add any value. These are two separate claims and must not be conflated:

- *Safety* is a property of the bound (FR-18). It holds trivially.
- *Value* is the foundational, unproven bet (Section 8.c #1, 9.d #1): that high-stakes/in-person/professional book tactics transfer to casual, low-dollar, async resale at all.

**Implication for the dev team:** the eval plan must prove **technique LIFT** — agent-with-techniques vs. naive-baseline on the *same* buyer seed (CONVENTIONS §F) — measured on conversion, price-vs-ask, and dispute rate. "We never went below walkaway" is necessary but says nothing about whether the playbook works. Do not let safety metrics stand in for value metrics.

### 9.2 Other key risks

| Risk | Detail | Mitigation / owner |
|---|---|---|
| **Deferred safety** | Scam/off-platform handling is a synthesized, off-book overlay (INTENT-009, PRIN-044) with no validated precision/recall. The books' golden-bridge logic is *actively wrong* for scammers. | MVP **escalates** scam-shaped signals, never negotiates them. A real detector is a separate research track (§4.2). Worst downside if wrong (Section 9.d). |
| **Comps data dependency** | Anchor (PRIN-009), price justification (PRIN-003), and the entire concession floor depend on *real* recent-sold comps — an external data dependency not present in MVP's simulated environment. | FR-6 forbids fabrication; pivot to interests/options when comps are absent. eBay sold-comps feed is the post-MVP source (§4.3). |
| **Synthesized concession magnitudes** | Every CONC discount % is a guess, likely category-dependent. | Treat as tunables; learning loop (FR-26) adjusts per category. NFR-5 cold-start. |
| **Empathy moves in tone-stripped chat** | Mirroring/labeling (PRIN-012/013/016) may read scripted in terse async DMs. | Measure seller-edit rate + conversion on label-bearing vs. plain replies (Section 8.c #3). |
| **Buyers resenting an AI** | If a buyer senses they're negotiating against a script, rapport/liking collapses and reactance spikes. | Disclosure A/B in eval; watch ghosting/escalation (Section 8.c #5). |

### 9.3 Open questions for the dev team

- **Q1.** Intent-confidence **threshold** for the ESCALATE-on-low-confidence rule (FR-8) — pick a starting value and make it a tunable.
- **Q2.** What exactly is the **"naive-baseline seller"** in the technique-lift A/B? Needs a precise definition before the eval plan can run (belongs in EVAL-PLAN.md).
- **Q3.** **Edit-diff representation** — how is the seller's edit captured and turned into a weight update (token diff? semantic intent diff? accept/reject of specific tactics)? FR-19/FR-26 specify *that* it happens, not *how*.
- **Q4.** **Per-category learning granularity** — what counts as a "category" for tuning CONC magnitudes (FR-26)? Not defined in any source.
- **Q5.** **Concrete latency target** for NFR-4 (p95 draft time) — CONVENTIONS gives no number.
- **Q6.** **AUTO-SEND timing** — should auto-sent replies be deliberately delayed to avoid reading as a bot (ties to Q in Section 8.c #5)?

---

## 10. Doc map — handoff reading order

Read in this order:

1. **[00-PRD.md](00-PRD.md)** ← you are here. What we're building and why.
2. **[Section 3 — Marketplace Playbook](SECTION-3-marketplace-playbook.md)** — the operational 5-stage playbook (listing → close → learn).
3. **[Section 4 — Decision Framework](SECTION-4-decision-framework.md)** — the runtime decision tree (automated vs. suggested).
4. **EVAL-PLAN.md** — the technique-lift eval plan and simulated-buyer harness spec. *(Forthcoming sibling doc; see §9.1 and CONVENTIONS §F for what it must prove.)*
5. **[Section 5 — Self-Improving System](SECTION-5-self-improving-system.md)** — the learning-loop design.
6. **[Section 6 — Metrics](SECTION-6-metrics.md)** — success metrics, north-star instrumentation.

**Reference / appendix** (consult as needed, not front-to-back):
- [Section 1 — Source Audit](SECTION-1-source-audit.md), [Section 2 — Cross-source Synthesis](SECTION-2-cross-source-synthesis.md), [Section 7 — Reusable Assets](SECTION-7-reusable-assets.md), [Section 8 — Gaps](SECTION-8-gaps.md), [Section 9 — Final Synthesis](SECTION-9-final-synthesis.md).
- The machine-readable assets: [`assets/json/`](assets/json/) — `principles.json` (PRIN), `buyer-intent-classifier.json` (INTENT), `objection-library.json` (OBJ), `concession-table.json` (CONC), `coaching-tips.json` (COACH).
- Binding spec: **[CONVENTIONS.md](CONVENTIONS.md)** — wins over everything, including this PRD.
