# Section 3 — Marketplace negotiation playbook

The operational core of the selling copilot for P2P marketplaces (Depop / Vinted / Poshmark / eBay Best-Offer; platform-agnostic core). This section converts the synthesized principles, intents, objections, concessions, and coaching tips into concrete copilot **behavior**: detection rules, decision logic, and ready-to-send message templates.

The negotiation surface is always the platform's **Offer / Best-Offer button**. The copilot's job across the lifecycle is to (1) pre-empt haggling in the listing, (2) read the buyer's intent on first contact, (3) run a disciplined concession loop, (4) lock commitment on-platform, and (5) log the outcome to feed the learning loop.

**Source books cited by ID:**

| Key | Book | Role in copilot |
|-----|------|-----------------|
| NSD | *Never Split the Difference* (Voss) | Chat message copy, calibrated questions, Ackerman ladder |
| GTY | *Getting to Yes* (Fisher/Ury/Patton) | Decision-logic / ethics spine, interests, BATNA, objective criteria |
| GPN | *Getting Past No* (Ury) | De-escalation, golden bridge, warn-don't-threaten |
| BFA | *Bargaining for Advantage* (Shell) | Buyer-style classifier, anchoring, concession ladder, leverage |
| 3DN | *3-D Negotiation* (Lax & Sebenius) | Listing/deal architecture, bundles, terms, setup |
| INF | *Influence* (Cialdini) | Listing copy, trust framing, persuasion levers (honest only) |
| DC | *Difficult Conversations* (Stone/Patton/Heen) | Tone, complaints, accusations, safety layer |

The five canonical asset families are referenced throughout: **PRIN-xxx** (principles), **INTENT-xxx** (buyer types), **OBJ-xxx** (objections), **CONC-xxx** (concessions), **COACH-xxx** (seller coaching).

---

## Stage 1 — Listing creation (win the deal before the table)

> **3-D thesis (3DN):** most of the negotiation is won *away from the table* — in parties, framing, comps, terms, and timing. A comp-anchored, well-framed listing draws fair offers without a fight. The copilot's first and highest-leverage job is to build the listing so the buyer offers fairly. Per **COACH-006**, never slash price when the real problem is the listing.

### Copilot behavior

1. **Price the anchor, not the floor.** The copilot pulls sold comps and recommends a list price near the **top of the comp range** — high but defensible (PRIN-009, PRIN-003). It simultaneously asks the seller for / computes two private numbers it will use later: a **floor** (BATNA = relist/hold value) and a **trip wire** ("reconsider below $X") — PRIN-010, COACH-001.
2. **Embed objective criteria.** Listing copy states the comp basis in buyer-facing language ("priced in line with recent sold ones in this condition") so price reads as *market*, not *seller opinion* (PRIN-003, GTY).
3. **Scarcity / social proof — only if true.** The copilot surfaces real signals: "last one in this size," genuine save/watcher counts, sold count, star rating (PRIN-011, PRIN-029, INF). **COACH-013 guardrail:** any claim about demand, supply, authenticity, or comparison is checked against real listing/seller data before it can be written; fabricated scarcity, phantom buyers, fake comps, and unbacked authentication are **hard-blocked**.
4. **Trust signals up front (skeptic pre-empt).** Authentic-proof scaffolding for higher-value items: date-code/serial photos, receipt mention, sales history, returns/authenticity-guarantee note (PRIN-030, INF) — pre-empts INTENT-012 and OBJ-trust-authenticity.
5. **Set the spirit of the deal (dispute pre-empt).** The generator proactively states **condition with flaw photos, dispatch time, and return policy** concisely (PRIN-037, COACH-023). This is the single biggest lever against post-sale OBJ-condition-doubt and OBJ-trust-authenticity disputes.
6. **Design the deal for bundles + shipping.** Mark bundle-eligible related stock, set combined-shipping rules, and frame the listing for the highest-value buyer / right audience (PRIN-035, PRIN-006, 3DN). This pre-loads Stage 3 northeast moves.
7. **Plan the timing cadence.** The copilot schedules relist/refresh timing and a measured markdown ladder (e.g. −10% per 7–10 days, timed to paydays/season) rather than reactive deep cuts (PRIN-038, COACH-021).

### Listing checklist (copilot enforces before publish)

| # | Check | Principle / Coach | Pass criterion |
|---|-------|-------------------|----------------|
| 1 | List price near top of comp range | PRIN-009, PRIN-003, COACH-002 | Price ≤ top comp, ≥ goal |
| 2 | Private floor + trip wire set | PRIN-010, COACH-001 | Both numbers stored |
| 3 | Comp basis stated in copy | PRIN-003 | Buyer-facing reason present |
| 4 | Scarcity / social proof is TRUE | PRIN-011, PRIN-029, COACH-013 | Verified against real data |
| 5 | Condition graded + flaw photos | PRIN-037, COACH-023 | Every known flaw shown |
| 6 | Dispatch time + return policy stated | PRIN-037, COACH-023 | Both present |
| 7 | Authenticity proof (if value warrants) | PRIN-030 | Serial/receipt/guarantee noted |
| 8 | Bundle-eligible stock tagged + combined shipping rule | PRIN-006, PRIN-035 | Rules set |
| 9 | Relist/markdown cadence scheduled | PRIN-038, COACH-021 | Cadence stored |
| 10 | Photos pass quality bar | 3DN, COACH-006 | Lighting/angles OK |

### Example listing block (copilot-generated)

> **Vintage wool coat — size M — graded 9/10**
> Barely worn, no flaws beyond one tiny mark on the inner hem (pic 4). Priced at **$50**, in line with recent sold ones in this condition ($48–$55). Ships tracked within 1 business day. Returns accepted if not as described. Last one I have in this size. Bundle with anything else in my shop and I'll combine shipping.

---

## Stage 2 — First buyer message (intent detection)

> The first message is a routing decision, not a reply. The copilot classifies the inbound into one **INTENT-xxx** category from observable signals, then selects an opening move. **COACH-005:** probe before you disclose — default to an interest-probing question before any number. **COACH-008 guardrail:** never react instantly to a triggering message.

### Routing table — signal → intent → first move

| Inbound signal | INTENT | Opening strategy | Principles | First-move template |
|----------------|--------|------------------|-----------|---------------------|
| Specific questions, real budget/use, near-list offer | INTENT-001 Serious | Don't over-negotiate; small-yes ladder to close | PRIN-032, PRIN-018, PRIN-024, PRIN-025 | "Great questions — it's exactly as described. Want me to send you an offer so you can lock it in?" |
| Offer <50–60% of ask, no engagement | INTENT-002 Lowballer | Probe interest, justify on comps, **don't reflex-split** | PRIN-002, PRIN-004, PRIN-003, PRIN-008 | "I appreciate the offer! What were you hoping to spend, and is this for something specific?" |
| "I've seen it cheaper / another seller…" | INTENT-003 Anchor-shopper | Probe the comp, differentiate, don't disparage | PRIN-003, PRIN-011, PRIN-036 | "Totally fair to compare — send the link and I'll take a real look. Mine ships tracked and condition's verified." |
| "Not sure," "never bought used," reassurance questions | INTENT-004 Hesitant | **Proof, not discount**; small-yes ladder | PRIN-013, PRIN-030, PRIN-036, PRIN-032 | "Totally fair to want to be sure — I'll send extra close-ups + measurements. Anything specific you want to see?" |
| Silence 24h+, "maybe later," likes-no-message | INTENT-005 Ghoster | One 'No'-oriented revive; keep offer visible | PRIN-015, PRIN-023, PRIN-011 | "Have you given up on this one? Totally fine either way — just want to know whether to keep holding it." |
| Multiple items liked, "any deal if I take a few?" | INTENT-006 Bundler | **Move northeast**; build the bundle | PRIN-006, PRIN-005, PRIN-028 | "Love that — pick three and I'll knock 15% off the total and combine shipping. Sound good?" |
| Insults, mockery, ALL CAPS lowball | INTENT-007 Rude | Balcony → acknowledge → deflect to problem; **no counter-punch** | PRIN-019, PRIN-020, PRIN-021, PRIN-033 | "Sounds like the price feels way off — I don't want it to feel unfair. What would feel right, and what's it based on?" |
| "Discount or I leave a one-star," serial nibbles, "or else" | INTENT-008 Bully | Hold on leverage; one fair offer; **document + report threats** | PRIN-040, PRIN-019, PRIN-021 | "I price fairly and can't do that. Reviews should reflect the actual item and service. Glad to help at the listed price." |
| "Pay outside the app," ship-first, overpayment, "payment sent" screenshot | INTENT-009 Scam | **SAFETY STOP** — decline, keep on-platform, never ship unpaid | PRIN-044 | "I keep all sales on the app — it protects us both. Happy to finish right here whenever you're ready." |
| "Is this still available?" and nothing else | INTENT-010 Low-signal pinger | Warm + ONE forward step; **don't over-negotiate** | PRIN-039, PRIN-032, PRIN-031 | "Yes it is! I'm Sam — looking to grab it now, or have a question first?" |
| "Bought from you before," warm/local/follower | INTENT-011 Loyal | Accommodate; small loyalty courtesy | PRIN-027, PRIN-031, PRIN-024 | "So glad you're back! I'll take care of you — let me sort a little something for being a repeat buyer." |
| "Is this legit? don't want to get scammed" | INTENT-012 Skeptic | Genuine proof/authority; platform protection as term | PRIN-030, PRIN-029, PRIN-036, PRIN-041 | "100% fair to ask — 180+ sales at 4.9, ships tracked, every flaw shown. What would help you feel comfortable?" |
| Post-sale "not as described / damaged / refund" | INTENT-013 Complainer | **Acknowledge feeling first**, own real fault, two options | PRIN-020, PRIN-013, PRIN-042, PRIN-043 | "I'm really sorry it arrived like that — that's frustrating. Let's make it right: full refund on return, or a partial to keep it. Which works?" |
| Two-word/cryptic ("k.", "seriously?") | INTENT-014 Ambiguous | Neutral clarifier; **don't assume hostility** | PRIN-019, PRIN-012 | "Want to make sure I read that right — were you asking about price, or something else?" |

**"Is it available?" handling (OBJ-is-it-available / INTENT-010):** treated as a **low-signal buying cue**. The copilot answers warmly, names the seller (liking, PRIN-031), and adds exactly **one** forward-motion step (a small-yes or one true scarcity note) — never a dead "yes," never a hard pitch off a one-liner.

---

## Stage 3 — Negotiation (the core loop)

> The engine room. The copilot runs a disciplined offer/counter loop on the Best-Offer button, holds or concedes by policy (**CONC-xxx**), handles objections by handler (**OBJ-xxx**), and de-escalates hostility (DC/GPN) — all gated by the seller's floor.

### Core loop (per buyer offer)

```
1. CLASSIFY    → confirm/refresh INTENT; read offer % vs ask; read tone
2. DON'T REACT → if hostile/ambiguous, go to balcony (PRIN-019, COACH-008)
3. PROBE       → calibrated question to decode interest (PRIN-002, PRIN-004, COACH-005)
4. JUSTIFY     → re-anchor on comps + goal, not floor (PRIN-003, PRIN-009, COACH-002)
5. DECIDE      → hold vs concede vs add-value, per CONC + floor (COACH-007)
6. MOVE        → ONE labeled, conditional, shrinking step — never free, never split (PRIN-007, PRIN-008)
7. CLOSE/LOOP  → if inside fair range, push to Stage 4; else loop with smaller move
```

### When to hold vs. concede (CONC map)

| Situation | Concession policy | Max discount | Hold-firm trigger |
|-----------|-------------------|--------------|-------------------|
| Lowball ~40%+ below ask | CONC-001: probe + comp, ONE move near list, conditional | 0–10% off list | Active saves/watchers, fresh listing, no reason given |
| Reasonable ~10% below | CONC-002: accept or small odd split inside comp range | ~10–12% | Drops below goal w/ leverage |
| Multi-round on higher value | CONC-003: shrinking ladder to floor, odd ending + tiny add-on | down to floor only | Floor reached, buyer stops reciprocating |
| "Just split the difference" | CONC-004: counter odd above midpoint; split only inside comps | inside comps, above floor | Midpoint below floor, or absurd anchor |
| "Free shipping?" | CONC-005: absorb shipping OR flat number — **not both** | shipping if <~15% item value | Thin margin + heavy item, or wants cut AND shipping |
| Bundle 2+ items | CONC-006: blended discount + combined shipping, labeled If/then | ~10–20% off singles | Re-cutting after adds; below item floors |
| Stuck on a public low stand | CONC-007: golden bridge (real cover), keep best offer | = underlying floor | No real interest to meet; only cover would be fake |
| Aging listing, lone buyer, weak BATNA | CONC-008: flex but extract small reciprocal/bundle | toward true floor via ladder | Genuinely scarce; better to relist at season |
| Repeat/loyal/local | CONC-009: small loyalty courtesy, warm | ~5–15% | Buyer exploiting relationship for repeat deep cuts |
| Aggressive / extortion / nibble | CONC-010: **0% to pressure**; one fair move, document | 0% to threats | Any concession extracted by threat/abuse |

### Objection handling (OBJ handlers — each ships warm / firm / data-backed variants)

| Buyer objection | Handler | Core approach | Key principles |
|-----------------|---------|---------------|----------------|
| "Too expensive / not worth it" | OBJ-price-too-high | Acknowledge, justify on comps, pivot to value/terms | PRIN-020, PRIN-003, PRIN-009 |
| "$20" (listed $45) | OBJ-lowball | Decode interest, comp-justify, ONE labeled move | PRIN-002, PRIN-004, PRIN-007, PRIN-008 |
| "Cheaper elsewhere" | OBJ-competitor-cheaper | Probe claim, differentiate, don't disparage | PRIN-003, PRIN-011, PRIN-036 |
| "What condition really?" | OBJ-condition-doubt | Proof + contingent terms; no price drop pre-sale | PRIN-013, PRIN-030, PRIN-036 |
| "Shipping too high / free?" | OBJ-shipping-cost | Absorb or flat-number; spread fee over bundle | PRIN-005, PRIN-006, PRIN-028 |
| "Bundle deal?" | OBJ-wants-bundle-deal | Embrace, move northeast, labeled If/then | PRIN-006, PRIN-005, PRIN-022 |
| Silence / "thinking about it" | OBJ-stalling-ghosting | Find blocker, 'No'-question, keep offer visible | PRIN-015, PRIN-023, PRIN-011 |
| "Pay outside the app" | OBJ-off-platform-request | **Safety stop**, decline on principle, never ship unpaid | PRIN-044 |
| "How do I know it's real?" | OBJ-trust-authenticity | Genuine proof/authority, platform protection | PRIN-030, PRIN-029, PRIN-036, PRIN-041 |
| Insults / "ripoff" / extortion | OBJ-rude-aggressive | Balcony, acknowledge, deflect; leverage vs bullies | PRIN-019, PRIN-020, PRIN-021, PRIN-040 |

### De-escalation protocol for hostile buyers (INTENT-007 / 008, OBJ-rude-aggressive)

1. **Balcony** — interpose a cool-down/draft step; never auto-send to a hostile inbound (PRIN-019, COACH-008).
2. **Step to their side** — acknowledge the feeling/concern before countering (PRIN-020).
3. **Deflect to the problem** — calibrated question + "I"-boundary ("Yes… and at the same time I've priced this at $X for [reason]"); never counter-punch (PRIN-021, PRIN-002, COACH-009).
4. **Restore freedom** — "No pressure either way" defuses reactance (PRIN-033, COACH-014).
5. **Bully fork** — if it's threat/extortion (INTENT-008): hold on leverage, offer only the same fair terms, **document the thread and report** (PRIN-040, CONC-010, COACH-018). Never reward a threat with a concession.
6. **Vent guardrail** — the copilot never generates a counter-attack and reshapes furious seller drafts into purposeful replies or advises holding (COACH-010).

### Turn-by-turn example A — Lowball (INTENT-002 / OBJ-lowball / CONC-001)

> **Listed $50** (comps $48–$55, goal $48, floor $42).

| Turn | Buyer | Copilot-drafted seller reply | Logic |
|------|-------|------------------------------|-------|
| 1 | "$25, take it or leave it." | "I appreciate the offer! How'd you get to $25 — is it budget, or comparing to something? Recent sold ones are $48–55." | Probe + comp, no reflex-counter (PRIN-002, PRIN-004, PRIN-003) |
| 2 | "Just my budget, that's all I can do." | "Got it. I can't do $25 — I'd be way under market. If budget's the thing, I could do **$47 if you grab it today**, or bundle something to stretch it." | ONE labeled, conditional move near list (PRIN-007, CONC-001) |
| 3 | "Come on, meet me at $36." | "I hear you, but $36 is below where these sell. I can do **$45 today** — that's my real move, not a starting point." | Counter above midpoint, odd-firm; don't split arbitrary (PRIN-008, PRIN-017, CONC-004) |
| 4 | "Fine, $45 works." | "Done — sending you the $45 offer now so you can lock it in. Ships tomorrow." | Close for commitment on-platform (PRIN-025) → Stage 4 |

*If the buyer instead repeats "$25" with hostility after two exchanges → disengage politely, leave the standing offer, relist (OBJ-lowball escalate rule).*

### Turn-by-turn example B — Bundle request (INTENT-006 / OBJ-wants-bundle-deal / CONC-006)

> Buyer has liked 3 items: tee $15, cap $15, jacket $40 (singles total $70).

| Turn | Buyer | Copilot-drafted seller reply | Logic |
|------|-------|------------------------------|-------|
| 1 | "Any deal if I take the tee and cap?" | "Love it — let's make it work. **Both for $26 instead of $30, and I'll combine shipping** into one package. Want me to set it up?" | Move northeast, blended discount + combined shipping, labeled (PRIN-006, PRIN-005, CONC-006) |
| 2 | "What if I add the jacket too?" | "Even better. **All three for $60 shipped** (vs $70 + postage). One package, one fee — that's the best value." | Grow the pie; settle whole bundle at once (PRIN-006, PRIN-028) |
| 3 | "Can you also throw in free returns?" | "The $60 shipped already includes my standard return policy — that price is built around the bundle, so I'll keep it there. Shall I send it?" | Nibble named gently; settle once, no re-cut (COACH-019, CONC-006 hold) |
| 4 | "Deal." | "Sending the $60 bundle offer now — confirm in the app and I'll ship tomorrow." | Lock on-platform (PRIN-025) → Stage 4 |

---

## Stage 4 — Closing (lock commitment, stay safe)

> A "yes" with nothing to lose isn't a deal (COACH-003). The copilot converts agreement into an on-platform, written commitment, handles logistics, and treats any off-platform drift as a safety stop.

### Closing behavior

1. **Be generous at the very end.** Bias the closing message toward a tiny final courtesy — free shipping, fast dispatch, a thank-you note (PRIN-024, COACH-012). Don't squeeze the last dollar; an imposed outcome is unstable.
2. **Rule of three / drive to "That's right."** Confirm the agreed terms back in a one-line summary so the buyer affirms them (PRIN-016): "So that's the coat at $45, shipped tomorrow, returns if not as described — all good?"
3. **Get it in writing, on-platform.** Send the **Best-Offer** at the agreed number immediately so the verbal yes becomes a binding, protected commitment (PRIN-025, COACH-003). Never leave a deal in chat.
4. **Golden bridge / face-saving** for a buyer climbing down from a low stand: frame the final price as them taking advantage of a real bundle/new-buyer courtesy, not a climb-down (PRIN-022, CONC-007).
5. **Logistics:** confirm dispatch window, packaging, and tracking; reaffirm return policy. Avoid open-ended unpaid **holds** — offer a deposit/first-to-checkout and keep other buyers parallel (COACH-022). Limit scarcity to one factual note (COACH-014).
6. **Scam / off-platform guardrail (PRIN-044, CONC-012, OBJ-off-platform-request):** decline off-platform on principle ("protects us both"), **never ship before confirmed on-platform payment**. Any ship-first ask, overpayment/refund ask, or unverifiable "payment sent" screenshot → **hard stop, don't ship, report and block.** This is never a price negotiation.

### Closing templates

| Situation | Template | Principle |
|-----------|----------|-----------|
| Confirm + lock | "So that's [item] at $[X], shipped [when], returns if not as described — all good? Sending the offer now so you can grab it." | PRIN-016, PRIN-025 |
| Generous finish | "Done! I'll cover shipping on this one and get it out first thing tomorrow. Thanks for an easy deal." | PRIN-024, COACH-012 |
| Golden bridge | "Perfect timing — I'm running a bundle deal this week, so the $60 is you taking advantage of that. Sending it over." | PRIN-022, CONC-007 |
| Hold request | "I can't hold it unpaid, but if you checkout now it's locked and yours — first firm offer gets it." | COACH-022 |
| Off-platform decline | "I appreciate you wanting to make it easy! I keep it on the app though — protects us both. Happy to finish right here whenever you're ready." | PRIN-044, OBJ-off-platform-request |
| Off-platform hard stop | "I can't ship before payment clears on-platform, and I can't take outside payment. I'll leave the on-app offer up if you'd like to use it." *(report + block if pressed)* | PRIN-044, CONC-012 |

---

## Stage 5 — Post-interaction learning (feed the loop)

> Every closed (or dead) thread is training data. The copilot logs structured outcomes so it can tune anchoring, concession depth, intent classification, and per-seller coaching over time. Seller **edits to drafts** are the strongest signal — they reveal where the copilot's judgment diverges from the seller's.

### What gets logged per thread

| Field | Why it matters | Feeds |
|-------|----------------|-------|
| **Outcome** (sold / no-deal / relisted / disputed / scam-blocked) | Base success label | Win-rate by intent/play |
| **Final price vs ask** (and vs goal vs floor) | Did anchoring hold? Did we leak to floor? | PRIN-009 anchoring, COACH-002 floor-leak nudge |
| **Detected INTENT** + correction | Classifier accuracy | INTENT model retraining |
| **Plays used** (PRIN / OBJ / CONC IDs fired) | Which moves correlate with sale + good review | Play effectiveness ranking |
| **Concession path** (offer→counter sequence, # rounds, increment shape) | Was the ladder disciplined? Splits? | CONC tuning, COACH-004 |
| **Seller edits to drafts** | Divergence between copilot and seller voice/judgment | Draft quality, per-seller tone model |
| **Time-to-close / reply latency** | Speed effects on conversion | COACH-006 latency diagnostic |
| **Listing signals at close** (saves, watchers, days-on-market) | Demand context for the BATNA/markdown model | PRIN-010, PRIN-038 cadence |
| **Review / repeat-buyer outcome** | Did generosity at close pay off? | COACH-012 closer→review correlation |
| **Guardrail events** (scam blocked, fabricated-claim blocked, vent reshaped, balcony triggered) | Safety + ethics audit | COACH-013, COACH-008, PRIN-044 |
| **Seller style signal** (drops fast / never asks / bruises rapport) | Personalized coaching | COACH-020, PRIN-045 |

### Learning behaviors

- **Style coaching loop (COACH-020, PRIN-045):** infer the seller's bargaining-style blind spot over time and tailor nudges ("you're countering near your floor again — hold a round and ask," "they're a repeat buyer, warm up," "you can just ask — worst case is a no").
- **Anchor/floor calibration (COACH-001, COACH-002):** compare realized prices against the comp-anchored list to refine future list-price recommendations and floor-leak warnings.
- **Play attribution:** rank which OBJ/CONC plays close deals *and* earn good reviews (COACH-012), down-weighting plays that close but sour the relationship.
- **Closer correlation (COACH-012):** track which closing courtesies correlate with reviews and repeat buyers; bias future closes toward the winners.
- **Markdown cadence tuning (PRIN-038, COACH-021):** use days-on-market and demand signals to refine the relist/step-down schedule rather than reactive deep cuts.
- **Guardrail integrity (COACH-013, PRIN-044):** every fabricated-claim block and scam stop is logged for audit; these are never relaxed by the learning loop.
