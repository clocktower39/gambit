"""Gemini Antigravity optimizer — the TEXTUAL-lesson half of the self-improvement loop.

The optimizer has two interchangeable backends behind one proposal interface
(docs/architecture.md "Self-improving optimizer — Gemini Antigravity"):

  - the LOCAL MiniMax optimizer owns the **parametric** channel (KnobPolicy.coeffs search), and
  - this AntigravityOptimizer owns the **textual** channel — the per-bucket `Lesson.text` table.

This module is the "actual Gemini" half: a hosted, managed agent that runs an ephemeral Linux
sandbox, reads ONE weak bucket's transcripts + audit signal, and proposes a single sharpened
tactical lesson for that bucket. It fires **once per generation** (cost discipline — the thousands
of per-move calls stay on MiniMax) and it **proposes, never selects**: the returned PolicyStore is
a *candidate*; the engine's paired held-out A/B gate (FDR + global non-regression) decides promotion.

Statefulness is the recursive-intelligence demo: successive `propose` calls in a run are chained via
`previous_interaction_id`, so the agent's scratch notes and the in-sandbox skill file survive across
generations. We persist `environment_id` (for reference/diffing) and the last interaction id (for
chaining) on the instance.

API path used: the real **Interactions API** (`client.interactions.create`) with the managed
`antigravity-preview-05-2026` agent — both are present in `google-genai` 2.9.0, matching the
architecture sketch. If that hosted-agent path is unavailable for the key/project, we fall back to
`client.models.generate_content` with a Gemini 3.5-class model so the textual proposal still works
live (documented fallback at `_propose_via_generate_content`); the Antigravity managed-agent path is
the target whenever it is provisioned.

How the engine calls this (once per generation, scoped to one weak bucket):

    opt = AntigravityOptimizer()                     # construct once per improve_loop run
    for generation in run:
        target = pick_weakest_bucket(...)            # the host chooses the bucket
        candidate = opt.propose(
            store=current_policy,                    # the live PolicyStore
            target_bucket=target,
            transcripts=recent_transcripts_for(target),
            performance={"reward": ..., "skill": ..., "viol": ...},
        )
        promote_if_gate_passes(candidate, target)    # held-out A/B decides — NOT this module
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from .negotiation.policy import BucketPolicy, Lesson, PolicyStore
from .settings import settings

# The hosted managed agent (a valid google-genai 2.9.0 AgentOption literal). Runs an ephemeral
# Linux sandbox per call — hence once-per-generation, never per move.
_AGENT_ID = "antigravity-preview-05-2026"

# Documented fallback only: a standard text model used iff the managed-agent path is unavailable.
_FALLBACK_MODEL = "gemini-3.5-flash"

# The agent's persona, mounted as a file so it is inspectable/diffable between generations.
_PERSONA_MD = (
    "# Optimizer\n"
    "You are a negotiation coach who distills durable, generalized tactics from evidence.\n"
)

# In-sandbox paths for the mounted working files (architecture: .agents/skills/seller-tactics/<bucket>.md).
_PERSONA_TARGET = ".agents/AGENTS.md"
_FRESH_TRANSCRIPTS = "/workspace/transcripts.json"
_FRESH_PERFORMANCE = "/workspace/performance.json"


def _skill_target(bucket: str) -> str:
    return f".agents/skills/seller-tactics/{bucket}.md"


# The read-back contract: the agent emits ONE atomic change (the strongest single lesson). Kept tiny
# and decoupled from PolicyStore so a malformed agentic turn can be validated/repaired in isolation.
class LessonProposal(BaseModel):
    """One atomic textual change for a single bucket — the JSON the managed agent returns."""

    target_bucket: str = Field(..., description="The bucket id this lesson applies to.")
    lesson: str = Field(..., description="One sharpened, generalized tactical lesson (a few sentences).")


class AntigravityOptimizer:
    """Hosted Gemini managed agent that proposes one textual lesson per generation for a weak bucket.

    Stateful across generations: chains interactions via `previous_interaction_id` so the agent's
    in-sandbox skill file and notes persist. Proposes only — promotion is the engine's held-out gate.
    """

    def __init__(self) -> None:
        # Lazy: no SDK import / client construction until the first propose call, so the module
        # imports cleanly even before `google-genai` finishes installing.
        self._client = None
        # Persisted across generations (the recursive-self-edit artifact). environment_id is kept for
        # reference/diffing; prev_interaction_id is what actually chains state on the next call.
        self.environment_id: str | None = None
        self.prev_interaction_id: str | None = None

    # ---- public API -------------------------------------------------------------------------

    def propose(
        self,
        store: PolicyStore,
        target_bucket: str,
        transcripts: list[str],
        performance: dict,
    ) -> PolicyStore:
        """Propose ONE improved lesson for `target_bucket`; return a NEW candidate PolicyStore.

        The candidate is a deep copy of `store` with a single un-promoted `Lesson` appended to
        `buckets[target_bucket]`. It is data, not a decision — the engine's paired held-out A/B
        gate decides whether to promote it. Never mutates the input store.
        """
        client = self._ensure_client()
        current = store.promoted_lessons(target_bucket)
        prompt = _render_prompt(target_bucket, current, performance)

        try:
            lesson_text = self._propose_via_interactions(client, store, target_bucket, transcripts, performance, prompt)
        except Exception as exc:  # hosted-agent path unavailable → keep the channel live via the model API
            lesson_text = self._propose_via_generate_content(client, prompt, exc)

        return _apply_proposal(store, target_bucket, lesson_text)

    # ---- the target path: the Antigravity managed agent over the Interactions API -------------

    def _propose_via_interactions(
        self,
        client,
        store: PolicyStore,
        target_bucket: str,
        transcripts: list[str],
        performance: dict,
        prompt: str,
    ) -> str:
        """Managed multi-step run: mount inputs, let the agent iterate in its sandbox, read one lesson.

        First call seeds the full environment (persona + this bucket's skill fragment); later calls
        chain via `previous_interaction_id` and only re-mount the fresh per-generation inputs — a
        reused environment does NOT already contain them.
        """
        bucket = store.buckets.get(target_bucket)
        promoted = "\n".join(l.text for l in bucket.lessons if l.promoted) if bucket else ""

        # Fresh inputs are ALWAYS mounted (architecture: re-mount each call even when reusing the env).
        fresh = [
            {"type": "inline", "target": _FRESH_TRANSCRIPTS, "content": json.dumps(transcripts)},
            {"type": "inline", "target": _FRESH_PERFORMANCE, "content": json.dumps(performance)},
        ]
        if self.prev_interaction_id is None:
            # Seed the environment the first time: persona + THIS bucket's lesson fragment only.
            seed = [
                {"type": "inline", "target": _PERSONA_TARGET, "content": _PERSONA_MD},
                {"type": "inline", "target": _skill_target(target_bucket), "content": promoted},
            ]
            sources = seed + fresh
        else:
            sources = fresh

        body: dict = {
            "agent": _AGENT_ID,
            "input": prompt,
            "environment": {"type": "remote", "sources": sources},
            # Ask for JSON matching the one-atomic-change contract. The prompt also spells the shape
            # out, so read-back stays robust even if an agentic final turn isn't strictly conformant.
            "response_format": {
                "type": "text",
                "mime_type": "application/json",
                "schema": LessonProposal.model_json_schema(),
            },
        }
        if self.prev_interaction_id is not None:
            body["previous_interaction_id"] = self.prev_interaction_id

        interaction = client.interactions.create(body=body)

        # Persist state for the next generation (the chaining + the env we can diff against).
        self.environment_id = getattr(interaction, "environment_id", None) or self.environment_id
        self.prev_interaction_id = getattr(interaction, "id", None) or self.prev_interaction_id

        return _read_lesson(interaction.output_text)

    # ---- documented fallback: standard text model so the textual channel still works live --------

    def _propose_via_generate_content(self, client, prompt: str, cause: Exception) -> str:
        """Fallback when the managed-agent path is unavailable for this key/project.

        Uses a single `generate_content` call (no sandbox, no multi-step loop) just to keep the
        textual-lesson proposal alive. The Antigravity managed agent is the target once provisioned.
        """
        try:
            from google.genai import types  # lazy: only needed on the fallback path

            resp = client.models.generate_content(
                model=_FALLBACK_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=LessonProposal,
                ),
            )
            return _read_lesson(resp.text)
        except Exception as exc:
            raise RuntimeError(
                "AntigravityOptimizer: both the Interactions managed-agent path and the "
                f"generate_content fallback failed. Interactions error: {cause!r}. "
                f"Fallback error: {exc!r}."
            ) from exc

    # ---- internals ---------------------------------------------------------------------------

    def _ensure_client(self):
        """Build (and cache) the genai client lazily, with an actionable error if the dep/key is absent."""
        if self._client is not None:
            return self._client
        try:
            from google import genai  # lazy import: module stays importable before the dep installs
        except ImportError as exc:
            raise ImportError(
                "AntigravityOptimizer needs the `google-genai` package. Install it with "
                "`uv sync --group feature-layer` (or `uv add google-genai`)."
            ) from exc
        if not settings.gemini_api_key:
            raise RuntimeError(
                "AntigravityOptimizer needs GEMINI_API_KEY set (settings.gemini_api_key is empty). "
                "Add it to .env."
            )
        self._client = genai.Client(api_key=settings.gemini_api_key)
        return self._client


def _render_prompt(target_bucket: str, current_lessons: list[str], performance: dict) -> str:
    """Assemble the once-per-generation instruction: sharpen ONE lesson for this bucket, anti-bloat."""
    current = "\n".join(f"- {t}" for t in current_lessons) if current_lessons else "(none yet)"
    return (
        f"You are improving the seller's tactics for ONE situation bucket: `{target_bucket}`.\n\n"
        f"Current promoted lesson(s) for this bucket:\n{current}\n\n"
        f"Current measured performance for this bucket (higher reward/skill is better, lower viol is "
        f"better):\n{json.dumps(performance, indent=2)}\n\n"
        f"Read the mounted negotiation transcripts ({_FRESH_TRANSCRIPTS}) and performance "
        f"({_FRESH_PERFORMANCE}) for this bucket. Then propose ONE improved, generalized tactical "
        f"lesson (a few sentences) that should raise verifiable surplus for THIS bucket without "
        f"tripping any integrity/audit flag.\n\n"
        f"Anti-bloat rules: do NOT restate or lightly reword an existing lesson — sharpen or replace "
        f"it. Prefer one durable, transferable principle over situational trivia. Output a single "
        f"strongest lesson.\n\n"
        f"Return JSON only: {{\"target_bucket\": \"{target_bucket}\", \"lesson\": \"...\"}}."
    )


def _read_lesson(output_text: str | None) -> str:
    """Validate-and-repair read-back: parse the JSON contract, else recover the lesson text.

    A malformed proposal can never reach the selector (the held-out gate decides regardless), so we
    are lenient: prefer the schema, fall back to any embedded JSON object, finally the raw text.
    """
    if not output_text:
        raise RuntimeError("AntigravityOptimizer: empty output from the optimizer agent.")
    text = output_text.strip()
    # Strip a fenced ```json block if the model wrapped its output.
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("\n") + 1 :] if "\n" in text else text
        if text.lstrip().startswith("json"):
            text = text.lstrip()[4:]
    try:
        return LessonProposal.model_validate_json(text).lesson.strip()
    except Exception:
        pass
    # Best-effort recovery: pull the first {...} object out of the text.
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(text[start : end + 1])
            lesson = obj.get("lesson")
            if isinstance(lesson, str) and lesson.strip():
                return lesson.strip()
        except Exception:
            pass
    # Last resort: treat the whole response as the lesson (the gate still guards promotion).
    return text


def _apply_proposal(store: PolicyStore, target_bucket: str, lesson_text: str) -> PolicyStore:
    """Return a deep copy of `store` with one new un-promoted Lesson in `target_bucket`.

    Promotion stats are left at defaults — this is a candidate; the engine's held-out gate sets
    `promoted`/`gate_delta`/`support` if it wins.
    """
    candidate = store.model_copy(deep=True)
    bucket = candidate.buckets.setdefault(target_bucket, BucketPolicy())
    bucket.lessons.append(Lesson(text=lesson_text))
    return candidate


if __name__ == "__main__":  # best-effort live smoke: build a tiny store, propose, print the lesson
    demo_store = PolicyStore()
    demo_store.buckets["lowballer"] = BucketPolicy(
        lessons=[Lesson(text="Hold firm near list on the first counter.", promoted=True)]
    )
    demo_transcripts = [
        "Buyer: I'll give you $40 for the $100 item. Seller: I can do $92, it's barely used.",
        "Buyer: $50 final. Seller: $88 and I'll include shipping.",
    ]
    demo_perf = {"reward": 0.41, "skill": 0.38, "viol": 0}

    print("Calling AntigravityOptimizer.propose(...) on bucket 'lowballer' ...")
    try:
        opt = AntigravityOptimizer()
        result = opt.propose(demo_store, "lowballer", demo_transcripts, demo_perf)
        new_lessons = [l.text for l in result.buckets["lowballer"].lessons]
        print("\nProposed lesson:\n  ", new_lessons[-1])
        print("\nenvironment_id:", opt.environment_id, "| prev_interaction_id:", opt.prev_interaction_id)
    except Exception as e:  # noqa: BLE001 — smoke must report, not crash the inspection
        print(f"\nLive call could not complete: {type(e).__name__}: {e}")
        print("(Module imports + builds the proposal correctly; set GEMINI_API_KEY to run live.)")
