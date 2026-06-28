# Section 5 — Self-Improving System Design

> How the copilot turns every conversation into a slightly better playbook. The 5 canonical assets (PRIN-xxx principles, INTENT-xxx classifier, OBJ-xxx objection handlers, CONC-xxx concession policy, COACH-xxx coaching tips) are the *current* playbook. This section defines how those assets get tuned over time from real outcomes — without learning to manipulate.
>
> **Source note:** The negotiation *content* being tuned is source-supported (the 7 books). The *learning machinery itself* — scoring, weighting, the feedback loop — is **synthesized**; no book describes a self-improving system. Where a learnable parameter has no source-given value (e.g. concrete discount %), it is a synthesized default to be tuned, not a book claim.

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

### B. Seller-action signals (the highest-value, cheapest-to-capture input)
| Signal | What it tells us |
|---|---|
| **Seller edits to a suggested reply** | The single richest quality signal. A heavy edit = the suggestion missed; a send-as-is = it landed. Diff the suggested vs. sent text. |
| Seller **rejects** a suggestion / writes their own | Strong negative on that asset for that context |
| Seller **overrides a guardrail prompt** (e.g. accepts a sub-floor offer) | Calibration data for that seller's real floor (COACH-001) |
| Which of the 3 OBJ variations (warm/firm/data-backed) the seller picks | Per-seller style preference |

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

---

## 5.2 What actually updates (LEARNING OUTPUTS)

The system does **not** retrain a model in the MVP. It updates **scalar weights and thresholds attached to the canonical assets**. Six tunable surfaces:

1. **Per-intent strategy weights** — for each INTENT-xxx, a weight over its `recommended_strategy` PRIN list. If PRIN-002 (calibrated question) closes lowballers (INTENT-002) more often than PRIN-008 (don't-split), its weight rises and it surfaces first.
2. **Per-objection reply effectiveness** — for each OBJ-xxx, the win-rate of the warm / firm / data-backed variation. Surface the best-performing variation by context (and per seller, once enough data).
3. **Concession policy / discount thresholds** — the synthesized `max_discount_guidance` figures in CONC-001…012 are **defaults, not constants**. Tune them per category and per seller from `final-price-vs-ask` and `time-to-sale`. Example: if CONC-001's "0–10% on a first lowball" yields high ghosting in fast-moving categories, the system nudges the default up — *but only inside the floor/BATNA gate* (see guardrails).
4. **Listing-quality recommendations** — PRIN-034 (barriers audit) / PRIN-037 (set the spirit) thresholds: how many photos, comp-anchored price band, bundle-eligibility, reply-latency targets that correlate with sell-through.
5. **Seller-specific style & floor calibration** — infer the seller's bargaining style (COACH-020) and their *revealed* floor from override behavior, then dial firmness (PRIN-027) and coaching nudges to their blind spot (PRIN-045).
6. **Intent-classifier signal weights** — which observable signals best predict each INTENT-xxx (e.g. how much "offers <50% instantly" should weigh toward INTENT-002). Corrected by seller re-labels and by outcomes.

---

## 5.3 The feedback loop (architecture)

```
                       ┌──────────────────────────────────────────────┐
                       │            CANONICAL PLAYBOOK                  │
                       │  PRIN · INTENT · OBJ · CONC · COACH  + weights │
                       └───────────────┬──────────────────────────────┘
                                       │ (1) reads current weights
                                       ▼
   buyer message ─────►  [ CLASSIFY ]  ──►  [ SUGGEST ]  ──►  draft reply
                         INTENT-xxx        pick PRIN/OBJ/        + coaching
                                           CONC by weight        nudge
                                       │
                                       ▼
                              [ SELLER REVIEWS ]   ◄── human-in-the-loop
                              edit / send / reject
                                       │ (2) log seller action  (edit-diff)
                                       ▼
                              message sent to buyer
                                       │
                                       ▼
                              [ OUTCOME LOGGED ]   (3)
                       accept · decline · price · time · ghost
                       · dispute · review · relist
                                       │
                                       ▼
                              [ SCORE EFFECTIVENESS ]  (4)
                       reward = f(closed?, price-vs-ask, speed,
                                 trust-preserved, seller-edit-distance)
                                       │
                                       ▼
                              [ UPDATE WEIGHTS ]  (5)
                       per-intent strategy · per-objection variation ·
                       concession thresholds · classifier signals ·
                       seller style/floor   ──► writes back to PLAYBOOK
                                       │
                                       └──────────► (loop)
```

**The loop in one line:** *suggest → seller edits/sends → outcome logged → effectiveness scored → playbook weights updated → next suggestion is better.*

### Scoring function (effectiveness reward)
A composite, deliberately **not** price-only:

```
reward = w1·closed
       + w2·(final_price / ask)          # margin capture
       − w3·time_to_sale_normalized      # speed
       + w4·trust_preserved              # no dispute, good/!bad review, repeat
       − w5·seller_edit_distance         # suggestion quality (low edit = good)
       − w6·ghosted                      # relationship/conversion failure
```

`trust_preserved` and `seller_edit_distance` are what stop the system from collapsing into a pure price-maximizer. The `w` weights are themselves a product decision (see §6 metric balance), not learned, so the system can't quietly re-prioritize toward extraction.

---

## 5.4 Guardrails on learning

The learning loop is the most dangerous part of this product: a naive optimizer *will* discover manipulation because manipulation often raises short-term price. These are hard constraints on what the system is allowed to learn.

1. **Never learn to manipulate (honesty is non-negotiable, not a tunable).** The COACH-013 guardrail — only TRUE scarcity, social proof, comps, authenticity — is a **fixed precondition on generation, outside the learning loop**. The system may learn *which true scarcity framing converts best*; it may never learn to fabricate saves, phantom buyers, fake countdowns, or comps. Tied to the unanimous fake-scarcity guardrail across NSD/GTY/GPN/BFA/3DN/INF.
2. **Don't optimize purely for price at the cost of trust/ethics.** The reward function includes `trust_preserved` and penalizes disputes/ghosting precisely so the optimizer can't trade relationship for margin. Anchored to Getting-to-Yes fairness (principled, hard-on-merits-soft-on-people) and the Influence guardrail that each principle "works as well honestly as dishonestly, so you never need to fake it." Reaction/reactance guardrails (PRIN-033, COACH-014) cap learned pressure: the system may not learn to nudge more than once.
3. **Floor/BATNA gate on concession learning.** Tuned discount thresholds (CONC-xxx) can move *within* the seller's comp-supported floor and BATNA (PRIN-010), never below. The system can learn to be *less* generous; it can only learn to be *more* generous up to the seller-set or comp-derived floor. No regret-accepts (COACH-001 trip wire).
4. **Human-in-the-loop is mandatory.** The seller always reviews and can edit/reject every outbound message; the copilot suggests, it does not autosend negotiation moves. Seller edits are *training signal*, but the seller is also the safety valve. Safety stops (PRIN-044 off-platform / INTENT-009 scam) are **never** part of the learning loop — they hard-block regardless of any learned weight.
5. **Cold-start defaults.** With zero history, the system runs the source-derived `marketplace_fit_rank` ordering of PRIN-xxx, the OBJ default variation = `warm`, and the CONC synthesized defaults — i.e. the books' best guess. Learning only overrides a default after a minimum support threshold (e.g. ≥ N observations for that intent×category), to avoid chasing noise. Until then, behavior is fully explainable from the source assets.
6. **Per-seller, then pooled — with privacy.** Seller-specific calibration is preferred; global priors fill in until a seller has enough data. Pooled learning is over *outcomes and asset-effectiveness*, never over raw buyer PII.
7. **Auditability.** Every suggestion records which asset IDs and weights produced it, so any learned drift is traceable back to a PRIN/OBJ/CONC id and the outcomes that moved it.

---

## 5.5 MVP cut (build this first)

You do not need RL or a model retrain to ship the loop. A concrete MVP:

- **Storage:** one row per (thread, asset_id_deployed, intent, objection, variation, suggested_text, sent_text, outcome). SQLite is fine.
- **Scoring:** compute `reward` on outcome events with fixed `w` weights; `seller_edit_distance` = normalized Levenshtein(suggested, sent).
- **Update rule:** maintain a running win-rate per (asset_id × intent × category) with a Bayesian/Beta prior seeded from `marketplace_fit_rank`; surface the highest-posterior option (Thompson sampling gives free exploration). No gradients required.
- **Concession tuning:** start at CONC defaults; adjust the threshold by a small step when `final-price/ask` and `time-to-sale` both move favorably across the support window, clamped by the floor gate.
- **Seller style:** rule-based from override/edit history (over-caves → COACH-020 accommodator nudge), upgraded later.
- **Human-in-the-loop + cold-start + honesty guardrails are in from day one** — they are correctness, not polish.
