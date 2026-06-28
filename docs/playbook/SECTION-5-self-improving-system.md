# Section 5 — Self-Improving System Design

> How the copilot turns every conversation into a slightly better playbook. The 5 canonical assets (PRIN-xxx principles, INTENT-xxx classifier, OBJ-xxx objection handlers, CONC-xxx concession policy, COACH-xxx coaching tips) are the *current* playbook. This section defines how those assets get tuned over time from real outcomes — without learning to manipulate.
>
> **Source note:** The negotiation *content* being tuned is source-supported (the 7 books). The *learning machinery itself* — scoring, weighting, the feedback loop — is **synthesized**; no book describes a self-improving system. Where a learnable parameter has no source-given value (e.g. concrete discount %), it is a synthesized default to be tuned, not a book claim.

## Changelog (v2)
- **6-step loop is now the architecture spine** (§5.0, new). The system is presented as the explicit 1–6 loop from CONVENTIONS §D — "system, not wrapper" — with each step mapped to the asset it uses.
- **Corrected the learning signal (key fix).** The step-5 self-check is a **pre-send GATE, not the teacher**. Ground truth = **seller edits** (esp. on held drafts) + **buyer outcomes**. Self-score is recorded *only* to measure its calibration vs. outcomes. Prior text implying the agent learns from its own grade has been removed (§5.1, §5.3 scoring function).
- **Hybrid autonomy as a data source** (§5.1, new column). Held-for-approval drafts yield the richest signal (AI-draft↔sent diff); auto-sent branches yield outcome-only signal. Both feed the loop.
- **Conversation-level strategy state made explicit** (§5.0, §5.2). Steps 1–3 persist across turns; learning updates per-intent strategy weights, per-objection effectiveness, and CONC-xxx thresholds — now objective/urgency-conditioned per CONVENTIONS §E.
- MVP build (SQLite + Beta/Thompson sampling), cold-start from `marketplace_fit_rank`, and learning guardrails are **unchanged** except where they conflicted with the above.

---

## 5.0 The 6-step loop IS the architecture (system, not wrapper)

This product is not a prompt around an LLM. It is the explicit **6-step agent loop** from CONVENTIONS §D, where each step is bound to a canonical asset and to persistent conversation state. The self-improving machinery in the rest of this section is *step 6 closing back onto steps 1–5* — that closed loop is what makes it a system.

```
                         CONVERSATION-LEVEL STRATEGY STATE
        (steps 1–3 persist across turns — strategy is NOT re-rolled per message)
        ┌─────────────────────────────────────────────────────────────────┐
        │                                                                   │
        ▼                                                                   │
  (1) UNDERSTAND CONSTRAINTS ──► seller input schema (§A: list/target/      │
        load once per listing        walkaway, urgency, objective_weight)   │
        │                                                                   │
        ▼                                                                   │
  (2) CLASSIFY INTENT ─────────► INTENT-xxx + confidence score              │
        per buyer message            (from message text + behavioral signals)│
        │                                                                   │
        ▼                                                                   │
  (3) PICK STRATEGY ───────────► PRIN-xxx + CONC-xxx,  conditioned on       │
        persisted, not re-rolled     intent × objective_weight × urgency (§E)│
        │                            └─ stored as conversation strategy state┘
        ▼
  (4) GENERATE GROUNDED REPLY ─► OBJ-xxx handler + voice layer (§C);
        per buyer message            grounded in constraints + comps only
        │
        ▼
  (5) SELF-CHECK = PRE-SEND GATE ─► within bounds? on-voice? guardrail/
        NOT the teacher                honesty pass? FAIL → regenerate / escalate
        │                            (self-score is RECORDED, never trained on)
        ▼
     hybrid-autonomy branch (§B): AUTO-SEND  |  HOLD-FOR-APPROVAL  |  ESCALATE
        │
        ▼
  (6) LEARN ◄─────────────────── ground truth = SELLER EDITS + BUYER OUTCOMES
        updates the assets used      self-score logged only for calibration
        in steps 1–3
        └──────────────► writes weights back to PRIN/INTENT/OBJ/CONC ──► (loop)
```

**Step → asset map (the spine):**

| Step | Asset / state it uses | What it produces |
|---|---|---|
| 1 Understand constraints | seller input schema (§A) + voice (§C) | the bounds every later step respects (walkaway, target, urgency, objective_weight) |
| 2 Classify intent | INTENT-xxx | intent label + **confidence score** |
| 3 Pick strategy | PRIN-xxx + CONC-xxx + **conversation strategy state** | a persisted plan, conditioned on intent × objective × urgency (§E) |
| 4 Generate reply | OBJ-xxx + voice layer (§C) | grounded draft, no fabricated scarcity/comps |
| 5 Self-check | the **pre-send gate** (bounds/voice/guardrail/honesty) | pass→send-branch, fail→regenerate/escalate; **a logged self-score** |
| 6 Learn | seller edits + buyer outcomes (this whole section) | updated weights on the assets in steps 1–3 |

**Why this is a system, not a wrapper:** steps 1–3 are *stateful* (they persist across the whole conversation, not per message — CONVENTIONS §D), step 5 *blocks* bad output before it ships, and step 6 *changes the assets that steps 1–3 read next time*. A wrapper would re-prompt from scratch every message and never close that loop.

---

## 5.1 What the system learns from (INPUTS)

Every input is an *event* the copilot can log against a conversation, a listing, and the asset(s) it deployed. Inputs split into three streams.

### A. Buyer-behavior signals (must come from platform data — see §8)
| Signal | Source | What it informs |
|---|---|---|
| Buyer message text + tone | conversation | INTENT-xxx classification, OBJ-xxx routing |
| Reply latency (buyer + seller) | timestamps | ghosting risk, intent strength, PRIN-015 timing |
| Likes / saves / watchers | platform API | scarcity truthfulness (PRIN-011, PRIN-029), BATNA strength (PRIN-010) |
| Days-on-market | listing | BATNA decay (CONC-008), markdown cadence (PRIN-038) |
| Repeat-buyer / follower / local status | platform | firmness dial (PRIN-027, INTENT-011) |
| Multi-item likes in one buyer | platform | bundle opportunity (PRIN-006, INTENT-006) |

### B. Seller-action signals (the highest-value, cheapest-to-capture input — and one of the two ground-truth signals)
**Seller edits are a ground-truth teacher, not just a hint.** Together with buyer outcomes (stream C), they are what the system actually learns from. The hybrid-autonomy branch (§B of CONVENTIONS) determines *how much* signal each message yields — see the table below.

| Signal | What it tells us |
|---|---|
| **Seller edits to a HELD draft** | **The single richest training signal.** The diff between the AI draft and what the seller actually sent *is* the supervised label: a heavy edit = the suggestion missed; send-as-is = it landed. Only the HOLD-FOR-APPROVAL branch produces this diff. |
| Seller **rejects** a held suggestion / writes their own | Strong negative on the asset(s) used in steps 3–4 for that context |
| Seller **overrides a guardrail prompt** (e.g. accepts a sub-floor offer) | Calibration data for that seller's real floor (COACH-001) |
| Which of the 3 OBJ variations (warm/firm/data-backed) the seller picks | Per-seller style preference |

**Signal richness by autonomy branch (§B):**

| Branch | What gets captured | Signal type |
|---|---|---|
| **HOLD FOR APPROVAL** (counters, concessions, OBJ handling, re-engagement, high-touch tactics) | AI draft **+** seller's edited/approved text **+** eventual buyer outcome | **Richest:** edit-diff (supervised) **and** outcome. The diff teaches *reply quality*; the outcome teaches *strategy*. |
| **AUTO-SEND** (greeting, "is it available?", factual Qs, accept ≥ target, confirm approved logistics) | sent text (= AI text, no edit) **+** buyer outcome | **Outcome-only:** no edit-diff exists (nothing was held), so these messages train strategy/asset effectiveness but not reply-quality-vs-edit. |
| **ESCALATE** (off-platform, dispute, offer < walkaway, low confidence) | handed to seller; not auto-sent | **Out of the learning loop** — safety stops never train weights (guardrail 4). |

> Implication for storage: log the autonomy branch per message so the scorer knows whether an edit-distance term is even defined. On AUTO-SEND rows `seller_edit_distance` is *absent* (not zero), and the reward falls back to outcome terms only.

### C. Outcome signals (the ground-truth label, often delayed)
| Outcome | Captured when |
|---|---|
| Accept / decline / counter event | buyer responds to an offer |
| Final price vs. ask (ratio) | sale closes |
| Time-to-sale (first-contact → paid) | sale closes |
| Ghosting (no reply within window after a copilot reply) | timeout |
| Relist outcome (re-sold at what price, after how long) | relist closes |
| Dispute / return / chargeback opened | post-sale |
| Review / rating + repeat purchase | post-sale, delayed |

> **Attribution rule:** an outcome is credited to *every asset deployed in that thread*, weighted toward the asset used closest to the decision point. This is coarse but adequate for an MVP (see §5.5).

### D. Self-check score (recorded — NOT a learning input)
The step-5 self-check (CONVENTIONS §D.5) emits a pass/fail gate decision and a score. **This score is logged but is never a training target.** LLM self-grading is unreliable and sycophantic, so it cannot be ground truth. We store it for exactly one purpose: to measure its **calibration** against the real ground-truth signals (seller edits in stream B, buyer outcomes in stream C). If self-score reliably predicts low edit-distance and good outcomes, it earns trust as a cheaper proxy; until then it only gates, it does not teach. (Calibration is also a north-star supplement — CONVENTIONS §G.)

---

## 5.2 What actually updates (LEARNING OUTPUTS)

The system does **not** retrain a model in the MVP. It updates **scalar weights and thresholds attached to the canonical assets** — i.e. it tunes the assets read by **steps 1–3 of the loop** (§5.0), which persist as conversation-level strategy state across turns. Six tunable surfaces:

1. **Per-intent strategy weights** (tunes step 3) — for each INTENT-xxx, a weight over its `recommended_strategy` PRIN list. If PRIN-002 (calibrated question) closes lowballers (INTENT-002) more often than PRIN-008 (don't-split), its weight rises and it surfaces first. Because strategy is *persisted per conversation* (not re-rolled per message — CONVENTIONS §D.3), the unit credited is the strategy chosen for the thread, not each individual reply.
2. **Per-objection reply effectiveness** (tunes step 4) — for each OBJ-xxx, the win-rate of the warm / firm / data-backed variation. Surface the best-performing variation by context (and per seller, once enough data). Reply quality here is judged primarily by **seller edit-distance on held drafts** (stream B), strategy fit by outcome (stream C).
3. **Concession policy / discount thresholds** (tunes step 3) — the synthesized `max_discount_guidance` figures in CONC-001…012 are **defaults, not constants**. They are tuned **conditioned on `objective_weight` and `urgency`** (CONVENTIONS §E): the same CONC-xxx has different learned thresholds for a price-weighted / `no_rush` seller vs. a speed-weighted / `gone_today` seller (opening counter, increment size/cadence, accept threshold, relist cadence all shift per §E). Tune per (category × objective-bucket × urgency-bucket × seller) from `final-price-vs-ask` and `time-to-sale`. Example: if CONC-001's "0–10% on a first lowball" yields high ghosting in fast-moving, speed-weighted contexts, the system nudges *that bucket's* default up — *but only inside the floor/BATNA gate* (see guardrails).
4. **Listing-quality recommendations** — PRIN-034 (barriers audit) / PRIN-037 (set the spirit) thresholds: how many photos, comp-anchored price band, bundle-eligibility, reply-latency targets that correlate with sell-through.
5. **Seller-specific style & floor calibration** — infer the seller's bargaining style (COACH-020) and their *revealed* floor from override behavior, then dial firmness (PRIN-027) and coaching nudges to their blind spot (PRIN-045).
6. **Intent-classifier signal weights** — which observable signals best predict each INTENT-xxx (e.g. how much "offers <50% instantly" should weigh toward INTENT-002). Corrected by seller re-labels and by outcomes.

---

## 5.3 The feedback loop (architecture)

This is step 6 of the loop (§5.0) drawn out. Note the two ground-truth signals feeding the scorer — **seller edits** and **buyer outcomes** — and that the **self-check is a gate before sending, off the learning path** (its score branches off only into a calibration log).

```
                       ┌──────────────────────────────────────────────┐
                       │            CANONICAL PLAYBOOK                  │
                       │  PRIN · INTENT · OBJ · CONC · COACH  + weights │
                       └───────────────┬──────────────────────────────┘
                                       │ steps 1–3 read current weights
                                       ▼   (persisted strategy state)
   buyer message ─────►  [ CLASSIFY ]  ──►  [ SUGGEST ]  ──►  draft reply
                         INTENT-xxx        pick PRIN/OBJ/        + coaching
                         (2)               CONC by weight (3,4)  nudge
                                       │
                                       ▼
                            [ SELF-CHECK = PRE-SEND GATE ] (5)
                            bounds? voice? guardrail? honesty?
                            FAIL → regenerate / escalate
                            self-score ─ ─ ─► [ calibration log only ]
                                       │ (gate PASSED)
                                       ▼
                            hybrid-autonomy branch (§B)
                            ┌──────────────┴───────────────┐
                            ▼                               ▼
                   HOLD FOR APPROVAL                  AUTO-SEND
                   [ SELLER REVIEWS ] ◄─ human-in-loop  (within bounds)
                   edit / send / reject                    │
                            │ GROUND TRUTH #1:              │ (no edit-diff)
                            │ edit-diff(draft, sent)        │
                            └──────────────┬───────────────┘
                                       ▼
                              message sent to buyer
                                       ▼
                              [ OUTCOME LOGGED ]   GROUND TRUTH #2
                       accept · decline · price · time · ghost
                       · dispute · review · relist
                                       ▼
                              [ SCORE EFFECTIVENESS ]  (6a)
                       reward = f(closed?, price-vs-ask, speed,
                                 trust-preserved, seller-edit-distance*)
                                 * defined only on HELD drafts
                                       ▼
                              [ UPDATE WEIGHTS ]  (6b)
                       per-intent strategy · per-objection variation ·
                       concession thresholds (by objective×urgency) ·
                       classifier signals · seller style/floor
                                       │  ──► writes back to PLAYBOOK
                                       └──────────► (loop)
```

**The loop in one line:** *suggest → (gate) → seller edits/sends OR auto-sends → outcome logged → effectiveness scored on **edits + outcomes** → playbook weights updated → next suggestion is better.* The self-score never appears in that chain; it is logged to the side for calibration only.

### Scoring / learning function (what trains the weights)
The scorer's job is to convert **ground-truth signals** — seller edits and buyer outcomes — into a reward. **It deliberately does not consume the model's own self-check score**, because LLM self-grading is unreliable and sycophantic (CONVENTIONS §D.5). A composite, deliberately **not** price-only:

```
# GROUND-TRUTH INPUTS ONLY. self_check_score is NOT an argument here.
reward = w1·closed
       + w2·(final_price / ask)          # margin capture          (outcome)
       − w3·time_to_sale_normalized      # speed                   (outcome)
       + w4·trust_preserved              # no dispute, good/!bad review, repeat (outcome)
       − w5·seller_edit_distance         # reply quality (low edit = good) (seller edit; HELD drafts only)
       − w6·ghosted                      # relationship/conversion failure (outcome)

# AUTO-SEND rows: w5 term is OMITTED (no edit-diff exists), reward = outcome terms only.
# self_check_score: stored separately, regressed against `reward` to measure calibration — never fed back as a target.
```

`trust_preserved` and `seller_edit_distance` are what stop the system from collapsing into a pure price-maximizer. The `w` weights are themselves a product decision (see §6 metric balance), not learned, so the system can't quietly re-prioritize toward extraction. **And critically, the agent never grades its own homework:** every term above is an observed fact (a seller action or a buyer/market outcome), not the agent's opinion of its own reply.

---

## 5.4 Guardrails on learning

The learning loop is the most dangerous part of this product: a naive optimizer *will* discover manipulation because manipulation often raises short-term price. These are hard constraints on what the system is allowed to learn.

1. **Never learn to manipulate (honesty is non-negotiable, not a tunable).** The COACH-013 guardrail — only TRUE scarcity, social proof, comps, authenticity — is a **fixed precondition on generation, outside the learning loop**. The system may learn *which true scarcity framing converts best*; it may never learn to fabricate saves, phantom buyers, fake countdowns, or comps. Tied to the unanimous fake-scarcity guardrail across NSD/GTY/GPN/BFA/3DN/INF.
2. **Don't optimize purely for price at the cost of trust/ethics.** The reward function includes `trust_preserved` and penalizes disputes/ghosting precisely so the optimizer can't trade relationship for margin. Anchored to Getting-to-Yes fairness (principled, hard-on-merits-soft-on-people) and the Influence guardrail that each principle "works as well honestly as dishonestly, so you never need to fake it." Reaction/reactance guardrails (PRIN-033, COACH-014) cap learned pressure: the system may not learn to nudge more than once.
3. **Floor/BATNA gate on concession learning.** Tuned discount thresholds (CONC-xxx) can move *within* the seller's comp-supported floor and BATNA (PRIN-010), never below. The system can learn to be *less* generous; it can only learn to be *more* generous up to the seller-set or comp-derived floor. No regret-accepts (COACH-001 trip wire).
4. **Human-in-the-loop on every move that matters (hybrid autonomy, CONVENTIONS §B).** The copilot never auto-sends a **negotiation move**: all counters, concessions, objection handling, and high-touch tactics are HOLD-FOR-APPROVAL — the seller reviews and can edit/reject. Only low-risk, within-bounds actions (greeting, "is it available?", factual Qs from the listing, accept ≥ target) AUTO-SEND. Anything risky (off-platform, dispute, offer < walkaway, low confidence) ESCALATES and is never auto-sent. Seller edits on held drafts are the *primary training signal*, and the seller remains the safety valve. Safety stops (PRIN-044 off-platform / INTENT-009 scam) are **never** part of the learning loop — they hard-block regardless of any learned weight.
5. **Cold-start defaults.** With zero history, the system runs the source-derived `marketplace_fit_rank` ordering of PRIN-xxx, the OBJ default variation = `warm`, and the CONC synthesized defaults — i.e. the books' best guess. Learning only overrides a default after a minimum support threshold (e.g. ≥ N observations for that intent×category), to avoid chasing noise. Until then, behavior is fully explainable from the source assets.
6. **Per-seller, then pooled — with privacy.** Seller-specific calibration is preferred; global priors fill in until a seller has enough data. Pooled learning is over *outcomes and asset-effectiveness*, never over raw buyer PII.
7. **Auditability.** Every suggestion records which asset IDs and weights produced it, so any learned drift is traceable back to a PRIN/OBJ/CONC id and the outcomes that moved it.

---

## 5.5 MVP cut (build this first)

You do not need RL or a model retrain to ship the loop. A concrete MVP:

- **Storage:** one row per (thread, asset_id_deployed, intent, objection, variation, **autonomy_branch**, suggested_text, sent_text, **self_check_score**, outcome). SQLite is fine. `autonomy_branch ∈ {auto_send, hold, escalate}` decides whether an edit-diff exists; `self_check_score` is stored but never read by the update rule (calibration column only). Also persist per-thread strategy state (chosen PRIN/CONC for steps 1–3) so it isn't re-rolled per message.
- **Scoring:** compute `reward` on outcome events with fixed `w` weights from **ground-truth signals only**. `seller_edit_distance` = normalized Levenshtein(suggested, sent) — computed **only on `hold` rows**; on `auto_send` rows omit the w5 term. Never feed `self_check_score` into `reward`; instead periodically regress `self_check_score` against realized `reward` to report calibration (CONVENTIONS §G).
- **Update rule:** maintain a running win-rate per (asset_id × intent × category) with a Bayesian/Beta prior seeded from `marketplace_fit_rank`; surface the highest-posterior option (Thompson sampling gives free exploration). No gradients required. The reward driving the Beta update comes from seller edits + outcomes, not self-score.
- **Concession tuning:** start at CONC defaults; key the threshold table by (category × **objective_weight bucket** × **urgency bucket**) per CONVENTIONS §E; adjust a bucket's threshold by a small step when `final-price/ask` and `time-to-sale` both move favorably across that bucket's support window, clamped by the floor gate.
- **Seller style:** rule-based from override/edit history (over-caves → COACH-020 accommodator nudge), upgraded later.
- **Human-in-the-loop + cold-start + honesty guardrails are in from day one** — they are correctness, not polish.
