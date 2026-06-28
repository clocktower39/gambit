"""The self-improvement brain. Given the current strategy and how it just
performed, propose improved candidate strategies. With an LLM it reflects on real
transcripts and proposes TARGETED tactic lessons + knob changes; offline it does
deterministic coordinate hill-climbing so the loop is testable.

Anti-bloat guardrails (per BINEVAL, arXiv:2606.27226): the LLM path extracts a few
generalized *lessons* and MERGES them into the tactics prompt with dedup + a hard
length cap, instead of rewriting from scratch — so the prompt can't balloon and
collapse across generations."""

from __future__ import annotations

import random
import re

from . import verifier
from .config import llm_available
from .inference import chat_json
from .metrics import score_episode
from .models import Episode, Strategy

MAX_TACTIC_BULLETS = 5
MAX_TACTIC_CHARS = 500


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _bullets(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"[;\n•]+", text or "") if p.strip()]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def merge_tactics(current: str, lessons: list[str]) -> str:
    """Merge new lessons into the tactics prompt: drop exact + near-duplicates, keep
    the most recent bullets, and cap total length so the prompt never bloats."""
    out: list[str] = []
    seen: list[str] = []
    for raw in _bullets(current) + [str(x) for x in lessons]:
        b = raw.strip()
        n = _norm(b)
        if not n or any(n == s or n in s or s in n for s in seen):
            continue
        seen.append(n)
        out.append(b)
    out = out[-MAX_TACTIC_BULLETS:]                       # keep the most recent bullets
    while len(out) > 1 and len("; ".join(out)) > MAX_TACTIC_CHARS:
        out.pop(0)                                        # drop oldest until under the cap
    return "; ".join(out)


# Deterministic, incrementing seed: fresh candidates each call, reproducible run-to-run.
_offline_seed = [0]


def propose_offline(strategy: Strategy, n: int = 8) -> list[Strategy]:
    """Multi-knob local search. Perturbing several knobs at once lets the loop escape
    the plateaus single-knob steps get stuck on (e.g. it must both lower walk-away
    patience to bail on hopeless lowballers AND keep enough to still close feasible ones)."""
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
    """Reflect on transcripts; extract a few generalized lessons + tuned knobs."""
    ranked = sorted(episodes, key=score_episode)
    samples = "\n\n".join(
        f"[score={score_episode(e):.2f}, outcome={e.outcome.reason}, price={e.outcome.price}]\n{e.transcript()}"
        for e in ranked[:2] + ranked[-1:]
    )
    # Dense binary-rubric feedback (BINEVAL): audit the worst transcripts so the
    # optimizer makes TARGETED fixes. The rubric SHAPES proposals; it never selects
    # (selection stays on the verifiable surplus reward).
    rubric_notes: list[str] = []
    try:
        for e in ranked[:2]:
            r = verifier.verify_episode(e)
            if not r["clean"]:
                flags = ", ".join(
                    verifier.QLABEL.get(q, q) + (f" ({r['reasons'].get(q)})" if r["reasons"].get(q) else "")
                    for q in r["flags"]
                )
                rubric_notes.append(f"{e.item.name} vs {e.persona.name}: {flags}")
    except Exception:
        rubric_notes = []
    rubric_block = (
        "\nIntegrity/quality audit flags on losing transcripts (write a lesson that fixes each):\n- "
        + "\n- ".join(rubric_notes) + "\n"
    ) if rubric_notes else ""

    system = (
        "You are an expert negotiation coach improving a selling agent's policy. "
        "Diagnose what cost money or lost deals. Output at most THREE generalized, concrete "
        "lessons (each a short phrase, NOT a paragraph) plus tuned knobs — do NOT rewrite the "
        "whole strategy. Higher score = extracting more of the buyer's true willingness on "
        "winnable deals while still closing, and walking away fast from hopeless lowballers.\n"
        'Reply ONLY as JSON: {"lessons": ["short phrase", ...], '
        '"opening_anchor_ratio": 0.9-1.0, "concession_rate": 0.05-0.8, '
        '"accept_ratio": 0.8-0.99, "walkaway_patience": 2-10, "urgency": true|false}'
    )
    user = (
        f"Current tactics: {strategy.tactics}\n"
        f"Current knobs: anchor={strategy.opening_anchor_ratio}, concession={strategy.concession_rate}, "
        f"accept={strategy.accept_ratio}, patience={strategy.walkaway_patience}, urgency={strategy.urgency}\n"
        f"Last round metrics: {summary}\n\n"
        f"Representative transcripts (worst first, best last):\n{samples}\n"
        f"{rubric_block}\n"
        "Propose lessons + knobs as JSON."
    )
    data = chat_json([
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ], temperature=0.5, max_tokens=400)

    lessons = data.get("lessons", [])
    if isinstance(lessons, str):
        lessons = [lessons]
    cand = strategy.clone(
        name=f"gen{strategy.gen + 1}",
        gen=strategy.gen + 1,
        tactics=merge_tactics(strategy.tactics, lessons) or strategy.tactics,
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
