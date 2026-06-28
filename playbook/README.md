# Marketplace Selling Copilot — Negotiation Playbook

Synthesized from 7 negotiation/persuasion/communication books into **product material** (system rules, message templates, classifiers, metrics, learning loops) for a self-improving selling copilot on P2P marketplaces — **Depop / Vinted / Poshmark / eBay Best-Offer** + a platform-agnostic core. Built for **casual sellers**.

> Method: **Pass 1** — extract each book to a structured profile (product material, not summary). **Pass 2** — dedupe/merge/rank into canonical assets + 9 synthesis sections. Source-supported takeaways are cited to the book; synthesized/inferred content is flagged.

## How to read this

| If you want… | Go to |
|---|---|
| The 60-second version (philosophy + top-10 lists + MVP features + riskiest bets) | [Section 9 — Final synthesis](SECTION-9-final-synthesis.md) |
| Which book is good for what | [Section 1 — Source audit](SECTION-1-source-audit.md) |
| The merged psychology, principles, tactics, objections | [Section 2 — Cross-source synthesis](SECTION-2-cross-source-synthesis.md) |
| The operational 5-stage playbook (listing → close → learn) | [Section 3 — Marketplace playbook](SECTION-3-marketplace-playbook.md) |
| The runtime decision tree (what's automated vs suggested) | [Section 4 — Decision framework](SECTION-4-decision-framework.md) |
| The learning-loop design | [Section 5 — Self-improving system](SECTION-5-self-improving-system.md) |
| Success metrics (beyond price) | [Section 6 — Metrics](SECTION-6-metrics.md) |
| **The drop-in config: principles, classifier, objections, concessions, coaching** | [Section 7 — Reusable assets](SECTION-7-reusable-assets.md) + [`assets/`](assets/) |
| Honest gaps & assumptions to test | [Section 8 — Gaps](SECTION-8-gaps.md) |

## Machine-readable assets (drop into agent config)

Stable-keyed JSON + CSV twins in [`assets/json/`](assets/json) and [`assets/csv/`](assets/csv):

| Asset | Key | Count | File |
|---|---|---|---|
| Principles table | `PRIN-xxx` | 45 | [principles.json](assets/json/principles.json) · [.csv](assets/csv/principles.csv) |
| Buyer-intent classifier | `INTENT-xxx` | 14 | [buyer-intent-classifier.json](assets/json/buyer-intent-classifier.json) · [.csv](assets/csv/buyer-intent-classifier.csv) |
| Objection library | `OBJ-<key>` | 11 | [objection-library.json](assets/json/objection-library.json) · [.csv](assets/csv/objection-library.csv) |
| Concession strategy table | `CONC-xxx` | 12 | [concession-table.json](assets/json/concession-table.json) · [.csv](assets/csv/concession-table.csv) |
| Seller coaching tips | `COACH-xxx` | 24 | [coaching-tips.json](assets/json/coaching-tips.json) · [.csv](assets/csv/coaching-tips.csv) |

`assets/build_assets.py` regenerates the CSV + Section-7 markdown from the canonical JSON.

## The corpus (Pass 1 profiles)

Profiles in [`book-profiles/`](book-profiles) (md) + [`book-profiles/json/`](book-profiles/json) (twins). Schema: [EXTRACTION-SCHEMA.md](EXTRACTION-SCHEMA.md).

| Book | Author | Score | Plays | Role in product |
|---|---|---|---|---|
| [Never Split the Difference](book-profiles/never-split-the-difference.md) | Voss | 5 | 18 | Live message copy (mirror/label/calibrated Qs/Ackerman) |
| [Influence](book-profiles/influence.md) | Cialdini | 5 | 15 | Listing copy + trust (8 guardrails on manipulation) |
| [Getting to Yes](book-profiles/getting-to-yes.md) | Fisher/Ury/Patton | 4 | 16 | Ethics, BATNA, objective-criteria/comps logic |
| [Bargaining for Advantage](book-profiles/bargaining-for-advantage.md) | Shell | 4 | 17 | Buyer-typing classifier, leverage, concession logic |
| [Getting Past No](book-profiles/getting-past-no.md) | Ury | 4 | 15 | Lowball/hostile de-escalation state machine |
| [3-D Negotiation](book-profiles/3d-negotiation.md) | Lax/Sebenius | 4 | 15 | Listing/setup architecture (fix the deal before the table) |
| [Difficult Conversations](book-profiles/difficult-conversations.md) | Stone/Patton/Heen | 4 | 15 | Dispute/complaint tone + safety layer |

**How the books divide labor:** 3-D (setup/listing) → Influence (trust copy) → Bargaining-for-Advantage (classify & coach) → Voss + Getting-to-Yes (live words + rational guardrails) → Getting Past No (hostile threads) → Difficult Conversations (post-sale disputes + ethics).

## Cross-source tensions reconciled
- **"Never split the difference" (Voss) vs. fair compromise (Fisher):** never split two *arbitrary* numbers; a midpoint *inside the comp-supported range and above floor* is allowed. Split is gated behind a standard.
- **Anchor high (Shell/3-D/Cialdini) vs. anchor on BATNA (Fisher):** anchor governs the *opening*, BATNA governs the *exit*.
- **Persuasion levers (Cialdini) vs. anti-manipulation ethics (Difficult Conversations/Shell):** use only the *honest* version of each lever — every demand/supply/authenticity claim is truth-gated (COACH-013).

## The honest caveats (read before building)
1. **Transfer risk** — these tactics were written for high-stakes / in-person / repeated-game negotiation; their fit for two strangers haggling over a $30 item in async chat is the product's foundational bet.
2. **Discount numbers are synthesized** — the books give concession *logic*, not magnitudes; every `max_discount_guidance` is a default to tune per category via the learning loop.
3. **Scam/safety is off-book** — the overpayment/refund/fake-screenshot/chargeback taxonomy (PRIN-044, INTENT-009) is a synthesized overlay, not from any source; the books' "golden bridge" logic is *actively wrong* for scammers.

See [Section 8](SECTION-8-gaps.md) for the full gap analysis.
