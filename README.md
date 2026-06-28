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
  Strategy ─┼─►  SellerAgent  ⇄  BuyerSimulator   ──►  Episodes  ──►  Score  │
  (policy)  │   (negotiator)     (hidden budgets)       (transcripts)   │    │
            │         ▲                                                 ▼    │
            │         └──────────  Optimizer  ◄── reflect on wins/losses ────┘
            │            (rewrites tactics + tunes knobs, keeps what scores higher)
```

- **BuyerSimulator** — adversarial LLM buyers with *hidden reservation prices* and personas
  (lowballer, fence-sitter, in-a-hurry, tire-kicker). Gives us conversation volume to learn
  from and a controlled, reproducible demo. The agent never sees the budgets.
- **SellerAgent** — negotiates from a `Strategy` (anchor, concession schedule, accept
  threshold, walk-away patience, free-text tactics).
- **Optimizer** — the self-improvement brain. With an LLM it reflects on real transcripts and
  rewrites its own tactics + knobs; offline it runs a deterministic search so the loop is
  testable with no API key.
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
rails; selection stays on the deterministic surplus. Full engineering design in
**[`docs/architecture.md`](docs/architecture.md)**.

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
| **1 — Learning core** | agent + buyer simulator + self-improvement loop + metrics + head-to-head | ✅ runnable (offline + MiniMax M3) |
| **2 — Real marketplace** | eBay Sandbox connector (real list + Best Offer loop) — see `docs/ebay.md` | ⬜ |
| **2 — Voice intake** | LiveKit: describe your item by talking, agent builds the listing live | ⬜ |
| **2 — Listing images** | DigitalOcean image generation for listing photos | ⬜ |
| **3 — Weight-level RSI** | LoRA fine-tune **Gemma 4** on winning transcripts (DO GPU droplet) | ⬜ stretch |
| **3 — Auto-post** | Gemini 3.5 computer-use to post where no API exists | ⬜ stretch |

Targets: **Continual Learning** theme · **Best MiniMax** (the negotiator + buyer + verifier all run
on MiniMax M3) · **Best DigitalOcean** (App Platform deploy, pgvector memory, Spaces images) ·
**Best LiveKit** (voice intake) · **Best Gemini \$5k** (stretch — Gemma 4 fine-tune + computer-use).

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
  llm.py           # DigitalOcean OpenAIChatModel factory + FallbackModel
  models.py        # ALL domain types as Pydantic BaseModel (+ validators)
  agents/          # seller · buyer · optimizer · verifier — one typed Agent each
  policies.py      # Policy protocol: LLM impl + deterministic offline impl
  negotiation.py   # referee loop over policies → Episode (Logfire episode spans)
  reward.py        # verifiable surplus + Tier-1 integrity audit (no LLM in the selector)
  opponent.py      # belief estimation (pure Python); Belief is a BaseModel
  improve_loop.py  # generational learning loop + head-to-head (Logfire generation spans)
  connectors/      # Phase 2: eBay Trading API (payloads as BaseModels)
scripts/run_demo.py
docs/architecture.md  # engineering design & approach
docs/self-learning.md # research grounding (which paper buys what)
docs/ebay.md          # Phase-2 eBay connector runbook
```

## Credentials to redeem (long poles first)
- **eBay** (longest setup): developer.ebay.com → Sandbox keyset (App/Cert/Dev IDs) + RuName +
  two sandbox test users + OAuth user token.
- **MiniMax** (the LLM): API key → `MINIMAX_API_KEY`, plus the M3 `MINIMAX_BASE_URL` / `MINIMAX_MODEL`.
- **DigitalOcean** (deploy + data): claim credits → App Platform (deploy) + Managed Postgres
  (pgvector) for memory + Spaces (images). Inference now lives on MiniMax.
- **Logfire** (optional, fast): logfire.pydantic.dev → write token → `LOGFIRE_TOKEN`. Without it
  tracing runs locally; with it the improvement curve is a live dashboard.
- **LiveKit**: Cloud project → URL + API key/secret.
- **Gemini**: aistudio.google.com API key (Phase 3).
