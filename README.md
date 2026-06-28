# Gambit — a self-improving auto-negotiator

> Lists your item, negotiates with buyers to get the best price in a reasonable time,
> and **gets better at it from its own past negotiations** — no human labeling.

**AI Engineer World's Fair Hackathon 2026 · Theme: Continual Learning.**
The agent improves in production from real use: it reflects on the conversations it has
had, rewrites its own negotiation strategy, and keeps what measurably wins.

## The demo in one line
> Same item, same buyer, same hidden budget. The day-one agent closes at **\$448**.
> After learning from its own negotiations — zero human labels — it closes the identical
> buyer at **\$471**, and *more than doubles* its surplus on buyers it never trained on.
> Watch the curve climb across generations.

## How it works

```
            ┌─────────────────── continual-learning loop ───────────────────┐
            │                                                                │
  Strategy ─┼─►   seller   ⇄   buyer (self-play)  ──►  Episodes  ──►  Score  │
  (policy)  │  (one shared policy, walled-off       (transcripts)        │   │
            │   private info on each side)                               ▼   │
            │         ▲                                                      │
            │         └──────────  Optimizer  ◄── reflect on wins/losses ────┘
            │            (improves the weakest situation-bucket; promotes what wins on held-out)
```

- **Pluggable counterparty** — the loop is a *referee* over two policies; what's on the other
  side of the table is a swap, not a rewrite. The default buyer is **self-play**: the *same
  shared policy* wearing the buyer's hat, assigned a *hidden reservation* drawn from a persona
  (lowballer, fence-sitter, in-a-hurry, tire-kicker) and rewarded for its own surplus — so the
  agent improves by negotiating against itself, no human labels. A **human** (by text or voice)
  or a **live market** (eBay) drops into the same seat unchanged. The seller never sees the budget.
- **Seller** — negotiates from the **resolved situation-bucket** of a learned `PolicyStore`, keyed
  by `(price_band, margin_band, buyer_type)`: per-bucket anchor, concession schedule, accept
  threshold, walk-away patience, **plus that bucket's validated lessons**. The model's weights are
  frozen — *the policy table is what learns.*
- **Optimizer** — the self-improvement brain. The weights can't change, so it improves the **data the
  agent reads**: each generation it finds the weakest bucket and proposes a scoped knob tweak or
  lesson, kept only if a **per-bucket held-out A/B** raises surplus with `viol=0` (Beta/Thompson
  exploration; validated lessons are never evicted → no forgetting). Offline it runs a deterministic
  search so the loop is testable with no API key. A **Gemini Antigravity** backend can run this as a
  managed agent that edits *one weak bucket's* skill fragment across generations. Either way it
  *proposes* — the deterministic reward *selects*. (Why a table, not one global prompt: a single
  prompt plateaus, forgets, and can't attribute gains — see [`docs/architecture.md`](docs/architecture.md).)
- **Reward** — a *deterministic, verifiable* surplus from the secret floor drives selection
  (no LLM judge — following arXiv:2604.09855), with a terminal penalty for going below floor and
  neutral credit for walking away. A reward-integrity guard audits every transcript so the
  optimizer can't game its own metric (`viol=0%`). `skill` (vs. the hidden budget), close rate,
  and anchor aggressiveness are reported as secondary panel metrics. The climbing curve is the demo.

## Built on
One typed contract end-to-end (**Pydantic**), every LLM role a typed agent with validated
structured output (**Pydantic AI** on **MiniMax M3**), every run traced (**Logfire**), deployed on
**DigitalOcean** (App Platform + Managed Postgres/pgvector). The seller, buyer, optimizer, and
verifier are four small `Agent`s; field constraints and output validators are the anti-reward-hacking
rails; selection stays on the deterministic surplus. On top sits a **Gemini 3.5** feature layer —
a Gemini **Antigravity** managed-agent optimizer (Interactions API), a **LiveKit + Gemini
Live/Translate** voice buyer seat, and **Nano Banana** listing images — none of which touch the
selector. Full engineering design in **[`docs/architecture.md`](docs/architecture.md)**.

## Quickstart

```bash
uv sync

# Runs with zero API keys (deterministic policy) — validates the whole pipeline:
uv run python scripts/run_demo.py --offline --generations 8

# With a MiniMax API key, the agents + optimizer use real LLMs:
cp .env.example .env   # fill in MINIMAX_API_KEY / MINIMAX_BASE_URL / MINIMAX_MODEL (+ optional LOGFIRE_TOKEN)
uv run python scripts/run_demo.py --generations 8
```

Offline sample output:

```
gen 0  score=0.132  close=67%  skill=0.34  price=$510  anchor=1.00  viol=0%  deals=6/12
gen 6  score=0.250  close=67%  skill=0.69  price=$550  anchor=0.92  viol=0%  deals=6/12
>>> Self-taught agent captured $+23 more from the same buyer.
held-out buyers (never trained on):  surplus 0.16 -> 0.36
```

## Roadmap & prize stack

| Phase | What | Status |
|---|---|---|
| **1 — Learning core** | seller + self-play buyer (one shared policy) + self-improvement loop + reward + head-to-head | ✅ runnable (offline + MiniMax M3) |
| **1 — Learned artifact** | situation-keyed `PolicyStore` (per-bucket knobs + value-attributed lessons) + per-bucket held-out A/B promotion — replaces the global tactics blob | ⬜ |
| **1 — Self-improving optimizer** | **Gemini Antigravity** managed agent improves one weak bucket's skill fragment across generations (stateful env) — proposes, never selects | ⬜ |
| **2 — Real marketplace** | eBay connector (real list + Best Offer loop, **eBay API**) — see `docs/ebay.md` | ⬜ |
| **2 — Voice buyer seat** | **LiveKit + Gemini Live/Translate**: a human haggles by voice, cross-language, in the buyer seat | ⬜ |
| **2 — Listing images** | **Nano Banana** (Gemini) listing photo + text-in-image | ⬜ |
| **3 — Weight-level RSI** | LoRA fine-tune on winning transcripts (DO GPU droplet) — *Gemma 4 on-device out of scope* | ⬜ stretch |

The inner negotiation loop stays on **MiniMax M3** (cheap, high-volume); **Gemini 3.5** rides a
feature layer on top (the Antigravity optimizer, the Gemini-Live voice seat, Nano Banana media).
Targets: **Continual Learning** theme · **Best DigitalOcean** (App Platform deploy, pgvector memory,
Spaces images) · **Best LiveKit** (voice buyer seat) · **Best Gemini \$5k** (Antigravity managed-agent
optimizer + Gemini Live/Translate + Nano Banana — three new surfaces, not a wrapper chatbot).
See the full prize-alignment map in **[`northstar.md`](northstar.md)** §9.

## Why eBay (not Facebook Marketplace)
Automating Facebook Marketplace/Messenger violates Meta's ToS (no public API) and risks
**hackathon disqualification** for a platform-policy violation. We build marketplace-agnostic:
**eBay Sandbox** is the real-platform proof (official listing API + native Best Offer
negotiation + test buyers), and the **buyer simulator** is the reproducible learning engine.
See `docs/ebay.md`.

## Layout
The full rebuild design (rationale + code shapes) is in **[`docs/architecture.md`](docs/architecture.md)**.
```
gambit/
  settings.py      # pydantic-settings BaseSettings (env / .env, validated)
  observability.py # logfire.configure() + instrument_pydantic_ai (once, at entry)
  llm.py           # MiniMax M3 OpenAIChatModel factory + FallbackModel (inner loop)
  models.py        # ALL domain types as Pydantic BaseModel (+ validators): Item, Strategy
                   #   (per-bucket knobs), Lesson, BucketPolicy, PolicyStore, Episode, Belief
  policy.py        # the learned artifact: situation_key() + PolicyStore + per-bucket held-out promotion
  agents/          # seller · buyer · optimizer · verifier (typed Agents)
                   #   + optimizer_antigravity.py — Gemini managed-agent optimizer backend
  policies.py      # Policy protocol: self-play (LLM) · heuristic · human · live-market
  voice/           # Gemini feature layer: LiveKit + Gemini Live voice buyer seat → BuyerMove
  media.py         # Gemini feature layer: Nano Banana listing images (Phase 2)
  negotiation.py   # referee loop over policies → Episode (Logfire episode spans)
  reward.py        # verifiable surplus + Tier-1 integrity audit (no LLM in the selector)
  opponent.py      # belief estimation (pure Python); Belief is a BaseModel
  improve_loop.py  # generational learning loop + head-to-head (Logfire generation spans)
  connectors/      # Phase 2: eBay API connector (payloads as BaseModels)
scripts/run_demo.py
docs/architecture.md  # engineering design & approach
docs/self-learning.md # research grounding (which paper buys what)
docs/eval-plan.md     # how we prove it works & keeps improving (safety vs transferable validity)
docs/ebay.md          # Phase-2 eBay connector runbook
```

## Credentials to redeem (long poles first)
- **eBay** (longest setup): developer.ebay.com → Sandbox keyset (App/Cert/Dev IDs) + RuName +
  two sandbox test users + OAuth user token.
- **MiniMax** (the LLM): API key → `MINIMAX_API_KEY`, plus the M3 `MINIMAX_BASE_URL` / `MINIMAX_MODEL`.
- **DigitalOcean** (deploy + data): claim credits → App Platform (deploy) + Managed Postgres
  (persists the `PolicyStore` as plain indexed rows; pgvector only for optional Tier-C exemplar
  retrieval) + Spaces (images). Inference now lives on MiniMax.
- **Logfire** (optional, fast): logfire.pydantic.dev → write token → `LOGFIRE_TOKEN`. Without it
  tracing runs locally; with it the improvement curve is a live dashboard.
- **LiveKit**: Cloud project → URL + API key/secret (the voice buyer seat's transport).
- **Gemini**: aistudio.google.com API key — the feature layer (Antigravity optimizer via the
  Interactions API · Gemini Live/Translate for the voice seat · Nano Banana for listing media).
