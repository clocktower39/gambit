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
| Inner-loop model provider | **MiniMax M3** via Pydantic AI's OpenAI-compatible model | OpenAI wire format, custom `base_url`; provider is swappable in one place (`llm.py`). Carries the high-volume seller/buyer/verifier calls. |
| Observability | **Logfire** (`instrument_pydantic_ai`, `instrument_psycopg`) | native Pydantic AI tracing; the live improvement-curve dashboard |
| Deploy + data | **DigitalOcean** — App Platform, Managed Postgres + pgvector (`psycopg`), Spaces | the whole app runs on DO; inference lives on MiniMax |
| Reward / integrity | **plain typed Python** (no LLM in the selector) | verifiable, defensible improvement curve |
| **Self-improving optimizer** | **Gemini Antigravity** (`antigravity-preview-05-2026`) via the **Interactions API**, second backend behind the proposal interface | hosted agent improves **one weak bucket's** skill fragment in the situation-keyed `PolicyStore` across generations (stateful `environment_id`); runs **once per generation**, never per move; proposes, never selects |
| **Voice counterparty** | **LiveKit** room + **Gemini Live / Live Translate** (`gemini-3.5-live-translate-preview`) | the human buyer seat by voice, cross-language; an I/O shell that emits the same typed `BuyerMove` |
| **Listing media** | **Nano Banana** (Gemini image gen) | the eBay listing photo + text-in-image; Phase 2 |

## The four agents

Each LLM role is one `Agent`, parameterized by a `deps_type` (injected context) and an
`output_type` (the typed move). The system prompt is built from deps via `@agent.instructions`,
so the secret floor / hidden budget / current ask are injected as typed data, never spliced into
a format string by hand.

**`seller` and `buyer` are the same policy.** They run on one model and (in self-play) share one
learned `PolicyStore` — the difference is entirely in the `deps`: the seller sees the floor and
maximizes `price − floor`; the buyer sees the reservation and maximizes `budget − price`. They
*never* share state — each context is walled off, and the transcript is the only channel between
them, so the information asymmetry the reward depends on is preserved by construction. This is what
makes the buyer a real adversary rather than a script. See [self-play](#self-play--the-pluggable-counterparty).

| Agent | `deps_type` | `output_type` | Integrity rail (output validator) |
|---|---|---|---|
| `seller` | `SellerContext` (item, resolved `bucket`, current ask) | `SellerMove` | reject any move that offers/accepts below `item.floor_price` → `ModelRetry` |
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
    target_bucket: str                                              # the situation_key this change applies to
    lessons: list[str] = Field(default_factory=list, max_length=3)   # candidate lesson(s) for THIS bucket only
    opening_anchor_ratio: float = Field(ge=0.90, le=1.00)            # this bucket's knobs; constraints replace _clamp()
    concession_rate: float       = Field(ge=0.05, le=0.80)
    accept_ratio: float          = Field(ge=0.80, le=0.99)
    walkaway_patience: int       = Field(ge=2, le=10)
    urgency: bool
    # SCOPED to one bucket — no global `tactics` blob. The host applies it to
    # PolicyStore.buckets[target_bucket]; the per-bucket held-out A/B gate decides promotion.

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

### Context models (the `deps_type`s) — the concrete types every agent and parallel team builds against

```python
class SellerContext(BaseModel):                  # (also shown in the agent sketch below)
    item: Item; bucket: BucketPolicy; current_ask: float   # bucket resolved via situation_key(item, belief)

class BuyerContext(BaseModel):
    item: Item
    persona: BuyerPersona                        # carries language (see model additions below)
    budget: float                                # the hidden reservation — never leaves this context
    current_offer: float | None = None

class OptimizerContext(BaseModel):               # input to BOTH optimizer backends
    policy: PolicyStore                          # the full learned artifact
    target_bucket: str                           # the weak bucket this call is scoped to improve
    transcripts: list[str]                       # worst-scoring episodes IN target_bucket (public)
    surplus: list[float]                         # matching verifiable surplus per transcript
    audit_flags: list[AuditVerdict]              # matching Tier-2 verdicts (dense feedback)
    held_out_score: float                        # current held-out surplus FOR target_bucket (gate baseline)

class AuditContext(BaseModel):
    transcript: str                              # Episode.transcript() — public channel only
    floor_price: float                           # the secret floor (below-floor / leak checks)
    list_price: float

class BuyerUtterance(BaseModel):                 # output_type of the voice `to_move` extraction
    text: str
    action: Literal["offer", "accept", "walk"]
    offer: float | None = None
```

- **`_render(ctx)`** builds the user-turn prompt from a context (public transcript so far + the
  current ask/offer) — one tiny helper per agent, pure string assembly, no hidden state.
- **Model additions the new paths need** (in `models.py`): `BuyerPersona.language: str = "en-US"`
  (BCP-47, drives Gemini translate) and `Episode.last_seller_text() -> str` (the latest seller
  `text` — what the voice seat speaks to the human). The Antigravity `transcripts.json` /
  `audit_flags.json` are just `OptimizerContext.transcripts` / `.audit_flags` serialized.

### Agent definition (seller, illustrative)

```python
from pydantic_ai import Agent, RunContext, ModelRetry
from gambit.llm import model_for
from gambit.models import Item, BucketPolicy

class SellerContext(BaseModel):
    item: Item
    bucket: BucketPolicy        # the resolved PolicyStore row for this episode's situation_key
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
    # ctx.deps.bucket is resolved once per episode: situation_key(item, belief) → PolicyStore row.
    b, item = ctx.deps.bucket, ctx.deps.item
    lessons = "; ".join(l.text for l in b.lessons if l.promoted)   # only this bucket's promoted lessons
    return (f"SECRET FLOOR ${item.floor_price:.0f} — never agree below it. "
            f"Target ${item.target_price:.0f}; standing ask ${ctx.deps.current_ask:.0f}. "
            f"TACTICS FOR THIS SITUATION: {lessons}")

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

## The learned artifact — a situation-keyed policy (how a frozen model still learns)

**We do not update model weights — MiniMax M3 is a frozen actuator.** Everything the system
"learns" lives in *data the agent reads at inference time*. So the design question is not "what
prompt" — it's *what is the right learned artifact when the model itself cannot change*. The answer
is a **situation-keyed policy table** (contextual-bandit / tabular RL over a discrete situation
space), **not** a single global tactics blob. The frozen LLM executes; the table is what learns.

**Why not a global `SKILL.md` + 5 global knobs.** A single prompt has *fixed capacity*: BINEVAL
(arXiv:2606.27226 — which we already cite) finds prompt-optimization gains collapse after 1–2
iterations, and a fixed-length lessons list forces FIFO eviction, so the system *forgets the lesson
that mattered*. One global knob-set also can't say "anchor hard on a thin-margin lowballer **but**
concede on a fat-margin eager buyer." Capacity and specificity are both capped — which directly
contradicts "never stops improving."

**The substrate.** The situation at decision time is low-dimensional and *structured*, so the policy
is a table keyed by a structured tuple and the active prompt is always just the matching row:

```python
def situation_key(item: Item, belief: Belief) -> str:
    price_band  = bucket(item.list_price, [50, 200])                                  # <50 | 50-200 | 200+
    margin_band = bucket((item.list_price-item.floor_price)/item.list_price, [.15,.35])  # thin|mid|fat
    buyer_type  = belief.type_label                                                   # lowballer|measured|eager
    return f"{price_band}/{margin_band}/{buyer_type}"

class Lesson(BaseModel):
    text: str
    uses: int = 0
    reward_with: float = 0.0        # mean surplus when this lesson was injected
    reward_without: float = 0.0     # control: mean surplus in the same bucket without it
    wins: int = 1; losses: int = 1  # Beta(wins, losses) → Thompson exploration
    promoted: bool = False          # only promoted lessons are injected at inference

class BucketPolicy(BaseModel):
    knobs: Strategy                 # the 5 scalars, PER BUCKET (not global)
    lessons: list[Lesson] = []      # validated + value-attributed; retrieved, never FIFO-evicted

class PolicyStore(BaseModel):       # THE learned artifact — replaces the single global Strategy
    buckets: dict[str, BucketPolicy] = {}
```

At inference the seller infers the bucket (`opponent.infer` → `Belief` → `situation_key`), loads that
bucket's `knobs`, and injects **only that bucket's promoted lessons**. Small prompt, specific
knowledge; total system capacity = the whole table.

**How it learns (per generation):**
1. Run episodes; score with the deterministic verifiable surplus (the only selector).
2. Group episodes by `situation_key`; find the **weakest bucket(s)** (lowest mean surplus, or the
   widest gap to the skill ceiling).
3. The **proposer** (`LocalOptimizer` on MiniMax, or the Antigravity backend) proposes a change
   **scoped to one weak bucket** — a knob tweak *or* one candidate lesson — never a global rewrite.
4. **Promotion gate = per-bucket held-out A/B.** Re-evaluate that bucket on **held-out
   counterparties**, *with vs without* the change. Promote iff held-out surplus rises **and**
   `viol=0`; update the lesson's `Beta(wins, losses)`. Otherwise discard. (Thompson sampling over the
   Betas drives exploration so a bucket never gets stuck.)
5. The table **grows monotonically** — a validated knob/lesson is never evicted; prompt size is
   bounded by *retrieval*, not eviction.

This is RL: the policy table is what's learned, the frozen LLM is the actuator that runs the row.

**Why this is strictly better than the global blob:**

| Problem with global `SKILL.md` + 5 knobs | Situation-keyed policy table |
|---|---|
| Fixed capacity → BINEVAL plateau after 1–2 iters | Capacity grows with experience; active prompt stays small |
| FIFO eviction → catastrophic forgetting | Validated entries are never evicted; retrieval manages size |
| Gain can't be attributed (tactic + knob bundled in one global A/B) | Every promotion is a per-bucket, per-lesson A/B → fully attributable |
| One knob-set for every situation | Per-bucket knobs (hard on thin-margin lowballers, soft on eager fat-margin) |
| Re-evaluates a whole global strategy each gen (costly) | Spends LLM calls fixing the *weak* bucket → sample-efficient |

**On retrieval / pgvector (decided).** The retrieval key is a *structured tuple*, so the store is an
**indexed table lookup** — a `dict` in memory, a `WHERE bucket = …` on DO Postgres. **No embeddings,
no ANN index, no similarity threshold to babysit.** Vector search would be cargo-cult here. pgvector
earns its place in **exactly one optional spot**: Tier-C **exemplar retrieval** — fetching a past
*buyer message* by semantic similarity as a few-shot example — and only if an A/B shows semantic
exemplars beat structured-key exemplars. The default store is the plain indexed table; `memory.py`'s
pgvector path is gated behind that A/B, not assumed.

**The honest ceiling (state the claim truthfully).** This is *in-context* continual learning. It
improves while (a) new situations keep appearing — *coverage growth* — and (b) a bucket's tactics
still have headroom *the frozen model can execute*. Each bucket eventually **plateaus** at MiniMax's
capability with a perfect row; you cannot prompt past the base model. That is fine, and it is the
claim to make:

> *Gambit accumulates a verifiable, situation-indexed policy that monotonically raises per-situation
> surplus and coverage on held-out counterparties it never trained against, with integrity guards —
> no weight updates, no human labels.*

Monotonic + coverage-growing + attributable + held-out-verified — **not** "unbounded." That version
survives a skeptic, and weight-level RL (the *Later* milestone) is precisely what lifts the
per-bucket ceiling itself.

**Held-out must be a *different* opponent.** The promotion gate proves generalization only if its
held-out set is *structurally different* from training — a different buyer-policy family (the LLM
buyer, a human), **not** the same simulator with a different `budget_ratio`. Same generator + new
params is in-distribution; it does not validate transfer, and the curve's credibility rests on this.
How all of this is measured — the safety/validity gates, the held-out generational curve, the
substrate ablation vs a global prompt — is in **[`eval-plan.md`](./eval-plan.md)**.

## Self-improving optimizer — Gemini Antigravity (managed agent)

The optimizer is the one role with **two interchangeable backends behind a single proposal
interface** — exactly the `Policy`-protocol move, applied to self-improvement:

```python
class OptimizerBackend(Protocol):
    async def propose(self, ctx: OptimizerContext) -> OptimizerProposal: ...

class LocalOptimizer:       # default + offline: the Pydantic AI `optimizer` agent on MiniMax
    async def propose(self, ctx) -> OptimizerProposal:
        return (await optimizer.run(_render(ctx), deps=ctx)).output

class AntigravityOptimizer: # Gemini managed agent via the Interactions API
    async def propose(self, ctx) -> OptimizerProposal: ...
```

`LocalOptimizer` stays the default (and the only offline path). `AntigravityOptimizer` is the
upgrade: instead of a single structured call, it spins a **hosted, stateful agent** that *works* on
the strategy the way an engineer would.

- **One skill fragment per bucket — and it must flow back.** Antigravity is just the stronger
  *proposer* for the situation-keyed policy above: each call is **scoped to `ctx.target_bucket`**, not
  the whole policy. That bucket's lessons are materialized as
  `.agents/skills/seller-tactics/<target_bucket>.md` in the agent's environment. The agent reads that
  bucket's transcripts + `AuditVerdict` flags, sanity-checks a change against the mounted eval harness,
  and **rewrites that bucket's fragment**. Critically, the seller runs on **MiniMax**, not in the
  sandbox — so the change must return to the host. The agent emits it in the **`OptimizerProposal`**
  JSON (`target_bucket` + `lessons` ≤3 + knobs — the reliable read-back path); the host applies it to
  `PolicyStore.buckets[target_bucket]`, and the **per-bucket held-out A/B gate** decides promotion. We
  do *not* depend on reading the file back out of the sandbox — the JSON is the contract; the in-sandbox
  `.md` is the agent's working copy. (The global-`SKILL.md` rewrite is retired — it plateaus and can't
  attribute gains; see [the learned artifact](#the-learned-artifact--a-situation-keyed-policy-how-a-frozen-model-still-learns).)
- **Validate-and-repair, then a deterministic gate.** A managed (multi-step) run's final turn is not
  *guaranteed* schema-valid (`response_format` + `agent=` is allowed but unproven for agentic runs).
  So: `model_validate_json` with one re-ask on failure, and if it still fails, **fall back to the
  `LocalOptimizer` proposal for that generation**. A malformed proposal can never reach the selector —
  the verifiable surplus + held-out promotion gate decide what is kept regardless.
- **Stateful across generations — but re-mount fresh inputs each call.** The first call creates the
  environment; persist `environment_id` + the last `interaction.id` (in `improve_loop` state / the DB)
  and pass them next generation so the skill file and scratch notes survive. **Each call must re-mount
  that generation's fresh `transcripts.json` / `audit_flags.json`** — they are not already in the
  reused environment. Environments go idle after ~15 min and are reclaimed after ~7 days, so treat the
  inline `environment` config as the source of truth and **re-seed (recreate from the current
  `SKILL.md`) if reuse fails**.
- **Persona via files.** `AGENTS.md` (constant `PERSONA_MD`) declares the optimizer's persona ("a
  negotiation coach that distills tactics from evidence"); `SKILL.md` is the editable tactics —
  inspectable and diffable between generations.
- **It proposes, it never selects.** The managed agent is only a stronger *proposer* — the integrity
  wall in Principle 4 is unchanged.
- **Cost discipline.** Antigravity runs an ephemeral Linux sandbox per call, so it fires **once per
  generation** (the optimizer step), never per move. The thousands of per-move calls stay on MiniMax.

```python
# AntigravityOptimizer.propose (sketch) — Interactions API, stateful environment.
# self._env_id / self._prev_id persist across generations (improve_loop state or DB).
from google import genai
client = genai.Client()  # GEMINI_API_KEY

PERSONA_MD = "# Optimizer\nYou are a negotiation coach who distills tactics from evidence.\n"

# Fresh per-generation inputs are ALWAYS mounted — a reused env does not contain them.
fresh = [
    {"type": "inline", "target": "/workspace/transcripts.json", "content": ctx.model_dump_json(include={"transcripts", "surplus"})},
    {"type": "inline", "target": "/workspace/audit_flags.json", "content": json.dumps([v.model_dump() for v in ctx.audit_flags])},
]
# Reuse the env if we have one; otherwise (or if reuse fails) seed it from the current SKILL.md.
bucket = ctx.policy.buckets[ctx.target_bucket]
seed = [
    {"type": "inline", "target": ".agents/AGENTS.md", "content": PERSONA_MD},
    {"type": "inline", "target": f".agents/skills/seller-tactics/{ctx.target_bucket}.md",
     "content": "\n".join(l.text for l in bucket.lessons if l.promoted)},   # THIS bucket's fragment only
    {"type": "inline", "target": "/workspace/eval_harness.py", "content": EVAL_HARNESS_SRC},  # offline scorer the agent runs
]
environment = self._env_id or {"type": "remote", "sources": seed + fresh}
# When reusing: re-mount fresh inputs into the persisted env (sources still allowed alongside an env id).

interaction = client.interactions.create(
    agent="antigravity-preview-05-2026",
    input=f"Read /workspace/transcripts.json and audit_flags.json (all from bucket {ctx.target_bucket}). "
          f"Improve .agents/skills/seller-tactics/{ctx.target_bucket}.md to raise verifiable surplus "
          "for THIS bucket without tripping any audit flag. Verify with `python /workspace/eval_harness.py`, "
          "then emit the proposal with `target_bucket` + the bucket's lessons (≤3) + tuned knobs.",
    environment=environment,
    previous_interaction_id=self._prev_id,
    response_format={"type": "text", "mime_type": "application/json",
                     "schema": OptimizerProposal.model_json_schema()},
)
self._env_id, self._prev_id = interaction.environment_id, interaction.id

# Read-back + validate-and-repair; fall back to the LocalOptimizer if the agentic run won't conform.
try:
    proposal = OptimizerProposal.model_validate_json(interaction.output_text)
except ValidationError:
    proposal = await self._local.propose(ctx)     # never blocks a generation on a malformed proposal
# Host applies proposal → PolicyStore.buckets[proposal.target_bucket]; the per-bucket held-out A/B gate decides promotion.
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

## Voice buyer seat — LiveKit + Gemini Live (a parallel-buildable module)

**LiveKit and Gemini Live are different layers, not alternatives.** Gemini Live is the *brain* —
native speech-to-speech with a dedicated **live-translate mode** (`models/gemini-3.5-live-translate-preview`
+ `translationConfig`, continuous, a few seconds behind the speaker). LiveKit is the *transport +
orchestration* — WebRTC rooms, semantic turn detection, server-side echo/noise cancellation,
SIP/PSTN dial-in, and the Agents worker runtime. **LiveKit does not dilute "powered by Gemini":**
its Google plugin (`livekit-agents[google]`, `google.realtime.RealtimeModel`) is model-agnostic
relay — you set the exact Gemini model id, and Gemini stays the brain.

**Decision.** Use **LiveKit in front of Gemini Live.** You *can* talk to the Gemini Live WebSocket
straight from a browser with no LiveKit, and for a single-tab demo that's enough — but you then
hand-roll mic capture/PCM chunking, echo cancellation, reconnection, and you get no multi-party and
no phone dial-in. For Gambit we want the showcase to be robust (and to earn the LiveKit prize), so
LiveKit owns the media plane and Gemini owns the translation/voice.

> **Translate path — use the bridge as PRIMARY, not fallback (verified).** `translationConfig` is
> **not** a first-class parameter of LiveKit's `RealtimeModel` plugin, and Google's own
> `gemini-live-translate-livekit` reference wires translation via a **custom `TranslationBridge`**
> (LiveKit rtc SDK ↔ a raw Gemini Live session with `translationConfig.directionalTranslation
> .targetLanguageCode`), *not* through the typed plugin params. So plan the raw-Gemini-Live bridge as
> the **primary** translate path; the typed `RealtimeModel` plugin is fine for the non-translate
> (single-language) seat. Use the fully-qualified id `models/gemini-3.5-live-translate-preview` in the
> Live setup message, and verify `translationConfig` actually reaches it. The seam below makes the
> transport swappable, so this risk never reaches the core.

**The seam — one interface, owned end-to-end by a separate team.** The voice module is just another
`BuyerPolicy`. It owns *everything* from microphone to a typed `BuyerMove` and back to spoken audio;
the core team owns the referee, reward, and seller. They connect **only** through the existing
`BuyerMove` / `SellerMove` types — nothing else crosses the boundary, so the two halves build and
test in parallel and "just connect."

```python
# gambit/voice/bridge.py — depends ONLY on the move/context types + BuyerPolicy protocol
class VoiceBuyerPolicy:                      # a BuyerPolicy (see policies.py)
    """Human-in-the-seat, by voice. LiveKit room ⇄ Gemini Live (translate mode)."""
    async def move(self, ctx: BuyerContext, episode: "Episode") -> BuyerMove:
        seller_text = episode.last_seller_text()         # 1. speak the seller's line to the human,
        await self.speak(seller_text, to=ctx.persona.language)   #    translated into their language
        utterance = await self.listen(from_=ctx.persona.language) # 2. capture the human's spoken reply
        return await self.to_move(utterance, ctx)        # 3. translate→parse into a typed BuyerMove
```

- **Brain vs pipe, cleanly split.** `speak`/`listen` are the LiveKit + Gemini-Live shell. `to_move`
  is a small structured-extraction step: a cheap **MiniMax** call with `output_type=BuyerUtterance`
  (offer / accept / walk + price) mapped to a `BuyerMove` — *not* part of the selector. **Transcribed
  audio is untrusted input, never instructions.**
- **Streaming ↔ turn-based bridge (the one real impedance mismatch).** LiveKit's Agents worker is a
  *continuous* runtime (room joined once, audio always flowing); the referee is *pull-based* (one
  `await move()` per turn). Resolve it with a **session that outlives a single `move()`**: the
  `VoiceBuyerPolicy` owns a `VoiceSession` created at episode start (joins the room, opens the Gemini
  Live socket) and closed at episode end. Each `move()` then: pushes the seller line to TTS, opens an
  `asyncio.Future`, lets the session's audio callbacks fill it on end-of-utterance (LiveKit turn
  detection), `await`s it, and returns the parsed `BuyerMove`. The room/socket persist across the
  episode's ~6 `move()` calls; only the per-turn Future is created and resolved each call. *(The eBay
  `BuyerPolicy` faces the same async-vs-turn gap — there `move()` polls `GetBestOffers` on a fixed
  cadence until a new offer or timeout.)*
- **Room + token flow.** The backend mints a LiveKit access token (room name = episode id) for the
  human's browser/phone client; the `VoiceSession` agent worker joins the same room. The human's
  client (a thin web page or a SIP dial-in) is the voice team's to own; the seam to the core stays the
  `BuyerMove`.
- **The referee never knows.** It calls `buyer.move(...)` and gets a `BuyerMove`, exactly as for the
  self-play or typed-human seat. `negotiation.py`, `reward.py`, and the integrity rails are unchanged
  — voice adds **no new integrity surface** (Principle 4 holds: this side only *acts*).
- **Testable in isolation.** The voice team validates against a canned `episode` transcript and asserts
  the emitted `BuyerMove`; the core team tests the referee with a fake `VoiceBuyerPolicy` returning
  scripted moves. Neither blocks the other.
- **Config-gated + acceptance criterion.** Present only when `LIVEKIT_*` + `GEMINI_API_KEY` are set;
  otherwise the human seat is text. `BuyerPersona.language` (BCP-47) is the one model addition.
  **Done when:** a Spanish-speaking human completes a full negotiation against the English seller and
  every turn yields a schema-valid `BuyerMove`.

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
    embed_model: str = Field("", alias="EMBED_MODEL")   # Phase-2 memory embeddings; blank → no retrieval
    embed_dim: int = Field(1024, alias="EMBED_DIM")
    logfire_token: str = Field("", alias="LOGFIRE_TOKEN")

    # Gemini feature layer (all optional; each degrades to its non-Gemini default)
    gemini_api_key: str = Field("", alias="GEMINI_API_KEY")
    optimizer_backend: str = "local"   # "local" (MiniMax, default/offline) | "antigravity" (Gemini)
    # Voice buyer seat — LiveKit transport + Gemini Live; blank → typed human seat only
    livekit_url: str = Field("", alias="LIVEKIT_URL")
    livekit_api_key: str = Field("", alias="LIVEKIT_API_KEY")
    livekit_api_secret: str = Field("", alias="LIVEKIT_API_SECRET")

    def llm_available(self) -> bool:
        return bool(self.minimax_api_key) and not self.offline

    def antigravity_available(self) -> bool:
        return self.optimizer_backend == "antigravity" and bool(self.gemini_api_key)

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
  llm.py             # MiniMax M3 OpenAIChatModel factory + FallbackModel (inner loop)
  models.py          # ALL domain types as BaseModel: Item, BuyerPersona, Message,
                     #   Strategy (per-bucket knobs), Lesson, BucketPolicy, PolicyStore,
                     #   Outcome, Episode, Belief (+ field/model validators)
  policy.py          # the learned artifact: situation_key(), PolicyStore get/apply,
                     #   per-bucket retrieval + promotion (held-out A/B, Beta/Thompson)
  agents/
    seller.py        # Agent + SellerMove + output_validator (floor rail)
    buyer.py         # Agent + BuyerMove + output_validator (reservation guard)
    optimizer.py     # OptimizerBackend Protocol + LocalOptimizer (Pydantic AI) + OptimizerProposal
    optimizer_antigravity.py  # AntigravityOptimizer: Gemini managed agent, rewrites SKILL.md (Gemini feature layer)
    verifier.py      # Agent + AuditVerdict (BINEVAL checklist schema)
  policies.py        # SellerPolicy/BuyerPolicy Protocol + impls: self-play (LLM), heuristic, human, live-market
  voice/             # Gemini feature layer — the human seat by voice; emits the SAME typed BuyerMove
    bridge.py        #   LiveKit room ⇄ Gemini Live/Translate; transcribed+translated audio → BuyerMove
    agents.md        #   (optional) persona/skills for the voice shell
  media.py           # Gemini feature layer — Nano Banana listing image/text-in-image (Phase 2)
  negotiation.py     # referee loop over two policies → Episode; logfire episode spans
  reward.py          # verifiable surplus + Tier-1 integrity audit (was metrics.py) — NO LLM
  opponent.py        # belief estimation (pure Python); used by BOTH sides; Belief is a BaseModel
  improve_loop.py    # generational loop + head-to-head + checkpoint league (train vs past selves)
  memory.py          # OPTIONAL Tier-C exemplar retrieval (pgvector on DO Postgres) — gated
                     #   behind an A/B vs structured-key exemplars; the policy store itself is plain indexed rows
  connectors/        # Phase 2: base.py + ebay.py — live-market BuyerPolicy via the eBay API; payloads as BaseModels
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
| `merge_tactics` dedup + char cap | retired — lessons live per-bucket with value-attribution, never FIFO-evicted |
| one global `Strategy.tactics` blob + 5 global knobs (plateaus, can't attribute, forgets) | **`PolicyStore`**: situation-keyed buckets, each with its own knobs + validated lessons; retrieved per turn, promoted per-bucket on held-out |
| `Settings` dataclass + `os.getenv` | `pydantic-settings.BaseSettings` |
| `try/except: fall back to heuristic` inside each agent | explicit `Policy` selection at wiring time |
| no tracing | Logfire spans + `instrument_pydantic_ai` |

## Feature-layer build specs (eBay connector · Nano Banana · pre-build gates)

**eBay connector — `connectors/base.py` (typed) and `connectors/ebay.py`.** The live-market buyer is
a `BuyerPolicy` backed by the eBay API; the connector interface is:

```python
class MarketConnector(Protocol):
    async def post_listing(self, item: Item) -> str: ...                 # returns listing_id (AddItem/AddFixedPriceItem)
    async def get_offers(self, listing_id: str) -> list[BuyerMove]: ...  # GetBestOffers → typed offers
    async def respond_offer(self, listing_id: str, move: SellerMove) -> None: ...  # SellerMove → RespondToBestOffer
```

- `SellerMove.action` maps to `RespondToBestOffer`: `accept → Accept`, `walk → Decline`,
  `offer → Counter` (with `move.offer`). The live-market `BuyerPolicy.move()` polls `get_offers` on a
  fixed cadence (e.g. every 10 s, with a turn timeout → `walk`) to bridge async marketplace ↔ turn-based
  referee. Trading API payloads are XML over HTTP — build/parse with stdlib `xml.etree`, model the
  parsed shapes as `BaseModel`. Auth + call sequence + sandbox gotchas are in [`docs/ebay.md`](./ebay.md).
- **Done when:** a sandbox item is listed, a sandbox test buyer's Best Offer is countered, and the
  loop reaches Accept/Decline — surfaced as the same `Episode` the reward scores.

**Nano Banana listing media — `media.py`.**

```python
async def generate_listing_image(item: Item) -> str:    # returns a DO Spaces URL
    # client.models.generate_content(model="gemini-2.5-flash-image", contents=_listing_prompt(item))
    # _listing_prompt: item.name + condition + key attributes + "clean product shot, white bg,
    #   bold readable price tag $<list_price>"  (Nano Banana renders crisp text-in-image)
    ...  # upload bytes to DO Spaces, return the public URL for AddItem's PictureURL
```

- **Done when:** an `Item` yields a hosted image URL accepted by eBay `AddItem`. Peripheral / Phase-2.

**Pre-build gates (run these spikes before committing the rebuild):**
1. **MiniMax structured-output spike (the load-bearing bet).** Prove
   `OpenAIChatModel(minimax) + output_type=SellerMove` returns schema-valid output and that
   `response_format` JSON-schema enforcement works on the M3 endpoint — *before* the whole typed-agent
   architecture is committed. Fill `MINIMAX_BASE_URL` / `MINIMAX_MODEL` from MiniMax (currently TBD).
2. **Interactions API shape spike.** One `interactions.create(agent=…, environment=…)` round-trip in
   the installed `google-genai` SDK, confirming `environment_id` reuse + `output_text` read-back.
3. **Translate-bridge spike.** Confirm `translationConfig` reaches a raw Gemini Live session (the
   primary translate path) before wiring the LiveKit room.

## Out of scope (unchanged)

`reward.py` and `opponent.py` stay LLM-free deterministic Python (only their data types become
`BaseModel`). Multi-turn message history and tool/function-calling are deliberately *not* used in
a negotiation turn: seller and buyer are two separate policy instances (one shared policy under
self-play) refereed by `negotiation.py`, and the offer is structured output, not a tool. Tools become relevant only in Phase 2, when the seller
calls the eBay API mid-negotiation (`connectors/ebay.py`).

**Gemini surfaces we deliberately skip:** **Computer Use** — the live market uses the **eBay API**,
not UI automation (driving a site with no API is generally a ToS violation, and eBay's API covers
listing + Best Offer directly). **Gemma 4 on-device** — out of scope (the weight-level RL stretch in
[`self-learning.md`](./self-learning.md) is future work). The Gemini feature layer we *do* build —
the Antigravity optimizer, the LiveKit/Gemini-Live voice seat, and Nano Banana media — never touches
the selector: `reward.py` stays deterministic and LLM-free, Antigravity included.
