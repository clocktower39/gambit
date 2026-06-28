"""The domain-agnostic seam for the self-improvement engine.

The engine (PolicyStore, per-bucket held-out A/B promotion, improve_loop) depends
ONLY on these abstractions. A *domain* — negotiation is the first plug-in, not the
only one — supplies concrete policies, counterparties, and a deterministic verifiable
reward by implementing `Domain`. Nothing domain-specific (no prices, no "buyer")
belongs in this file. If you find yourself widening this for negotiation, stop and
generalize instead.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class EpisodeResult(BaseModel):
    """What one rollout yields to the engine — generic, no domain specifics.

    `reward` is the deterministic verifiable signal the engine selects on; `viol` is
    the integrity-violation count (a *clean* gain requires `viol == 0`); `skill` is an
    optional honest secondary metric (extraction vs. hidden ground truth) the engine
    reports but never selects on.
    """

    bucket: str = Field(min_length=1)              # situation_key(...) — the policy cell exercised
    reward: float = Field(ge=-1.0, le=1.0)         # deterministic verifiable reward (the selector)
    viol: int = Field(ge=0)                        # integrity violations; clean gain ⇒ 0
    seed: int                                      # the rollout seed (paired comparison / repro)
    skill: float | None = Field(default=None, ge=0.0, le=1.0)  # honest secondary metric


@runtime_checkable
class Policy(Protocol):
    """The artifact being improved. Opaque to the engine; a domain knows its shape
    (for negotiation: a parametric knob policy + per-bucket lessons)."""


@runtime_checkable
class Counterparty(Protocol):
    """The other side of an episode — a counterparty family, an environment, an opponent.
    Carries a `family` tag so held-out can be a *structurally different* family, not
    the same generator with new params."""

    family: str


@runtime_checkable
class Domain(Protocol):
    """The seam. The engine calls exactly this to gather learning signal."""

    def rollout(self, policy: Policy, counterparty: Counterparty, seed: int) -> EpisodeResult:
        """Run ONE deterministic episode (fully determined by `seed`) and score it.
        The reward must be a deterministic function of ground truth — never an LLM judge."""
        ...
