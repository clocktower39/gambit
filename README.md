# Haggle — a self-improving auto-negotiator

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

## Quickstart

```bash
pip install -r requirements.txt

# Runs with zero API keys (deterministic heuristics) — validates the whole pipeline:
python3 scripts/run_demo.py --offline --generations 8

# With a DigitalOcean model access key, the agents + optimizer use real LLMs:
cp .env.example .env   # fill in DIGITAL_OCEAN_MODEL_ACCESS_KEY
python3 scripts/run_demo.py --generations 8
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
| **1 — Learning core** | agent + buyer simulator + self-improvement loop + metrics + head-to-head | ✅ runnable (offline + DO Inference) |
| **2 — Real marketplace** | eBay Sandbox connector (real list + Best Offer loop) — see `docs/ebay.md` | ⬜ |
| **2 — Voice intake** | LiveKit: describe your item by talking, agent builds the listing live | ⬜ |
| **2 — Listing images** | DigitalOcean image generation for listing photos | ⬜ |
| **3 — Weight-level RSI** | LoRA fine-tune **Gemma 4** on winning transcripts (DO GPU droplet) | ⬜ stretch |
| **3 — Auto-post** | Gemini 3.5 computer-use to post where no API exists | ⬜ stretch |

Targets: **Continual Learning** theme · **Best DigitalOcean** (inference, pgvector memory,
image gen, App Platform, Spaces) · **Best LiveKit** (voice intake) · **Best Gemini \$5k**
(Gemma 4 fine-tune + computer-use).

## Why eBay (not Facebook Marketplace)
Automating Facebook Marketplace/Messenger violates Meta's ToS (no public API) and risks
**hackathon disqualification** for a platform-policy violation. We build marketplace-agnostic:
**eBay Sandbox** is the real-platform proof (official listing API + native Best Offer
negotiation + test buyers), and the **buyer simulator** is the reproducible learning engine.
See `docs/ebay.md`.

## Layout
```
haggle/
  models.py        # Item, BuyerPersona, Strategy, Episode, Outcome
  personas.py      # fixture items + buyer personas (hidden budgets)
  seller_agent.py  # the negotiator (LLM + offline heuristic)
  buyer_sim.py     # adversarial buyer simulator
  negotiation.py   # runs one episode, scores the outcome
  metrics.py       # verifiable surplus reward + reward-integrity guard + metric panel
  optimizer.py     # the self-improvement brain (LLM reflection + offline search)
  improve_loop.py  # the generational learning loop + head-to-head
  inference.py     # DigitalOcean Serverless Inference (OpenAI-compatible) client
  config.py        # env / settings
scripts/run_demo.py
docs/ebay.md       # Phase-2 eBay connector runbook
```

## Credentials to redeem (long poles first)
- **eBay** (longest setup): developer.ebay.com → Sandbox keyset (App/Cert/Dev IDs) + RuName +
  two sandbox test users + OAuth user token.
- **DigitalOcean**: claim credits → Inference → Serverless → Create Model Access Key →
  `DIGITAL_OCEAN_MODEL_ACCESS_KEY`. Also a managed Postgres (pgvector) for memory.
- **LiveKit**: Cloud project → URL + API key/secret.
- **Gemini**: aistudio.google.com API key (Phase 3).
