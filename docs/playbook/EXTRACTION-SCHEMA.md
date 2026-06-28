# Pass 1 — Book Profile Extraction Schema (shared by all 7 agents)

> Goal: turn each book into **product material** for a marketplace selling copilot — NOT a book summary.
> Target markets: Depop / Vinted / Poshmark / eBay (Best-Offer) + a platform-agnostic core. Casual sellers.
> Always: cite source locators, distinguish source-supported from inferred, convert ideas into product behavior.

## Output 1 — `<book-slug>.md` (human-readable profile)

### 1. Metadata
- `title`, `author`, `category` (e.g. tactical-negotiation, principled-negotiation, persuasion, communication)
- `domain_fit_note`: 2–3 sentences — how directly this book maps to P2P resale chat negotiation.
- `applicability_score`: 1–5 (5 = directly usable as message copy/logic; 1 = mostly ignorable for this product).

### 2. Core thesis
3–5 sentences. The book's central argument in its own terms.

### 3. Plays (the atomic unit — aim for 8–20 strong ones)
Each play:
```
- id: <book-slug>-play-NN
  principle: <short name>
  what_it_means: <1–2 sentences>
  why_it_matters: <why it works, psychologically/strategically>
  when_to_use: <buyer/listing situation>
  when_NOT_to_use: <failure / backfire condition>
  mechanic: <OPTIONAL — for multi-turn/sequenced/numeric plays (e.g. concession ladders, reciprocity sequences): the step-by-step algorithm. Omit for single-exchange plays.>
  marketplace_mapping: <how it shows up on Depop/Vinted/Posh/eBay specifically>
  example_buyer_message: "<realistic buyer chat/offer>"
  recommended_agent_reply: "<the copilot's suggested seller reply>"
  source_quote_or_locator: "<short quote + chapter/section locator>"
  product_stage_tags: [listing | intent-detection | reply-gen | objection | pricing | trust | safety | coaching | learning-loop | metrics]
```
SOURCE-STATUS CONVENTION (resolves prior friction): `principle / what_it_means / why_it_matters / when_to_use / when_NOT_to_use / mechanic / source_quote_or_locator` are **source-supported** — cite the book. `marketplace_mapping / example_buyer_message / recommended_agent_reply` are understood to be the **inferred product layer by default** — do NOT tag each one [INFERRED]. Only use the [INFERRED] tag when a *principle itself* is your synthesis rather than the book's.

### 4. Communication tactics (phrase-level)
Each: `name`, `purpose`, `phrase_patterns` (templated, e.g. "It sounds like ___"), `overuse_risk`, `good_example`, `bad_example`, `source_locator`.

### 5. Objection material
Map to objection taxonomy: `price-too-high`, `is-it-available`, `lowball`, `competitor-cheaper`, `condition-doubt`, `shipping-cost`, `wants-bundle-deal`, `stalling-ghosting`, `off-platform-request`, `trust-authenticity`, `rude-aggressive`. For each relevant: the book's recommended handling + a sample reply.

### 6. Buyer psychology insights
Bulleted. What the book reveals about how the *other side* thinks/decides.

### 7. Seller psychology insights
Bulleted. Biases/mistakes the *seller* (our user) makes that the copilot should counter.

### 8. Ignore-list
Concepts deliberately dropped (hostage/crisis, enterprise B2B, legal, career comp, in-person-only tactics) — name them so synthesis knows they were considered.

### 9. Guardrail flags
Anything manipulative / fake-urgency / ethically risky that must be flagged if used (esp. Influence).

### 10. Classifiers & personas (NEW)
Any buyer-typing, seller-typing, style, or tone/voice models the book offers (e.g. Voss's Analyst/Accommodator/Assertive + three-voice model; Shell's bargaining styles). For each: `name`, `signals` (observable cues in chat/behavior), `recommended_approach`. These feed the buyer-intent classifier and coaching assets — keep them out of `plays`.

## Output 2 — `json/<book-slug>.json` (machine-readable twin)
Mirror the profile with stable keys:
```json
{
  "book": {"slug":"","title":"","author":"","category":"","domain_fit_note":"","applicability_score":0},
  "core_thesis": "",
  "plays": [ { ...all play fields above, tags as arrays... } ],
  "communication_tactics": [ {"name":"","purpose":"","phrase_patterns":[],"overuse_risk":"","good_example":"","bad_example":"","source_locator":""} ],
  "objection_material": [ {"objection_key":"","handling":"","sample_reply":"","source_locator":""} ],
  "buyer_psychology": [], "seller_psychology": [], "ignore_list": [], "guardrail_flags": [],
  "classifiers_personas": [ {"name":"","signals":[],"recommended_approach":"","source_locator":""} ]
}
```

## Rules
- Cite a locator for every play & tactic (chapter name/number or a short verbatim quote).
- Prefer fewer, sharper, genuinely-usable plays over padding.
- Marketplace mapping must be concrete (mention the Offer button, bundles, likes, shipping, relisting, cross-listing where relevant), not generic.
- Mark inferred/synthesized content explicitly vs. source-supported.
