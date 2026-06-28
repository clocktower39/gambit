# Gambit — Conversation Capture (for consolidation)

> **Status:** raw capture, not final docs. Everything below came out of the design/build
> conversation for the **Gambit** auto-negotiator (AIEWF 2026 hackathon). To be merged with
> the other apps'/conversations' captures during consolidation. Some pieces (the Tier-2
> verifier, reward-integrity work, the Haggle→Gambit rename) originated in *parallel* sessions
> co-developing the same repo — consolidation should reconcile those too.

---

## 1. Project at a glance
- **Gambit** (formerly "Haggle"): a **self-improving auto-negotiator**. It lists an item, negotiates with buyers to get the best price in a reasonable time, and **gets better from its own past negotiations** — no human labeling.
- Inputs: item + photo + min / max / target price.
- One-line pitch: *"Same item, same buyer, same hidden budget — the day-one agent closes at \$448; after learning from its own negotiations, zero human labels, it closes the identical buyer at \$471 and more than doubles its surplus on buyers it's never seen."*
- Python package `gambit/`; repo `/Users/mattkearns/Programming/Projects/2026-hackathon`; branch `phase-1-core`.

## 2. Hackathon context & constraints
- **Event:** AI Engineer World's Fair Hackathon 2026 (Cerebral Valley), Shack15, SF.
- **Timeline:** hacking Sat 2026-06-27 11:30am → **submissions due Sun 2026-06-28 12:00pm PT**.
- **Team:** 2–4 people; **risk appetite = "play it safe"** (reliable live demo over max ambition).
- **Hard rules:** repo must be **public**; **new work only**; demo must clearly isolate what was built during the event (or DQ); 1-minute demo video required.
- **Banned project types** (we deliberately avoid all): basic RAG, Streamlit apps, image analyzers, **any project where a dashboard is the main feature**, analyzers/coaches/advisors/screeners. → Gambit is an *active agentic system that does work and self-improves*, not a dashboard.

## 3. Theme fit & judging strategy
- **Theme chosen: Continual Learning** — "improve from real-world use via memory, self-reflection, prompt/strategy optimization; become more useful the more it's used." Gambit matches this almost verbatim.
  - (Considered & rejected: Recursive Intelligence / weight-level RSI as the *primary* frame — kept only as the optional Gemma LoRA stretch. The Self-Improvement Stack is an adjacent secondary fit.)
- **Judging weights:** Technicality **40%**, Creativity/Originality **25%**, Live Demo **20%**, Future Potential **15%**.
- **Strategic read:** optimize for *technically ambitious + never-seen + works live in 3 min*. The killer demo is a system that **visibly improves itself** (or clean before/after). Technicality signals (verifiable reward, integrity guard, standing on 2026 papers) directly target the 40%.

## 4. Prize-stacking strategy (one project, four targets)
| Target | How |
|---|---|
| **Continual Learning** theme | self-improving negotiation policy + memory + self-reflection |
| **Best DigitalOcean** | Serverless Inference (agent + buyer-sim + verifier), pgvector memory (managed Postgres), image gen for listings (gpt-image-2 / SD-3.5 / fal flux), App Platform deploy, Spaces |
| **Best LiveKit** | **seller-facing voice intake + live item showcase** (talk about the item, agent builds the listing live) — explicitly NOT buyer haggling |
| **Best Gemini $5k** | Gemma 4 LoRA fine-tune on winning transcripts (stretch) + Gemini 3.5 computer-use auto-post; image gen via DO replaces Nano Banana ("same concept, different generator") |

## 5. Marketplace / ToS decision (THE critical call)
- **Do NOT automate Facebook Marketplace / Messenger.** No public consumer API; Meta ToS prohibits bots/scraping; the hackathon DQs platform-policy violations → risks both account ban and disqualification. The riskiest, least-reproducible integration must not be the load-bearing demo.
- **Build marketplace-agnostic** behind a connector interface.
- **Real-platform proof = eBay (Sandbox):** the one big marketplace with an official listing API + native Best Offer negotiation + sandbox test buyers/sellers → real list→offer→counter→accept flow, no real money, no ToS risk.
  - **Decisive technical detail:** use the **legacy Trading API (XML)** for BOTH listing (`AddFixedPriceItem` with `BestOfferEnabled`) and the negotiation loop (`GetBestOffers` / `RespondToBestOffer` / `PlaceOffer`). The modern REST "Negotiation API" is seller-initiated only and half-broken in Sandbox — a trap.
  - Auth: OAuth **user** tokens (not app tokens), 2 sandbox test users (eBay forbids buying your own listing), 5-min auth codes, store the ~18-mo refresh token. ~1–2 hrs setup; sandbox keysets are instant (no approval).
  - Top gotchas: Trading-API-only negotiation; OAuth + two-user friction; sandbox flakiness + listing-field landmines (get one listing live in the first 1–2 hrs; keep a manual sandbox.ebay.com fallback).
  - Free-text Q&A also available (`GetMemberMessages` / `AddMemberMessageRTQ`).
  - Full runbook: `docs/ebay.md`.
- **Learning engine + reproducible stage demo = the buyer simulator** (controlled buyers, ground-truth willingness-to-pay, deterministic head-to-head).
- **Alternatives evaluated:** Reverb = strong backup (real offers/negotiation API + official Offer Bot) but **no sandbox** (live only). Etsy/Shopify: listing APIs but no buyer↔seller negotiation. Mercari/OfferUp/Craigslist: no usable API, automation prohibited.

## 6. System architecture (modules in `gambit/`)
- `models.py` — `Item`, `BuyerPersona` (hidden `budget_ratio`), `Strategy` (the policy), `Message` (`offer` binding ⊥ `text` dialogue ⊥ `reasoning` hidden), `Episode`, `Outcome`; `budget_of()` (sim-only ground truth).
- `personas.py` — fixture items + 5 buyer personas; **TRAIN_PERSONAS vs HOLDOUT_PERSONAS** split. Tire-kicker Tess is infeasible on every item by design (tests "walk away early").
- `seller_agent.py` — the negotiator; LLM path + deterministic offline heuristic; emits hidden reasoning never shown to the buyer.
- `buyer_sim.py` — adversarial buyer simulator (reservation-enforced; never pays above hidden budget).
- `negotiation.py` — runs one episode, computes Outcome (surplus, skill).
- `metrics.py` — verifiable surplus **reward** + Tier-1 `audit_episode` integrity guard + metric panel + `summarize`.
- `verifier.py` — Tier-2 BINEVAL binary-question auditor (stronger model + deterministic offline subset) + `audit_run`.
- `optimizer.py` — the self-improvement brain: offline multi-knob search + LLM `propose_llm` (targeted lessons), `merge_tactics` anti-bloat; **now consumes verifier feedback**.
- `improve_loop.py` — generational loop, train/holdout eval, **held-out early-stop**, `head_to_head`.
- `opponent.py` — opponent modeling + belief calibration (NEW).
- `inference.py` — DigitalOcean Serverless Inference (OpenAI-compatible) client; tolerant JSON.
- `config.py` — env/settings; `llm_available()`; offline mode.
- `storage.py` — persistence (Postgres/pgvector + local fallback).
- `scripts/run_demo.py` — the end-to-end demo CLI.

## 7. The self-learning loop
```
Strategy ─► SellerAgent ⇄ BuyerSimulator ─► Episodes ─► verifiable Reward
   ▲                                                         │
   └──────── Optimizer ◄── reflect on wins/losses + rubric ──┘
        (rewrites tactics + tunes knobs; keeps only what scores higher)
```
- **Strategy** = the optimized policy: `opening_anchor_ratio`, `concession_rate`, `accept_ratio`, `walkaway_patience`, `urgency`, free-text `tactics`.
- **Selection = mean verifiable surplus reward** across episodes; promote a generation only if it scores higher.
- **Offline mode** = deterministic heuristics + multi-knob search → runs with **no API key** (pipeline validation + API-free stage fallback). LLM mode upgrades automatically when `DIGITAL_OCEAN_MODEL_ACCESS_KEY` is set.
- Self-improvement mechanisms: strategy/prompt optimization + self-reflection (+ planned pgvector case memory).

## 8. Reward design & integrity rails (the research-grounded heart)
- **PRIMARY reward = deterministic verifiable surplus from the secret floor** `(price − floor)/(list − floor)`, NOT an LLM judge. Removes judge bias/variance/cost and is itself the best anti-reward-hacking defense (the judge would be the hackable component).
- **Terminal shaping:** −1 integrity violation (below floor / hallucinated close / leak) · **0 neutral for no-deal/walk-away** (don't punish walking from a bad buyer) · surplus ∈ [0,1] on a deal.
- **Load-bearing nuance:** binary/LLM evaluators give **dense qualitative feedback** to the optimizer but **NEVER select**. Money-moving selection stays on verifiable surplus.
- **Three-tier reward-integrity guard** (patterns borrowed from `hud-trace-explorer`; do NOT adopt HUD itself — re-implement patterns):
  - **Tier 1 (done):** deterministic transcript audit — price ≥ floor, no sub-floor seller offer, agreed price present in transcript, deal-flag consistent. Shows as `viol=0%`.
  - **Tier 2 (done):** BINEVAL binary-question checklist (floor leak? below floor? hallucinated price? buyer out-of-character? misrepresentation?), each with verdict + reason, run on a **different/stronger model** than the optimizer. Visible audit artifact.
  - **Tier 3 (done):** score each generation on a **held-out buyer population**; non-transferring gains → early-stop (anti-overfit / anti-collapse).
- **Prompt-bloat mitigation** (BINEVAL: gains peak at 1–2 iters then collapse as the prompt balloons): `merge_tactics` extracts ≤3 generalized lessons, dedups, caps length — **targeted edits, not rewrite-from-scratch**.
- **Verifier→optimizer wiring (added this conversation):** `propose_llm` audits the worst transcripts and turns each flag into a targeted lesson.

## 9. Research grounding — the 2026 negotiation-RL frontier ("stand on giants")
- **Thesis:** 2026 negotiation is moving from *prompted haggling bots* → *RL-trained agents in verifiable bargaining environments*. Winning recipe = structured action space + NL channel + private information + verifiable-outcome reward + GRPO/RLVR-style optimization.
- **Canonical papers & what we took:**
  - **RLVR — Instructing LLMs to Negotiate w/ Verifiable Rewards (arXiv:2604.09855):** verifiable surplus reward (not LLM judge), terminal shaping, reservation-enforced sim, `<reasoning>/<dialogue>/<action>` schema, strategic phase changes (naive→aggressive anchoring→deadlock→rational concession). Buyer-side mirror of Gambit's seller side. → adopted as the core.
  - **Training LMs for Bilateral Trade w/ Private Information (arXiv:2604.16472):** separate **binding structured offers** from NL messages; surplus↔deal-rate tension; SFT+GRPO on Qwen. → our `Message.offer ⊥ text`.
  - **BINEVAL (arXiv:2606.27226):** decompose fuzzy judgment into atomic binary checks; prompt-opt collapse. → Tier-2 verifier + anti-bloat.
  - **TERMS-Bench (arXiv:2605.13909):** eval beyond deal-rate — belief calibration, type inference, compliance, surplus. → `opponent.py`.
  - **AgenticPay (arXiv:2602.06008):** Gymnasium-like buyer-seller benchmark; JSON contracts, memory, opponent modeling, many-to-many. → opponent modeling + roadmap.
  - Adjacent/aware: Learning to Negotiate (2603.10476), PieArena (2602.05302), Self-Driving Negotiator (2606.15139), LLM-X (2605.11376), Surrogate Goals for Safer Bargaining (2604.04341), Personality Engineering (2605.20554), SoK Security of Agentic Commerce (2604.15367), Universal Commerce Protocol (Google, Jan 2026).
- **Commercial landscape:** academic frontier richer than commercial; clearest wedge = procurement/tail-spend. Players: **Nibble** (procurement AI negotiator, 2M+ negotiations, Coupa/Ariba), **Pactum** (Walmart vendor negotiations).
- **The 8-component "serious negotiator" build thesis:** (1) structured contract actions (JSON), (2) NL strategy channel, (3) private constraints, (4) verifiable reward, (5) BINEVAL-like binary rubric layer, (6) opponent model, (7) authorization layer (commitment/disclosure/escalation boundaries), (8) audit trail. **Don't use LLM judgment alone as RL reward for money-moving negotiation.**
- Full mapping doc: `docs/self-learning.md`.

## 10. Opponent modeling (`opponent.py`, TERMS-Bench/AgenticPay)
- Estimates the buyer's **hidden reservation price** from their ascending offer sequence (geometric extrapolation of shrinking increments), classifies type (eager / measured / lowballer) + urgency, with a confidence that grows with observations.
- **Belief-calibration metric:** mean reservation-estimate error vs sim ground truth → **~95% accuracy offline** (`python3 -m gambit.opponent`).
- Finding: **eager buyers are hardest to read** (16% error) because they jump fast and overshoot the extrapolation — a real, explainable result.
- `recommend_ask(belief, item)` → opponent-aware target price. **Not yet wired into the live agent** (highest-demo-value remaining item).

## 11. Metrics & eval panel
- `score` (verifiable surplus reward — the selector) · `close_rate` · `avg_skill` (vs hidden budget) · `avg_surplus` · `avg_price` · `avg_turns` · `first_offer_ratio` (anchor aggressiveness) · `overshoot_rate`/`viol` (→ 0) · `deals` · `holdout` score.
- Planned additions: belief-calibration accuracy (TERMS-Bench), surplus↔deal-rate Pareto point.
- **Strategic-phase narrative** derivable from the panel: naive → aggressive-anchor → deadlock → rational-concession.

## 12. Demo plan & "money shot"
- **The money shot:** gen-0 (naive) vs gen-N (self-taught) **head-to-head on the same buyer** → self-taught captures more (\$448 → \$471 in latest offline run; earlier runs \$489). Plus **held-out surplus doubling** (0.16 → 0.36) = real learning, not overfitting. Plus **Tier-2 audit 12/12 clean** = defensible.
- **Demo-safety locks (for the "play it safe" appetite):** (1) **offline deterministic mode** = API-free fallback that still self-improves; (2) verifiable reward = reproducible numbers; (3) **pre-baked golden run** concept — run the real loop before judging, replay real checkpoints/curve so a flaky API can't kill the demo; (4) checkpoint/strategy hot-swap for the head-to-head.
- **30-second pitch script (captured asset):**
  > "This is **Gambit** — an AI that lists your item and negotiates with buyers to get you the best price. And it *teaches itself to negotiate better* from every conversation it has. It haggles against simulated buyers with **hidden budgets**, scores itself on **real dollars captured — a verifiable reward, not an AI judge** — and rewrites its own strategy, keeping only what wins. Day one, it closes at **\$448**. After learning from its own negotiations — **zero human labeling** — it closes the *same buyer* at **\$471**, and more than doubles its surplus on buyers it's never seen. And an **integrity auditor checks every gain, so it can't game its own reward.**"
  - Delivery: land the numbers; emphasize "verifiable reward, not an AI judge" + "can't game its own reward" (technicality signal).
  - Optional swap (creativity flex): "*It even reads the buyer — infers their hidden budget from how they bid, 95% accurate — so it knows when to stop folding.*"

## 13. Compute & infra decisions
- **Core needs NO GPU** — runs entirely on DO Serverless Inference + managed Postgres (pgvector) + App Platform + Spaces.
- **DO GPU droplet only for the Gemma-4 LoRA fine-tune** stretch.
- DO Inference: OpenAI-compatible, base `https://inference.do-ai.run/v1/`, key `DIGITAL_OCEAN_MODEL_ACCESS_KEY`; default model `llama3.3-70b-instruct` (Claude/GPT available on DO too); verifier on a stronger model.

## 14. Roadmap / phases / workstreams
- **Phase 1 (done):** learning core — agent + simulator + loop + metrics + head-to-head (offline + DO Inference).
- **Phase 1.5 (done):** Tier-2 integrity verifier + optimizer anti-bloat + held-out early-stop + opponent modeling + verifier→optimizer wiring.
- **Phase 2:** eBay Sandbox connector (Trading API) · LiveKit voice intake · DO image generation for listings.
- **Phase 3 (stretch):** Gemma-4 LoRA fine-tune on winning transcripts (DO GPU) · Gemini 3.5 computer-use auto-post.
- **Workstreams:** A = learning core · B = DO infra (inference, pgvector, image gen, deploy, GPU) · C = connectors + voice (eBay, LiveKit, computer-use) · D/shared = live UI + demo narrative + video.

## 15. Credentials checklist (long poles first)
- **eBay** (longest): developer.ebay.com → Sandbox keyset (App/Cert/Dev IDs) + RuName + 2 sandbox test users + OAuth user token.
- **DigitalOcean:** claim $200 credits → Inference → Serverless → Create Model Access Key; managed Postgres (pgvector).
- **LiveKit:** Cloud project → URL + API key/secret.
- **Gemini:** aistudio.google.com API key (Phase 3).

## 16. Current status (built vs remaining)
- **Built:** loop, buyer simulator, verifiable surplus reward, Tier-1 + Tier-2 integrity guard, held-out early-stop, `merge_tactics` anti-bloat, opponent modeling + belief calibration, verifier→optimizer dense feedback, eBay runbook (`docs/ebay.md`), research map (`docs/self-learning.md`). Offline demo runs clean.
- **Remaining (prioritized menu):** (1) opponent-aware pricing wired into `SellerAgent` (highest demo value); (2) belief calibration on the panel; (3) surplus↔deal-rate α knob + Pareto sweep; (4) strategic-phase labeling; (5) held-out *promotion* gate (stricter than early-stop); (6) Phase 2/3 items.

## 17. Dev-process notes (multi-agent)
- Repo is **co-developed across parallel sessions/worktrees**; changes sync into the working tree mid-session.
- Coordination discipline: prefer **surgical `Edit`s** on shared/hot files (fail-safe vs clobber); net-new modules + docs to avoid collisions; verify with the offline demo after each change.
- Commit history so far: `Initial commit` → `Phase 1: self-improving negotiator core` → `Rename Haggle→Gambit` → `Phase 1.5: Tier-2 integrity verifier + optimizer anti-bloat` → `Add opponent modeling + belief calibration and self-learning design map`.

## 18. Open decisions / pending
- Push `phase-1-core` to origin? (2 commits ahead; outward-facing — needs explicit OK.)
- Final real-platform call: eBay Sandbox only, or also add Reverb (live) as supporting proof?
- Add-on prioritization order for Phase 2/3 under the time budget.
- Whether to wire opponent-aware pricing before or after the eBay connector.
