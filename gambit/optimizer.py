"""The self-improvement brain. Given the current strategy and how it just
performed, propose improved candidate strategies. With an LLM it reflects on
real transcripts and rewrites its own tactics + knobs (prompt optimization);
offline it does deterministic coordinate hill-climbing so the loop is testable."""

from __future__ import annotations

import random

from .config import llm_available
from .inference import chat_json
from .metrics import score_episode
from .models import Episode, Strategy


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


# Deterministic, incrementing seed so each call explores fresh candidates while
# staying fully reproducible run-to-run (no Math.random-style nondeterminism).
_offline_seed = [0]


def propose_offline(strategy: Strategy, n: int = 8) -> list[Strategy]:
    """Multi-knob local search. Perturbing several knobs at once lets the loop
    escape the plateaus that one-knob steps get stuck on (e.g. it must both lower
    walk-away patience to bail on hopeless lowballers AND keep enough patience to
    still close the feasible ones — a tradeoff no single-knob step can find)."""
    _offline_seed[0] += 1
    rng = random.Random(1000 + _offline_seed[0])
    candidates: list[Strategy] = []
    for _ in range(n):
        candidates.append(strategy.clone(
            name=f"gen{strategy.gen + 1}",
            gen=strategy.gen + 1,
            opening_anchor_ratio=_clamp(strategy.opening_anchor_ratio + rng.uniform(-0.08, 0.08), 0.90, 1.00),
            concession_rate=_clamp(strategy.concession_rate + rng.uniform(-0.18, 0.18), 0.05, 0.80),
            accept_ratio=_clamp(strategy.accept_ratio + rng.uniform(-0.05, 0.05), 0.80, 0.99),
            walkaway_patience=int(_clamp(strategy.walkaway_patience + rng.randint(-3, 3), 2, 10)),
            urgency=strategy.urgency if rng.random() > 0.25 else (not strategy.urgency),
        ))
    return candidates


def propose_llm(strategy: Strategy, episodes: list[Episode], summary: dict) -> list[Strategy]:
    """Reflect on transcripts and propose an improved strategy."""
    ranked = sorted(episodes, key=score_episode)
    worst = ranked[:2]
    best = ranked[-1:]
    samples = "\n\n".join(
        f"[score={score_episode(e):.2f}, outcome={e.outcome.reason}, "
        f"price={e.outcome.price}]\n{e.transcript()}"
        for e in worst + best
    )
    system = (
        "You are an expert negotiation coach improving a selling agent's policy. "
        "Diagnose what cost money or lost deals, then output a SHARPER strategy. "
        "Higher score = extracting more of the buyer's true willingness on winnable "
        "deals while still closing, and walking away fast from hopeless lowballers.\n"
        'Reply ONLY as JSON: {"tactics": "<= 3 sentences of concrete guidance", '
        '"opening_anchor_ratio": 0.9-1.0, "concession_rate": 0.05-0.8, '
        '"accept_ratio": 0.8-0.99, "walkaway_patience": 2-10, "urgency": true|false}'
    )
    user = (
        f"Current strategy tactics: {strategy.tactics}\n"
        f"Current knobs: anchor={strategy.opening_anchor_ratio}, concession={strategy.concession_rate}, "
        f"accept={strategy.accept_ratio}, patience={strategy.walkaway_patience}, urgency={strategy.urgency}\n"
        f"Last round metrics: {summary}\n\n"
        f"Representative transcripts (worst first, best last):\n{samples}\n\n"
        "Propose the improved strategy as JSON."
    )
    data = chat_json([
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ], temperature=0.5, max_tokens=400)
    cand = strategy.clone(
        name=f"gen{strategy.gen + 1}",
        gen=strategy.gen + 1,
        tactics=str(data.get("tactics", strategy.tactics)).strip() or strategy.tactics,
        opening_anchor_ratio=_clamp(float(data.get("opening_anchor_ratio", strategy.opening_anchor_ratio)), 0.9, 1.0),
        concession_rate=_clamp(float(data.get("concession_rate", strategy.concession_rate)), 0.05, 0.8),
        accept_ratio=_clamp(float(data.get("accept_ratio", strategy.accept_ratio)), 0.8, 0.99),
        walkaway_patience=int(_clamp(int(data.get("walkaway_patience", strategy.walkaway_patience)), 2, 10)),
        urgency=bool(data.get("urgency", strategy.urgency)),
    )
    return [cand]


def propose(strategy: Strategy, episodes: list[Episode], summary: dict) -> list[Strategy]:
    if llm_available():
        try:
            return propose_llm(strategy, episodes, summary)
        except Exception:
            pass
    return propose_offline(strategy)
