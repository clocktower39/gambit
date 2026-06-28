# Book Profile — Getting to Yes

> Pass 1 extraction for the marketplace selling copilot (Depop / Vinted / Poshmark / eBay Best-Offer + platform-agnostic core). Product material, not a summary.
> Source-supported content is cited with a chapter/quote locator. Items marked **[INFERRED]** are synthesized mappings to the marketplace domain (not in the book).
> Role in the system: this book is the **ethical backbone + decision logic** layer. It does NOT supply message copy (that's Voss); it supplies *why* the copilot does what it does, *how to justify a price without it getting personal*, and *when to walk away*. Map "objective criteria" → comp/sold-price citation in chat. Map "BATNA" → the relist/hold decision and reservation price.

---

## 1. Metadata

- **title:** Getting to Yes: Negotiating Agreement Without Giving In (2nd ed.)
- **author:** Roger Fisher, William Ury, Bruce Patton
- **category:** principled-negotiation (interest-based / Harvard Negotiation Project)
- **domain_fit_note:** This is the decision-logic and ethics spine of the copilot, not its phrasebook. Its four principles (separate people from problem; interests over positions; invent options for mutual gain; insist on objective criteria) plus BATNA convert directly into the copilot's core moves: defuse personal heat in chat, decode the real interest behind a lowball, expand beyond price (bundles, shipping, terms), justify your number with sold comps so it isn't "you vs. them," and decide rationally when to relist/hold rather than cave. It is light on ready-to-send copy and assumes longer, higher-stakes, often multi-session negotiations — so for a $25 Depop sale it must be applied selectively, but its judgment layer is what keeps the copilot fair and un-manipulative.
- **applicability_score:** 4/5

---

## 2. Core thesis

Most people negotiate by **positional bargaining** — staking out a position, defending it, and grudgingly conceding toward a compromise — which is inefficient, damages relationships, and produces unwise outcomes because egos get welded to positions. The alternative, **principled negotiation** ("negotiation on the merits"), is hard on the merits and soft on the people, and rests on four moves: separate the people from the problem; focus on interests, not positions; invent options for mutual gain before deciding; and insist the result rest on objective criteria independent of either side's will. Your leverage in all of this comes not from stubbornness but from your **BATNA** (Best Alternative To a Negotiated Agreement) — the better your walk-away option, the more power you have, and any offer should be judged against it rather than against an arbitrary bottom line. When the other side won't play or fights dirty, you don't fight back in kind; you deflect their moves back onto interests and standards ("negotiation jujitsu"), name the tactic, and refuse to yield to pressure — only to principle.

---

## 3. Plays

```
- id: getting-to-yes-play-01
  principle: Separate the people from the problem
  what_it_means: Treat the buyer as a human being on the same side of the table as you, and treat the disagreement (the price/terms) as the shared problem you're both attacking — not each other.
  why_it_matters: Egos get entangled with positions; a comment on substance ("this is overpriced") is heard as a personal attack, triggering defensiveness and counterattack that kills the deal. Disentangling them lets you be firm on the number while warm to the person.
  when_to_use: Any chat that's getting tense; when a buyer takes your firm price personally; opening any haggling thread you want to keep cordial.
  when_NOT_to_use: When there's no friction at all (don't manufacture warmth that reads as fake); when the "person" is abusive/scam — that's a safety issue, not a relationship to preserve.
  marketplace_mapping: Framing replies as "us vs. the price gap" not "me vs. you"; pairing a firm no with genuine appreciation ("thanks for the interest, really"); keeping tone friendly in DMs/offer messages even while holding the line.
  example_buyer_message: "Come on, $45 is way too much, you're ripping people off."
  recommended_agent_reply: "I hear you — nobody wants to overpay, and I want you to feel good about this. Let's figure out together what a fair number looks like. Here's how I landed on $45…"
  source_quote_or_locator: "Ch. 2 'Separate the People from the Problem' — 'be hard on the merits, soft on the people'; 'partners in a hardheaded, side-by-side search for a fair agreement.'"
  product_stage_tags: [objection, trust, reply-gen, coaching]

- id: getting-to-yes-play-02
  principle: Focus on interests, not positions (decode the lowball)
  what_it_means: A buyer's stated position ("I'll give you $20") obscures the underlying interest (a budget cap, fear of overpaying, wanting it for an occasion, doubt about condition). Find the interest and you find moves that satisfy it without simply dropping price.
  why_it_matters: For every interest there are several positions that satisfy it; reconciling interests (not splitting positions) produces wiser deals and uncovers shared/complementary interests behind seemingly opposed numbers.
  when_to_use: Every lowball or "best price?" message; whenever a buyer fixates on one number; before you counter.
  when_NOT_to_use: When the interest is obvious and already met (don't interrogate a clean accept-able offer); on tiny items where the back-and-forth costs more than the gap.
  mechanic: 1) Don't react to the number. 2) Ask "why?" / "what were you hoping to spend?" / "what's this for?" 3) Classify the interest (budget cap vs. value-doubt vs. occasion/timing vs. comparison-shopping). 4) Pick the response lever that fits the interest, not the position (e.g., budget cap → bundle or terms; value-doubt → comps/proof; timing → ship-fast).
  marketplace_mapping: Replacing an instant counter on eBay/Posh Offer with one interest-probing question in chat first; using the answer to choose between price, bundle, shipping, or proof responses.
  example_buyer_message: "Would you take $20?" (listed $45)
  recommended_agent_reply: "Happy to work with you — what were you hoping to spend, and is this for something specific? Helps me see what I can do beyond just the number."
  source_quote_or_locator: "Ch. 3 'Focus on Interests, Not Positions' — the library window story; 'Your position is something you decided upon. Your interests are what caused you to so decide.'"
  product_stage_tags: [intent-detection, objection, pricing, reply-gen]

- id: getting-to-yes-play-03
  principle: Ask "Why?" and "Why not?" to surface the real need
  what_it_means: To uncover a buyer's interest, ask why they take their position, and also ask yourself why they haven't already said yes — what interest of theirs is blocking the purchase.
  why_it_matters: Positions are explicit; interests are usually unexpressed. Reconstructing the buyer's perceived choice ("if I say yes I lose X; if I say no I keep Y") tells you exactly what to change to make yes easy.
  when_to_use: Stalled threads; a saved/liked item that never converts; a buyer who keeps asking questions but won't commit.
  when_NOT_to_use: When you'd be putting words in their mouth on a fast clean sale; interrogating a ready buyer.
  marketplace_mapping: For a buyer who liked the item days ago: figure out the blocker (price? fit? shipping? trust?) and address that specific one rather than nudging generically.
  example_buyer_message: "Still thinking about it…"
  recommended_agent_reply: "Totally fair — what's the one thing holding you back? If it's fit or condition I can send more pics; if it's the price, tell me your ballpark and I'll see what's doable."
  source_quote_or_locator: "Ch. 3 'How do you identify interests? Ask Why? … Ask Why not? Think about their choice' — reconstruct the other side's 'presently perceived choice.'"
  product_stage_tags: [intent-detection, objection, reply-gen, learning-loop]

- id: getting-to-yes-play-04
  principle: Invent options for mutual gain (expand beyond price)
  what_it_means: Don't treat the deal as a fixed pie split along one axis (price). Generate several options that trade on differing interests — bundles, shipping splits, delayed/partial terms, add-ons — so both sides do better than a straight price cut.
  why_it_matters: Negotiators "leave money on the table" by assuming fixed-sum; differences in what each side values (peel vs. fruit) are exactly what makes win-win deals possible. A price cut costs you dollar-for-dollar; an option can be low-cost to you, high-value to them.
  when_to_use: Price is stuck but there's goodwill; multi-item interest; buyer wants a deal but you can't move much on the headline number.
  when_NOT_to_use: Single cheap item where complexity annoys; when the buyer explicitly only wants the one item at a lower price and nothing else has value to them.
  mechanic: 1) List what's cheap-to-you/valuable-to-them (free local pickup, free shipping by absorbing it, throwing in a low-value add-on, holding the item, bundling a slow-moving piece). 2) Offer 2+ options together so none reads as a committed concession. 3) Ask which they prefer, then refine.
  marketplace_mapping: "Add the matching top and I'll do both shipped for $X" (bundle); "I'll cover shipping instead of dropping the price" (Depop/Vinted shipping); "grab it now and I'll hold the other for a week."
  example_buyer_message: "$45 is more than I wanted to spend on just this."
  recommended_agent_reply: "Two ways we could make it work: I keep it at $45 but cover shipping, or if you add the grey hoodie you've liked I'll do the pair for $60 shipped. Which sounds better?"
  source_quote_or_locator: "Ch. 4 'Invent Options for Mutual Gain' — the orange/peel sisters; 'Look for items that are of low cost to you and high benefit to them, and vice versa… Vive la difference!'"
  product_stage_tags: [pricing, objection, reply-gen]

- id: getting-to-yes-play-05
  principle: Dovetail differences (trade on what each side values differently)
  what_it_means: Use differences in timing, certainty, and taste as the basis of a deal — e.g., buyer cares about paying later, you care about a higher total; buyer wants the slow-mover, you want it gone.
  why_it_matters: "Agreement is often based on disagreement." Different valuations, not shared ones, frequently unlock the deal; this is the engine behind bundles, installment-style holds, and clearing dead stock.
  when_to_use: When a flat price gap won't close but interests clearly diverge (urgency, item mix, payment timing).
  when_NOT_to_use: When platform rules forbid the mechanism (e.g., off-platform installments — keep it on-platform/safe).
  marketplace_mapping: Pairing a hot item with a stale-listing in a bundle; offering to hold for a payday the buyer mentioned (within platform rules); accepting a slightly lower price to clear inventory you value less than they do.
  example_buyer_message: "I love the boots but I also kind of want the bag, can't do both right now though."
  recommended_agent_reply: "How about this — take the boots now, and I'll hold the bag for you at today's price till Friday. You're not double-spending this week and I know they're both going to a good home."
  source_quote_or_locator: "Ch. 4 'Dovetail differing interests' — 'Differences in interests, beliefs, the value placed on time… make dovetailing possible.'"
  product_stage_tags: [pricing, objection, reply-gen, trust]

- id: getting-to-yes-play-06
  principle: Insist on objective criteria (cite sold comps, not opinion)
  what_it_means: Justify your price by an external standard — recent sold prices for the same item, condition/grading norms, retail-minus-depreciation, replacement cost — so the number rests on a fair standard, not your will vs. theirs.
  why_it_matters: Settling on will is costly and personal; an agreement grounded in a standard "is less vulnerable to attack," lets neither side feel browbeaten, and means conceding to the standard isn't conceding to *you*. This is the copilot's primary anti-"it's-personal" tool.
  when_to_use: Any price challenge, lowball, or "competitor's cheaper"; defending a firm price; whenever you'd otherwise be tempted to just say "no, that's my price."
  when_NOT_to_use: When you can't actually cite a real standard (never fabricate comps — guardrail); on items so unique no comp exists (pivot to interests/options instead).
  mechanic: 1) Frame it as a joint search: "let's figure out a fair price." 2) Offer the standard + the number, reasoning FIRST then the figure. 3) Invite their standard ("how did you get to your number?"). 4) If they propose a fair standard, use it as the lever. 5) Yield only to a better standard, never to pressure.
  marketplace_mapping: Citing eBay "Sold" filter range, Poshmark/Depop comparable sold listings, condition vs. a brand-new retail price; screenshotting a sold range in chat to depersonalize the number.
  example_buyer_message: "$45 is too much, nobody pays that."
  recommended_agent_reply: "Fair question — I based it on recent sold ones: the last three of these sold for $48–$55 in this condition (happy to screenshot). $45 is already under that. If you're seeing them cheaper somewhere, send me the link and I'll take a real look."
  source_quote_or_locator: "Ch. 5 'Insist on Using Objective Criteria' — 'Never yield to pressure, only to principle'; the insurance-adjuster case (Tom's totaled car) and 'What's your theory?'"
  product_stage_tags: [pricing, objection, trust, reply-gen]

- id: getting-to-yes-play-07
  principle: Ask "What's your theory?" before reacting to their number
  what_it_means: When a buyer throws out a price, don't accept or reject it — ask how they arrived at it. Treat their number as if it too is reaching for a fair standard.
  why_it_matters: It shifts the conversation from a clash of wills to a comparison of standards, exposes lowballs that have no basis (they look ridiculous when they can't justify them), and surfaces any legitimate comp they have that you should account for.
  when_to_use: Every offer that's below your number; "competitor cheaper" claims; aggressive anchors.
  when_NOT_to_use: On a reasonable offer you'd accept (just accept it); when it would read as combative on a trivial item.
  marketplace_mapping: Responding to a $20 eBay Offer with "what's that based on?" rather than an instant counter; asking a "saw it cheaper" buyer for the link/standard.
  example_buyer_message: "I'll do $20, that's what it's worth."
  recommended_agent_reply: "Genuinely curious how you got to $20 — is that from sold listings you've seen? I ask because the recent solds I'm looking at are higher, so if you've got better data I want to see it."
  source_quote_or_locator: "Ch. 5 'Ask “What's your theory?”' — 'If the seller starts by giving you a position… ask for the theory behind that price.'"
  product_stage_tags: [intent-detection, objection, pricing, reply-gen]

- id: getting-to-yes-play-08
  principle: Know your BATNA → set your reservation price (relist/hold)
  what_it_means: Before negotiating, decide what you'll do if this sale falls through — relist, wait for other interested buyers, cross-list elsewhere, or keep/use the item. The value of that best alternative, not a guessed-at floor, is what any offer must beat.
  why_it_matters: A BATNA is a smarter measure than an arbitrary bottom line (which is too rigid and usually mis-set); it tells you exactly when to walk, and a strong BATNA is itself your power — "the better your BATNA, the greater your power."
  when_to_use: Setting accept/counter/decline thresholds; deciding whether to take a sitting offer; any "this is my final" moment.
  when_NOT_to_use: As a static number — re-evaluate it as conditions change (item's been listed 60 days with no other interest = weaker BATNA = be more flexible).
  mechanic: 1) List alternatives if no sale (relist, hold, cross-list to other platform, keep). 2) Improve the best one (e.g., actually cross-list to check demand). 3) Pick the best → that's your walk-away. 4) Compare every offer to it. 5) Recompute as time/interest changes (a real "trip wire" price between BATNA and ideal triggers a re-think before accepting anything worse).
  marketplace_mapping: "If it doesn't sell at $40, I relist + cross-post to Vinted where similar go for ~$42" → reservation ≈ $40; an aging listing with zero saves → lower the reservation; multiple savers/watchers → raise it.
  example_buyer_message: "$30 take it or leave it." (your reservation is $40, item gets steady saves)
  recommended_agent_reply: "I appreciate the straight offer. At $30 I'd genuinely rather relist — it's getting steady interest at $45. I could meet you at $40 today, though, and we're done. Deal?"
  source_quote_or_locator: "Ch. 6 'What If They Are More Powerful? (Develop Your BATNA)' — 'The reason you negotiate is to produce something better than… without negotiating'; 'The better your BATNA, the greater your power.'"
  product_stage_tags: [pricing, coaching, metrics, learning-loop]

- id: getting-to-yes-play-09
  principle: Don't use a rigid bottom line; use a trip wire
  what_it_means: Instead of a hard, arbitrary "lowest I'll take," set a BATNA-based walk-away AND a slightly-better "trip wire" figure that triggers a pause-and-reconsider before you accept anything worse.
  why_it_matters: A fixed bottom line is set too high by wishful thinking, shuts your ears to what you learn mid-chat, and blocks creative term-based deals; a trip wire keeps flexibility while still protecting you from a regret-accept in the heat of the moment.
  when_to_use: Coaching the seller's thresholds; high-emotion fast haggles where they might cave; when a tempting-but-low offer lands.
  when_NOT_to_use: When a true firm floor is required (e.g., you literally can't sell below cost) — then a bottom line is appropriate.
  marketplace_mapping: Copilot holds a private "reconsider below $X" alert: if an incoming Offer dips under the trip wire, it prompts the seller "this is under your reconsider line — want to counter, hold for relist, or accept?" instead of one-tap accepting.
  example_buyer_message: "Final offer $32."
  recommended_agent_reply: "(copilot to seller) That's below your $38 reconsider line. Your relist alternative is ~$40 with active saves — suggest countering $38 or letting it ride. Want me to send a $38 counter?"
  source_quote_or_locator: "Ch. 6 'The cost of using a bottom line' & 'Formulate a trip wire' — 'A bottom line — by its very nature rigid — is almost certain to be too rigid.'"
  product_stage_tags: [pricing, coaching, safety, metrics]

- id: getting-to-yes-play-10
  principle: Consider — and shape — the buyer's BATNA
  what_it_means: Think about the buyer's best alternative (other listings, waiting, going without) and where they're over- or under-estimating it; gently correct an inflated one and highlight where yours is genuinely better.
  why_it_matters: Negotiating power is relative to each side's walk-away; a buyer threatening "I'll find it cheaper" may be overrating their alternative. Realistically framing it (without lying) lowers their leverage and their expectation.
  when_to_use: "Competitor cheaper" objections; buyers stalling on the assumption they have endless options; defending a premium for condition/authenticity/speed.
  when_NOT_to_use: To bluff about scarcity or fabricate competing buyers (guardrail — must be true).
  marketplace_mapping: "The cheaper ones are unauthenticated / worse condition / ship in 3 weeks" — differentiating your offer against their actual alternative; only mentioning real other-buyer interest.
  example_buyer_message: "I can get this cheaper on another account."
  recommended_agent_reply: "You might find a lower sticker — worth checking the condition and whether it's authenticated and ships fast, though. Mine's [authenticated/next-day]. If the cheaper one matches all that, honestly grab it; if not, $45 here is solid."
  source_quote_or_locator: "Ch. 6 'Consider the other side's BATNA' — 'If they appear to overestimate their BATNA, you will want to lower their expectations.'"
  product_stage_tags: [objection, pricing, competitor, reply-gen]

- id: getting-to-yes-play-11
  principle: Negotiation jujitsu — don't push back, redirect to merits
  what_it_means: When the buyer attacks your price, your idea, or you, don't defend or counterattack. Treat their position as one option, ask the interest behind it, invite criticism of yours, and recast personal attacks as attacks on the shared problem.
  why_it_matters: Pushing back locks both sides into positions and starts an attack/defense spiral. Deflecting their force onto interests and standards is how you get an unwilling, positional buyer to start negotiating on the merits without a fight.
  when_to_use: Buyer who states a flat position and won't engage; rude/aggressive messages; "you're ripping people off" type attacks.
  when_NOT_to_use: Genuine abuse/harassment or scam attempts — disengage/report (safety), don't jujitsu.
  mechanic: 1) Don't reject their position — ask what's behind it. 2) Don't defend yours — ask "what's wrong with it?" / "what would you do in my shoes?" 3) Recast attack-on-you as attack-on-problem ("sounds like the price feels unfair — let's find a number that is"). 4) Ask questions, not statements. 5) Use silence after a question — let it sit.
  marketplace_mapping: Turning "this is a scam price" into "what would feel fair to you, and why?"; answering an aggressive DM with a calm interest-question instead of a defense.
  example_buyer_message: "This is a joke, you're price gouging."
  recommended_agent_reply: "Sounds like the price feels off to you — I don't want it to feel unfair. What number would feel right, and what are you basing it on? If there's a fair standard I'm missing, I'll adjust."
  source_quote_or_locator: "Ch. 7 'What If They Won't Play? (Use Negotiation Jujitsu)' — 'Don't push back… sidestep their attack and deflect it against the problem'; 'Ask questions and pause. Silence is one of your best weapons.'"
  product_stage_tags: [objection, reply-gen, trust, safety]

- id: getting-to-yes-play-12
  principle: "Please correct me if I'm wrong" — open with a correctable claim
  what_it_means: State your key facts as something the buyer is invited to correct, not as an assertion, so the exchange starts as two colleagues establishing facts rather than a confrontation.
  why_it_matters: Asserting facts as facts makes the buyer defensive and they may deny them; framing them as correctable defuses confrontation, builds a reasoned dialogue, and saves face if you turn out to be wrong.
  when_to_use: Opening a price-justification, a condition disclosure, or any claim about comps/market the buyer might dispute.
  when_NOT_to_use: When false modesty would undercut a clear, verifiable fact the buyer is exploiting (don't invite "correction" of your authenticity proof).
  marketplace_mapping: "Correct me if I'm wrong, but the last few of these sold around $50?" before quoting your price; "tell me if I've misread the listing, but I think the size you need is the M?"
  example_buyer_message: "Your price makes no sense for a used item."
  recommended_agent_reply: "Correct me if I'm off here — but for this brand in this condition, the recent sold ones I've seen are $48–$55. If you're seeing them go for less, point me to it and I'll rethink the $45."
  source_quote_or_locator: "Ch. 7 Turnbull/Jones dialogue — '“Please correct me if I'm wrong”… establishes a dialogue based on reason… The confrontation is defused.'"
  product_stage_tags: [objection, trust, pricing, reply-gen]

- id: getting-to-yes-play-13
  principle: "Trust is a separate issue" — don't let appeals to trust force a concession
  what_it_means: When a buyer (or seller's own guilt) frames the deal as a matter of trusting them, decouple trust from the substance: handle the transaction on verifiable terms and standards regardless of trust.
  why_it_matters: "You don't trust me?" is a manipulation that corners you into either looking suspicious or giving in. Naming trust as irrelevant to the question ("did we land on a fair price?") slips the corner without insulting them.
  when_to_use: "Just trust me" pressure; requests to take a claim on faith; off-platform "I'm honest, pay me directly" pushes.
  when_NOT_to_use: Where trust genuinely is the product (authenticity guarantees) — there you provide proof, not a brush-off.
  marketplace_mapping: Declining off-platform payment ("not about trust — the app protects us both"); insisting on tracked shipping; verifying a buyer's "I always pay" with platform's normal process.
  example_buyer_message: "Just send it first and I'll pay you after, you can trust me."
  recommended_agent_reply: "It's honestly not a trust thing — I keep everything through the app so we're both covered if anything goes sideways. Buy it here and it ships same day."
  source_quote_or_locator: "Ch. 7 Turnbull/Jones — '“Trust is a separate issue.” … defining the question of trust as irrelevant.'"
  product_stage_tags: [objection, trust, safety, reply-gen]

- id: getting-to-yes-play-14
  principle: Name the dirty trick, then negotiate the rules
  what_it_means: When you spot a manipulative tactic (fake "other offer," escalating demands after a deal, "my partner won't allow it," extreme anchor, calculated delay), recognize it, raise it gently and explicitly, and question its legitimacy rather than silently absorbing it or retaliating.
  why_it_matters: The two reflex responses — tolerate it (you lose) or retaliate (deal blows up) — both fail. Tricks are illegitimate because they fail reciprocity; just naming a tactic often neutralizes it, and reframing it as a "rule" exposes its unfairness.
  when_to_use: Post-agreement demand creep ("ok but also throw in…"); "another buyer offered more" with no proof; sudden "my husband says no lower than…"; absurd anchors; stall-then-pressure.
  when_NOT_to_use: When it's not actually a tactic (a buyer genuinely consulting a partner is fine) — don't accuse; raise it as a possibility.
  mechanic: 1) Recognize it. 2) Surface it lightly ("I might be misreading, but it feels like the deal keeps moving"). 3) Ask for the principle / apply reciprocity ("would that feel fair if I did it to you?"). 4) Refuse to yield to the pressure; offer to proceed on the agreed basis or walk to BATNA.
  marketplace_mapping: When a buyer adds conditions after you accept their offer: "We'd agreed $40 shipped — happy to honor that. The extra ask is a new deal; I can't keep adding in. Still want it at $40?"; calling out an unverifiable "someone offered $60" calmly.
  example_buyer_message: "Ok deal at $40 — oh and can you also include the belt and do free express shipping?"
  recommended_agent_reply: "Glad we're aligned on $40! The belt and express are a bigger ask though — that'd be a different deal. I can do the original $40 shipped standard as agreed. Want me to send the invoice for that?"
  source_quote_or_locator: "Ch. 8 'What If They Use Dirty Tricks?' — 'recognize the tactic, raise the issue explicitly, and question the tactic's legitimacy'; escalating-demands (Malta) and hardhearted-partner examples."
  product_stage_tags: [objection, safety, reply-gen, pricing]

- id: getting-to-yes-play-15
  principle: Give reasons before the number; make their "yes" easy
  what_it_means: Present your interests/reasoning first and the proposal/figure second, and shape the final ask as a simple, fair "yesable proposition" the buyer can accept in one word.
  why_it_matters: Lead with a number and the buyer stops listening and starts countering; lead with reasoning and they follow you to the conclusion. Framing the close as one easy, legitimate yes (and being generous at the very end) clinches deals.
  when_to_use: Sending a counter or final price; closing a long haggle; any moment you want acceptance not more back-and-forth.
  when_NOT_to_use: Over-explaining a trivial price (reads as defensive); burying a simple accept under a paragraph.
  mechanic: 1) Reasoning/standard first. 2) Then the concrete figure as "one fair solution," not "my position." 3) Make it a single yes/no. 4) At the close, add a small genuine sweetener framed as final ("and I'll cover shipping to seal it").
  marketplace_mapping: "Sold ones are $48–55, mine's clean and ships tomorrow — so one fair option: $45 and I cover shipping. Want it?"; ending with a small add-on rather than another price drop.
  example_buyer_message: "So what's your actual best?"
  recommended_agent_reply: "Given the condition and that comparable ones sell for $48–55, here's a fair one: $44 shipped, and I'll toss in the dust bag. That work?"
  source_quote_or_locator: "Ch. 3 'Put the problem before your answer' + Ch. 4 'yesable proposition' + Q8 'Be generous at the end.'"
  product_stage_tags: [pricing, reply-gen, objection]

- id: getting-to-yes-play-16
  principle: Look forward, not back (drop the grievance loop)
  what_it_means: Steer away from re-litigating past friction ("you said it was available yesterday," "you lowballed me last time") toward what you both want to happen now.
  why_it_matters: People reflexively react to past acts and score points instead of pursuing their interest; future-focused framing ("who does what now?") keeps the deal moving and the relationship intact.
  when_to_use: A buyer relitigating a prior message, a delayed reply, or an earlier price; reviving a thread that soured.
  when_NOT_to_use: When a past fact is materially relevant to safety/trust (a real prior scam attempt shouldn't be waved off).
  marketplace_mapping: After a slow reply or a price misunderstanding: acknowledge briefly, then pivot to "here's what I can do right now."
  example_buyer_message: "You ignored me for two days and now it's still here."
  recommended_agent_reply: "Sorry for the slow reply — that's on me. Good news is it's still available and yours if you want it. Want me to send it out today?"
  source_quote_or_locator: "Ch. 3 'Look forward, not back' — 'talk about where you would like to go rather than… where you have come from… Who should do what tomorrow?'"
  product_stage_tags: [reply-gen, objection, trust, stalling]
```

---

## 4. Communication tactics (phrase-level)

| name | purpose | phrase_patterns | overuse_risk | good_example | bad_example | source_locator |
|---|---|---|---|---|---|---|
| Correctable-claim opener | defuse confrontation, start on reason | "Correct me if I'm wrong, but ___?" / "Tell me if I've misread this, ___" | Sounds unsure if used on solid proof; weakens authenticity claims | "Correct me if I'm wrong, but the last few sold around $50?" | "Correct me if I'm wrong, but this is 100% real" (undercuts your own proof) | Ch. 7 Turnbull dialogue |
| "What's your theory?" | shift number to a standard | "How did you get to that number?" / "What's that based on?" | Reads combative on a fair offer or tiny item | "Curious how you landed on $20 — sold listings?" | "Why would you even offer that?" (accusatory) | Ch. 5 'Ask What's your theory?' |
| Joint-search framing | depersonalize price | "Let's figure out a fair price together" / "What standard should we use?" | Over-formal for a $10 sale | "You want low, I want fair — let's find the number the comps support" | "My price is my price." | Ch. 5 'Frame each issue as a joint search' |
| Reasoning-first | get them to listen | "Here's why, then the number: ___" | Over-explaining trivial prices | "Condition's clean, solds are $50, so $45 is fair" | leading with "$45." then justifying | Ch. 3 'Put the problem before your answer' |
| "One fair solution might be…" | propose without locking in | "One fair option could be ___ — does that sound fair?" | Stacking too many tentative options confuses | "One fair option: $44 shipped. Fair?" | "Final answer, $44, take it." (positional) | Ch. 7 Turnbull '"One fair solution might be…"' |
| "Trust is a separate issue" | block trust-based pressure | "It's not about trust — it's about ___ (the app protecting us / a fair number)" | Sounds cold if buyer's worry is genuine | "Not a trust thing — the app covers us both" | "I don't trust you, so no." | Ch. 7 Turnbull '"Trust is a separate issue"' |
| Recast attack as problem | de-escalate | "Sounds like the price feels unfair — let's find one that is" | Feels scripted if every message | "Sounds like it feels steep — what would feel fair?" | "Don't call me a scammer." (counterattack) | Ch. 7 'Recast an attack on you as an attack on the problem' |
| "Why would you do it in my shoes?" | invite their advice/criticism | "If you were selling this, what would you do?" / "What's wrong with this option?" | Buyer may exploit it to push lower | "If you were me at these comps, what'd you price it?" | none needed | Ch. 7 'Don't defend your ideas, invite criticism' |
| Question + silence | make them fill the gap | ask one open question, then stop typing | Looks like ghosting if overused | "What were you hoping to spend?" (then wait) | rapid-fire follow-ups that answer for them | Ch. 7 'Ask questions and pause' |
| Reciprocity test (anti-trick) | expose an unfair move | "Would that feel fair if I did it to you?" / "Is that the rule we're both playing by?" | Accusatory if it isn't actually a trick | "We'd agreed $40 — is adding asks after a deal fair both ways?" | "Stop trying to scam me." | Ch. 8 'Try out the principle of reciprocity on them' |
| Generous-final-gesture | clinch the close | "To seal it, I'll also ___ — but that's my final" | Trains buyers to expect endless extras if repeated | "$45 and I'll cover shipping to close it out" | dropping price again after "final" | Q8 'Be generous at the end' |

---

## 5. Objection material

| objection_key | book's recommended handling | sample_reply |
|---|---|---|
| **lowball** | Don't counter the number — ask the interest/theory behind it (Ch. 3, Ch. 5), reframe to a joint search for a fair price, then anchor on objective comps. | "Happy to work with you — how'd you get to $20? The recent sold ones run $48–55, so $20's a stretch, but tell me your real budget and what it's for and I'll see what's doable." |
| **price-too-high** | Insist on objective criteria: justify with sold comps/condition, reasoning first, number second; never yield to pressure, only to principle. (Ch. 5, Ch. 3) | "Totally fair to push on price. I set $45 off the last few solds ($48–55) and the condition — so it's already under market. If price is the blocker, I can cover shipping or bundle to add value." |
| **is-it-available** | Treat as a buying signal; answer warmly then move forward with one interest question (look forward, not back). (Ch. 2, Ch. 3) | "Yes it is! Were you looking to grab it now, or is there anything about it you want to check first?" |
| **competitor-cheaper** | Consider/shape their BATNA: don't disparage, differentiate on the real alternative (condition, authenticity, ship speed); ask for their standard. (Ch. 6, Ch. 5) | "You might find a lower sticker — worth checking it's the same condition, authenticated, and ships fast. Mine is. If the cheaper one matches all that, grab it; if not, $45 here is solid." |
| **condition-doubt** | Trust is a separate issue → provide proof, not reassurance; use objective condition standards; invite "correct me if I'm wrong." (Ch. 7, Ch. 5) | "Good to be careful. Rather than just say 'it's fine' — here are close-ups of the seams and sole, and I'd grade it 8/10. Anything specific you want a photo of?" |
| **shipping-cost** | Invent options / dovetail: absorb shipping instead of cutting price, or fold into one flat number (a low-cost-to-you, high-value-to-them trade). (Ch. 4) | "How about I build shipping into one flat $48 so there are no surprises at checkout? Often works out better than a price drop plus postage." |
| **wants-bundle-deal** | Expand the pie: invent multi-item options, pair slow movers with wanted items, present 2+ options and ask preference. (Ch. 4) | "Love a bundle. Add the grey tee you liked and I'll do both for $60 shipped, or keep it to this one at $45 + free shipping — which works better?" |
| **stalling-ghosting** | Ask "why not?" to find the real blocker; look forward; make the next yes easy. (Ch. 3) | "No rush — what's the one thing holding you back? If it's fit I'll send pics, if it's price tell me your ballpark. Happy to make it easy either way." |
| **off-platform-request** | Trust is a separate issue + safety: decline on principle (mutual protection), not suspicion; keep it on-platform. (Ch. 7) | "Not a trust thing at all — I just keep everything through the app so we're both protected. Checkout here and it ships today." |
| **trust-authenticity** | Provide objective proof/standards; decouple from personal trust; reasoning-first. (Ch. 5, Ch. 7) | "Fair to want certainty. It comes with the receipt and the authentication tag — here's a photo of both. Want any other angle before you decide?" |
| **rude-aggressive** | Negotiation jujitsu: don't counterattack; recast the attack as the shared problem; one calm question + silence. Escalate to safety only if abusive. (Ch. 7) | "Sounds like the price feels way off to you — I don't want it to feel unfair. What would feel right, and what's it based on? Happy to talk it through, but I can't do $15." |
| **escalating-demands (post-deal)** | Name the trick, apply reciprocity, hold to the agreed basis or walk to BATNA. (Ch. 8) | "Glad we agreed on $40! The extra asks are a new deal though — I can do the original $40 shipped as agreed. Want the invoice for that?" |

---

## 6. Buyer psychology insights

- A buyer's stated **position is not their interest** — "$20" usually masks a budget cap, a value-doubt, a deadline, or a comparison they've made; the real lever is the interest, not the number. (Ch. 3)
- The **most powerful interests are basic human needs**: security (won't get scammed), economic well-being (a fair deal), recognition (being treated as an equal, not bullied), and control over the decision. A buyer will reject a numerically fine deal that wounds these. (Ch. 3)
- Buyers **confuse their perception with reality** and read tone/intent into neutral statements; "your price is high" is partly about feeling respected, not just the figure. (Ch. 2)
- Buyers (and sellers) **over-estimate their own BATNA** ("I'll just find it cheaper") and feel the *sum* of vague alternatives, not the one they'd actually have to pick. (Ch. 6)
- A buyer **anchors on the first number** and often judges success by how far you moved off your asking price, regardless of true value. (Q7 'How high should I start?')
- People want to **save face** — they'll reject a fair outcome that makes them look like they backed down, but accept the same terms framed as their own reasonable decision. (Ch. 2)
- **Participation creates buy-in**: a buyer who helped arrive at the price (you asked their view, used their standard) defends and honors the deal far more than one handed a take-it-or-leave-it. (Ch. 2 'In a sense, the process is the product.')

---

## 7. Seller psychology insights (mistakes the copilot should counter)

- **Soft positional bargaining**: being "nice" and conceding to avoid confrontation gets the seller exploited by a hard bargainer. Counter: be hard on the merits (comps, BATNA), soft on the person. (Ch. 1)
- **Setting an arbitrary bottom line** (wishful, set too high or too low) instead of a real BATNA — leads to both bad accepts and bad rejects. Counter: compute relist/hold value and a trip wire. (Ch. 6)
- **Neediness / over-attachment to closing this sale** ("just agree and end this") makes sellers cave; an unexamined BATNA means negotiating "with your eyes closed." Counter: surface the walk-away. (Ch. 6)
- **Treating price disputes as personal attacks** and counter-punching — entangles people with problem and tanks deals. Counter: jujitsu + separate people from problem. (Ch. 2, Ch. 7)
- **Reflexive splitting-the-difference** of two arbitrary numbers — produces an arbitrary result. Counter: split only between figures each backed by a real standard, or use options. (Ch. 5, Q8)
- **Leading with the number / over-defending it** — buyer stops listening and counters. Counter: reasoning-first, then a yesable figure. (Ch. 3)
- **Tolerating dirty tricks silently** (demand creep, fake other-offers) hoping to keep the peace — invites more. Counter: name it, reciprocity test, hold to principle. (Ch. 8)
- **Fabricating fairness/standards or scarcity** to win — destroys the reputation asset that makes future creative deals possible, and may bring regret. Counter: only cite real comps/real interest. (Q3, guardrails)

---

## 8. Ignore-list (considered, deliberately dropped)

- **International diplomacy / arms-control / multilateral (150-nation) examples** (Sinai, Law of the Sea, Camp David, Iran hostages) — used only to extract the underlying mechanic; the geopolitics is irrelevant to a $30 resale. (Ch. 3–7)
- **The One-Text Procedure / formal mediator with 20+ drafts** — assumes a neutral third party and many rounds; overkill for two-party P2P chat. The lightweight idea (offer a draft, invite criticism) is retained inside plays 11/15. (Ch. 7)
- **Brainstorming-session logistics** (5–8 people, facilitator, blackboard, off-the-record rules) — the *output* (invent options before deciding) is kept; the workshop apparatus is dropped. (Ch. 4)
- **Framework / written contract drafting, constituencies, "boss approval" chains** — enterprise/labor/legal machinery with no analog for a casual seller. (Q8, Ch. 3)
- **Negotiating with terrorists / Hitler / hostage refusal-to-negotiate** — wrong stakes; only the "refusal to negotiate is a ploy" insight is generalized into stalling/safety handling. (Q5, Ch. 8)
- **Lock-in / commitment-via-irrevocability tactics** (dynamite-truck steering wheel) — too brinkmanlike and trust-damaging for marketplace chat; noted only so synthesis knows it was considered. (Ch. 8)
- **Gender/culture/personality adjustment essay (Q6)** — kept at a high level (question your assumptions, listen) but no buyer-typing model is offered by this book (see Section 10).

---

## 9. Guardrail flags

- **No fabricated objective criteria.** Plays 06/07/12 depend on *real* sold comps and condition standards. The copilot must never invent a "sold range," cite a fake "GM/last-week bill of sale" style precedent, or screenshot doctored data. Flag any comp claim for a truthfulness check; if no real comp exists, pivot to interests/options instead. (Ch. 5, Q3)
- **No fake BATNA / fake scarcity.** Plays 08/10 (and "other interested buyers," "I'll relist") must reflect true alternatives and true watcher/save interest. Bluffing a competing buyer or an imminent relist is a trust-and-safety risk. (Ch. 6)
- **"Worsening their BATNA" stays benign.** The book notes you can lower the other side's alternative (Q10 lawn-mowing example); the copilot must only do this via honest differentiation (condition/authenticity/speed), never coercion, threats, or disparaging false claims about competitors. (Q10)
- **Don't weaponize "fairness" or "trust."** Principled framing is for reaching fair deals, not guilt-tripping; "trust is a separate issue" is a boundary tool, not a way to dodge legitimate proof obligations. (Q3, Ch. 7)
- **Be fair even when you don't have to be.** The book explicitly warns that an unfair windfall risks repudiation, reputation, and regret (the Weimar-marks rug story). The copilot should not coach extracting more than the seller can justify as fair, especially against inexperienced buyers. (Q3)
- **Safety overrides jujitsu.** Plays 11/13/16 de-escalate friction, but genuine abuse, harassment, or scam attempts are not "people problems to preserve a relationship" — route to decline/report, don't keep redirecting to merits. (Ch. 7–8)

---

## 10. Classifiers & personas

> Getting to Yes offers **no formal buyer-typing or style taxonomy** (unlike Voss's Analyst/Accommodator/Assertive or Shell's styles). It explicitly resists personality typing (Q6: "question your assumptions… all of us have special interests and qualities that do not fit any standard mold"). What it *does* give is a small set of **synthesized situational classifiers** below — derived from its concepts, not named types in the book — useful for routing the copilot's response.

| name | signals (observable in chat/behavior) | recommended_approach | source_locator |
|---|---|---|---|
| Positional bargainer (won't engage on merits) **[INFERRED type]** | States a flat number/demand, repeats it, ignores questions, frames it as will ("that's my price / final"), no reasons given. | Negotiation jujitsu: don't reject — ask the interest/theory behind it, invite criticism of yours, question + silence; shift to objective criteria. (plays 07, 11) | Ch. 7 'Negotiation jujitsu' |
| Interest-revealing buyer **[INFERRED type]** | Volunteers context — "it's for a gift," "on a student budget," "been looking for this size." | Reconcile the interest, not the position: pick the lever (bundle/terms/proof/ship-fast) that fits; expand options. (plays 02, 04, 05) | Ch. 3 'Focus on Interests' |
| Trick-using / pressure buyer **[INFERRED type]** | Demand creep after a deal, "another buyer offered more" (unproven), "my partner won't allow," extreme anchor, stall-then-rush. | Name the tactic gently, apply reciprocity test, hold to the agreed basis or walk to BATNA; never tolerate silently or retaliate. (play 14) | Ch. 8 'Dirty Tricks' |
| Trust-appealing buyer **[INFERRED type]** | "Just trust me," off-platform pay request, "I'm honest," resistance to normal process. | "Trust is a separate issue" — handle on verifiable terms/safety, provide proof not faith, keep on-platform. (play 13) | Ch. 7 '"Trust is a separate issue"' |
| Seller-state: needy/over-attached **[INFERRED — coaching target]** | (Our user) keeps dropping price, splits the difference fast, anxious to close, no walk-away in mind. | Surface BATNA + trip wire before they cave; coach reasoning-first and hold-the-line. (plays 08, 09) | Ch. 6 'BATNA' |

> Underlying decision principle for all of the above (book-supported): diagnose the **situation and interest**, not the personality — "be optimistic, let your reach exceed your grasp," and tailor the approach to specific circumstances rather than a fixed type. (Q6, Q10)

---

*Locators reference the chapter titles/sections of the 2nd-edition (Fisher, Ury & Patton) text as present in the source file: Ch. 1 Don't Bargain Over Positions; Ch. 2 Separate the People; Ch. 3 Focus on Interests; Ch. 4 Invent Options; Ch. 5 Objective Criteria; Ch. 6 BATNA; Ch. 7 Negotiation Jujitsu / Turnbull-Jones dialogue; Ch. 8 Dirty Tricks; Q1–Q10 "Ten Questions People Ask." Plays 01–16 are source-supported principles re-mapped to marketplace chat; marketplace_mapping / example_buyer_message / recommended_agent_reply lines are the inferred product layer. Section 10 types are explicitly synthesized — the book offers no native persona model.*
