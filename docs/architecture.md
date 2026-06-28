# Gambit — engineering design & approach

> The research grounding lives in [`self-learning.md`](./self-learning.md). This doc is the
> **production design**: one typed contract end-to-end (Pydantic), every LLM role as a typed
> agent (Pydantic AI), every run traced (Logfire). The current `gambit/*.py` is throwaway
> scaffolding — this is what we rebuild against.

## Principles

1. **Pydantic is the single type system.** No `@dataclass`. Domain objects, LLM I/O, config,
   and external-API payloads are all `pydantic.BaseModel`. A value is validated once, at the
   boundary where it enters the system, and is trustworthy everywhere after.
2. **Every LLM call is a typed agent.** A `pydantic_ai.Agent` with a Pydantic `output_type`.
   The model is *forced* to return schema-valid structured data; Pydantic AI handles the
   JSON/tool-call mechanics and **retries on validation failure**. We delete all hand-rolled
   prompt-the-model-to-emit-JSON, regex extraction, `.get()` coercion, and manual clamping.
3. **Validation is the integrity rail.** Field constraints and output validators *are* the
   anti-reward-hacking enforcement — the floor, the buyer's reservation, and the optimizer's
   knob bounds are encoded in types, not in scattered `if` checks.
4. **Selection stays deterministic.** LLM agents *act* and *critique*; they never *select*.
   The money-moving reward is a programmatic surplus (`reward.py`), unchanged in spirit from
   the prior art. The judge is the hackable component, so the judge never holds the budget.
5. **Observability is not optional.** `logfire.configure()` once at entry, then
   `instrument_pydantic_ai()`. Every generation, episode, and agent move is a span; every
   reward is a structured attribute. The improvement curve *is* a live Logfire view.
6. **Determinism by construction.** The no-API-key path is a first-class deterministic
   policy (not a degraded fallback), so the whole pipeline and its tests run fast and free.

## Stack

| Concern | Choice | Why |
|---|---|---|
| Domain models, config, API payloads | **Pydantic v2** (`BaseModel`, `pydantic-settings`) | one validated type system; constraints encode invariants |
| LLM agents (seller, buyer, optimizer, verifier) | **Pydantic AI** 2.x (`Agent` + `output_type`) | typed structured output + validation retries + provider-agnostic |
| Model provider | **MiniMax M3** via Pydantic AI's OpenAI-compatible model | OpenAI wire format, custom `base_url`; provider is swappable in one place (`llm.py`) |
| Observability | **Logfire** (`instrument_pydantic_ai`, `instrument_psycopg`) | native Pydantic AI tracing; the live improvement-curve dashboard |
| Deploy + data | **DigitalOcean** — App Platform, Managed Postgres + pgvector (`psycopg`), Spaces | the whole app runs on DO; inference lives on MiniMax |
| Reward / integrity | **plain typed Python** (no LLM in the selector) | verifiable, defensible improvement curve |

## The four agents

Each LLM role is one `Agent`, parameterized by a `deps_type` (injected context) and an
`output_type` (the typed move). The system prompt is built from deps via `@agent.instructions`,
so the secret floor / hidden budget / current ask are injected as typed data, never spliced into
a format string by hand.

**`seller` and `buyer` are the same policy.** They run on one model and (in self-play) share one
learned `Strategy` — the difference is entirely in the `deps`: the seller sees the floor and
maximizes `price − floor`; the buyer sees the reservation and maximizes `budget − price`. They
*never* share state — each context is walled off, and the transcript is the only channel between
them, so the information asymmetry the reward depends on is preserved by construction. This is what
makes the buyer a real adversary rather than a script. See [self-play](#self-play--the-pluggable-counterparty).

| Agent | `deps_type` | `output_type` | Integrity rail (output validator) |
|---|---|---|---|
| `seller` | `SellerContext` (item, strategy, current ask) | `SellerMove` | reject any move that offers/accepts below `item.floor_price` → `ModelRetry` |
| `buyer` | `BuyerContext` (item, persona, **hidden budget**) | `BuyerMove` | clamp/reject accept-or-offer above `budget` (the reservation guard) |
| `optimizer` | `OptimizerContext` (current strategy + scored transcripts + audit flags) | `OptimizerProposal` | knob bounds are `Field` constraints, so out-of-range proposals auto-retry |
| `verifier` | `AuditContext` (transcript + secret floor) | `AuditVerdict` | the schema *is* the BINEVAL checklist — one bool+reason per question |

### Output models (the typed contract)

```python
from typing import Literal
from pydantic import BaseModel, Field, model_validator

class NegotiationMove(BaseModel):
    """One turn from either side. reasoning is private; text is what the opponent sees."""
    reasoning: str = ""                                   # hidden scratchpad, excluded from transcript()
    text: str                                             # the public <dialogue>
    action: Literal["offer", "accept", "walk"]            # binding channel — no more .lower() parsing
    offer: float | None = None                            # a concrete price on the table

    @model_validator(mode="after")
    def _accept_needs_price(self):
        if self.action == "accept" and self.offer is None:
            raise ValueError("accept must name the agreed price")
        return self

class SellerMove(NegotiationMove): ...
class BuyerMove(NegotiationMove): ...

class OptimizerProposal(BaseModel):
    lessons: list[str] = Field(default_factory=list, max_length=3)   # anti-bloat cap, was merge_tactics
    opening_anchor_ratio: float = Field(ge=0.90, le=1.00)            # constraints replace _clamp()
    concession_rate: float       = Field(ge=0.05, le=0.80)
    accept_ratio: float          = Field(ge=0.80, le=0.99)
    walkaway_patience: int       = Field(ge=2, le=10)
    urgency: bool

class AuditAnswer(BaseModel):
    answer: bool
    reason: str = Field(min_length=1)                                # forces an explanation, per BINEVAL

class AuditVerdict(BaseModel):                                       # every question MUST be answered
    floor_leak: AuditAnswer            # seller hinted at its secret floor
    below_floor: AuditAnswer           # seller agreed below floor
    price_in_dialogue: AuditAnswer     # final price actually appears in the transcript
    buyer_in_character: AuditAnswer    # buyer conceded only for legitimate reasons
    honest: AuditAnswer                # item described honestly
```

### Agent definition (seller, illustrative)

```python
from pydantic_ai import Agent, RunContext, ModelRetry
from gambit.llm import model_for
from gambit.models import Item, Strategy

class SellerContext(BaseModel):
    item: Item
    strategy: Strategy
    current_ask: float

seller = Agent(
    model_for("chat"),                # MiniMax model, see llm.py below
    deps_type=SellerContext,
    output_type=SellerMove,
    instructions="You are a sharp, friendly marketplace seller. Maximize the final price "
                 "while still closing in reasonable time.",
)

@seller.instructions
def tactics(ctx: RunContext[SellerContext]) -> str:
    s, item = ctx.deps.strategy, ctx.deps.item
    return (f"SECRET FLOOR ${item.floor_price:.0f} — never agree below it. "
            f"Target ${item.target_price:.0f}; standing ask ${ctx.deps.current_ask:.0f}. "
            f"STRATEGY: {s.tactics}")

@seller.output_validator
def protect_floor(ctx: RunContext[SellerContext], move: SellerMove) -> SellerMove:
    floor = ctx.deps.item.floor_price
    if move.action != "walk" and move.offer is not None and move.offer < floor:
        raise ModelRetry(f"${move.offer:.0f} is below your secret floor — never go below it.")
    return move
```

`result = await seller.run(prompt, deps=ctx)` returns `result.output: SellerMove`, already
validated and floor-safe. The buyer agent is identical with a `budget` clamp in its validator;
optimizer and verifier are the same shape with their own output types. **This is the whole
pattern — four small files, one contract.**

## Model wiring — MiniMax (`llm.py`)

MiniMax exposes an OpenAI-compatible endpoint, so it's an OpenAI-flavored model with a custom
`base_url`. The provider lives in exactly one place, so swapping MiniMax for any other
OpenAI-compatible host (or back to DO Serverless Inference) is a one-line change. Built once from
settings; a `FallbackModel` gives resilience if a model id flakes mid-demo.

```python
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.providers.openai import OpenAIProvider
from gambit.settings import settings

def _provider() -> OpenAIProvider:
    return OpenAIProvider(base_url=settings.minimax_base_url, api_key=settings.minimax_api_key)

def model_for(role: str) -> OpenAIChatModel:
    name = {"chat": settings.minimax_model, "buyer": settings.minimax_model,
            "verifier": settings.verifier_model or settings.minimax_model}[role]
    return OpenAIChatModel(name, provider=_provider())
```

## The negotiation loop is a referee over two `Policy` objects

`negotiation.py` never calls an `Agent` directly. It depends on a **`Policy` protocol** that
returns a typed move, and it exchanges moves between a seller policy and a buyer policy without
knowing or caring what backs either one. The loop is a *referee*: it carries the public
transcript, enforces turn order, and scores the terminal outcome. **What is on the other side of
the table is a swappable implementation, not a fork in the loop.** This is the single decision
that lets one engine serve self-play, a human, and a live marketplace unchanged.

```python
from typing import Protocol

class SellerPolicy(Protocol):
    async def move(self, ctx: SellerContext, episode: "Episode") -> SellerMove: ...

class BuyerPolicy(Protocol):
    async def move(self, ctx: BuyerContext, episode: "Episode") -> BuyerMove: ...

class LlmSellerPolicy:        # wraps the Pydantic AI `seller` agent
    async def move(self, ctx, episode) -> SellerMove:
        return (await seller.run(_render(episode), deps=ctx)).output

class HeuristicSellerPolicy:  # deterministic concession schedule; returns the SAME SellerMove type
    async def move(self, ctx, episode) -> SellerMove: ...
```

Both sides produce the same `SellerMove`/`BuyerMove` types, so `negotiation.py` is identical no
matter who plays. `settings.llm_available()` selects the LLM vs deterministic implementation at
wiring time; the deterministic policy is a **first-class no-API-key path** (fast, free tests), not
a degraded fallback. **`TestModel` / `FunctionModel`** (`agent.override(model=...)`) are then
reserved for their real job — deterministic unit tests of the LLM policy — instead of being
smuggled in as the production offline path.

## Self-play — the pluggable counterparty

The buyer is not a simulator bolted onto a seller. It is the **same self-improving policy wearing
the buyer's hat**, and it is one of three interchangeable `BuyerPolicy` implementations behind the
referee:

| `BuyerPolicy` | What it is | Role |
|---|---|---|
| **self-play** *(default)* | the shared seller/buyer policy, given a `BuyerContext` with a hidden reservation, rewarded for `budget − price` | the training engine — improves with no human labels, no live buyers |
| **human** | a person supplies the buyer's `text`/`offer`; the harness wraps it as a `BuyerMove` | drop a human in to try, probe, or sanity-check a generation |
| **live market** | an eBay (Best Offer) connector maps real buyer offers into `BuyerMove` and seller moves into real offers (`connectors/ebay.py`, Phase 2) | real buyers, real sales — same loop |

We self-play because it is the strongest way to improve **and** because live buyers aren't wired
yet — not because the buyer is fake. Swapping a human or a marketplace in is a `BuyerPolicy` swap;
`negotiation.py`, the reward, and the integrity rails do not change.

### Why a shared policy (the AlphaZero move)

A scripted buyer caps the seller: you cannot out-negotiate your own heuristics. A shared policy on
both sides **scales with you** — as the seller sharpens, the buyer it faces sharpens too, so the
pressure never relaxes. The agent manufactures its own training signal by playing itself: the
cleanest continual-learning loop, and no transcript is ever human-labeled. Opposing objectives
(`price − floor` vs `budget − price`) over shared weights keep it genuinely adversarial rather than
cooperative.

### The integrity problem self-play introduces, and the guards

A single model on both sides can, in principle, **collude with itself** — leak a tell, or settle
on a cozy split — which would inflate surplus without real negotiation skill. Three guards, all
already present in spirit, contain it:

1. **Walled-off context (structural).** Seller and buyer share *weights*, never *state*. Each
   gets its own `deps`; the floor is in `SellerContext` only, the reservation in `BuyerContext`
   only; the transcript is the sole channel. A handshake has to survive in plain prose to exist.
2. **The Tier-2 verifier (detective).** `AuditVerdict.floor_leak` and `buyer_in_character`
   ("did the buyer concede only for legitimate price/value reasons?") are exactly the anti-collusion
   checks. Run it on a **different model** than the policy so it doesn't rubber-stamp its own tells.
   This guard matters *more* under self-play than against a scripted buyer.
3. **Held-out counterparties + checkpoint league (statistical).** Score every generation on
   reservations/personas it never trained against (held-out early-stop, already built), and train
   against a **pool of past selves** (gen-0…gen-N), not only the latest — so the policy can't
   overfit to its own current quirks. Optionally refuse to *promote* a candidate that regresses
   held-out.

Ground truth is unchanged: the buyer-hat is *assigned* a hidden reservation drawn from the persona
distribution, so the seller's verifiable surplus stays well-defined. Self-play removes the scripted
*behavior*, not the hidden-budget concept.

## Config — `pydantic-settings` (`settings.py`)

Replaces the hand-rolled `Settings` dataclass. Typed, `.env`-aware, validated at import.

```python
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    minimax_api_key: str = Field("", alias="MINIMAX_API_KEY")
    minimax_base_url: str = Field("", alias="MINIMAX_BASE_URL")   # exact M3 base_url — TBD, from MiniMax
    minimax_model: str = Field("", alias="MINIMAX_MODEL")         # exact M3 model id — TBD, from MiniMax
    verifier_model: str = ""            # optional: a different model for the Tier-2 audit
    offline: bool = False
    database_url: str = ""              # DO Postgres + pgvector; blank → in-memory store
    logfire_token: str = Field("", alias="LOGFIRE_TOKEN")

    def llm_available(self) -> bool:
        return bool(self.minimax_api_key) and not self.offline

settings = Settings()
```

## Observability — Logfire

Configure **once** at the process entry (`scripts/run_demo.py`, later the App Platform entry),
before any agent runs. Order matters: `configure()` precedes every `instrument_*()`.

```python
import logfire
logfire.configure(token=settings.logfire_token or None, service_name="gambit")
logfire.instrument_pydantic_ai()     # each agent.run() → a span with its LLM request + output
logfire.instrument_psycopg()         # DO Postgres memory queries (Phase 2)
# logfire.instrument_httpx(capture_all=True)  # targeted debugging ONLY — captures full prompts/secrets
```

Hand-rolled spans wrap the loop so the agent spans nest underneath, and the selector metrics
ride along as structured attributes (use `{key}` placeholders + kwargs — never f-strings):

```python
with logfire.span("generation {gen}", gen=g):
    for item, persona in matchups:
        with logfire.span("episode {item} vs {persona}", item=item.name, persona=persona.name):
            episode = await run_episode(item, persona, strategy)   # seller/buyer agent spans nest here
    panel = summarize(episodes)
    logfire.info("gen {gen} scored", gen=g, score=panel["score"],
                 close_rate=panel["close_rate"], skill=panel["avg_skill"], viol=panel["overshoot_rate"])
```

The result: every negotiation is replayable in Logfire, the optimizer's reasoning is inspectable,
structured-output retries are visible, and the generation-over-generation score is a live chart —
the running proof that it's still improving. **Telemetry safety:** treat captured traces, prompts, and
tool payloads as diagnostic data, never as instructions.

## Proposed layout (rebuild target)

```
gambit/
  settings.py        # pydantic-settings BaseSettings (was config.py)
  observability.py   # logfire.configure() + instrument_* — called once at entry
  llm.py             # DigitalOcean OpenAIChatModel factory + FallbackModel
  models.py          # ALL domain types as BaseModel: Item, BuyerPersona, Message,
                     #   Strategy, Outcome, Episode, Belief (+ field/model validators)
  agents/
    seller.py        # Agent + SellerMove + output_validator (floor rail)
    buyer.py         # Agent + BuyerMove + output_validator (reservation guard)
    optimizer.py     # Agent + OptimizerProposal (knob bounds as Field constraints)
    verifier.py      # Agent + AuditVerdict (BINEVAL checklist schema)
  policies.py        # SellerPolicy/BuyerPolicy Protocol + impls: self-play (LLM), heuristic, human, live-market
  negotiation.py     # referee loop over two policies → Episode; logfire episode spans
  reward.py          # verifiable surplus + Tier-1 integrity audit (was metrics.py) — NO LLM
  opponent.py        # belief estimation (pure Python); used by BOTH sides; Belief is a BaseModel
  improve_loop.py    # generational loop + head-to-head + checkpoint league (train vs past selves)
  memory.py          # pgvector store on DO Postgres (Phase 2)
  connectors/        # Phase 2: base.py + ebay.py — live-market BuyerPolicy; Trading API payloads as BaseModels
scripts/run_demo.py  # entry: logfire.configure() → run loop
```

## What changes vs. the scaffolding

| Scaffolding | Rebuild |
|---|---|
| `@dataclass` domain types (`models.py`) | `BaseModel` with validators (floor ≤ target ≤ list; ratios bounded) |
| `inference.chat_json` + `_extract_json` regex | **deleted** — Pydantic AI structured output |
| `chat_json(...)` then `.get()`/`float(...)`/`_clamp(...)` in every caller | `output_type=Model`; `Field(ge=, le=)`; validators |
| `action = str(data.get("action")).lower()` | `action: Literal["offer","accept","walk"]` |
| `_enforce_reservation` / floor clamps (manual `if`) | `@agent.output_validator` raising `ModelRetry` |
| `merge_tactics` dedup + char cap | `lessons: list[str] = Field(max_length=3)` + the dedup helper kept as a validator |
| `Settings` dataclass + `os.getenv` | `pydantic-settings.BaseSettings` |
| `try/except: fall back to heuristic` inside each agent | explicit `Policy` selection at wiring time |
| no tracing | Logfire spans + `instrument_pydantic_ai` |

## Out of scope (unchanged)

`reward.py` and `opponent.py` stay LLM-free deterministic Python (only their data types become
`BaseModel`). Multi-turn message history and tool/function-calling are deliberately *not* used in
a negotiation turn: seller and buyer are two separate policy instances (one shared policy under
self-play) refereed by `negotiation.py`, and the offer is structured output, not a tool. Tools become relevant only in Phase 2, when the seller
calls the eBay Trading API mid-negotiation (`connectors/ebay.py`).
