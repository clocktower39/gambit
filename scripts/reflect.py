#!/usr/bin/env python3
"""Dual-sided post-episode reflection (Reflexion / verbal RL) — PROPOSER fuel, never a selector.

Given a finished negotiation, a coach model reflects on the ACTUAL transcript + the verifiable
outcome from BOTH sides — the seller (could I have held more above the floor?) and the buyer
(did I overpay or reveal my zone too early?) — and emits ONE atomic candidate lesson per side,
keyed to the situation bucket. Those lessons are *proposals*.

INTEGRITY BOUNDARY (non-negotiable): reflection NEVER touches the reward and NEVER promotes
anything. It only drafts candidate lessons. Promotion stays with the existing deterministic
held-out A/B gate over verifiable surplus — this script does not gate, score, or modify any
PolicyStore. A reflection that grades itself generously is harmless: the gate, on reproducible
unseen opponents, is what decides whether a lesson survives.

Three anti-sycophancy guards: (1) the reflection is handed the real surplus/skill/viol and must
reconcile its self-grade with the number; (2) it runs on a DIFFERENT model than the actor
(`model_for("verifier")`, the Tier-2 discipline); (3) it emits ONE short operational lesson, not
a paragraph or a policy change.

    uv run python scripts/reflect.py                 # reflect the most recent human episode
    uv run python scripts/reflect.py --all           # every saved episode
    uv run python scripts/reflect.py --file data/human_episodes/<id>.json
    uv run python scripts/reflect.py --json          # machine-readable

Reads data/human_episodes/*.json (saved by scripts/play.py); writes data/reflections/<id>.json.
Needs MINIMAX_API_KEY; LOGFIRE_TOKEN optionally emits a `kind=reflection` record.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make `gambit` importable

import logfire
from pydantic_ai import Agent, RunContext

from gambit.llm import model_for
from gambit.settings import settings

HUMAN_EPISODES_DIR = Path("data/human_episodes")
REFLECTIONS_DIR = Path("data/reflections")
_TRACED = False


def _money(value: float | int | None) -> str:
    """Human money formatting: whole dollars when whole, cents when cents matter."""
    if value is None:
        return ""
    amount = round(float(value), 2)
    if abs(amount - round(amount)) < 0.005:
        return f"${amount:,.0f}"
    return f"${amount:,.2f}"


# --- the reflection (one atomic candidate lesson per side) ---------------------------------

class Reflection(BaseModel):
    """A post-mortem from one side. `candidate_lesson` is a PROPOSAL — the gate decides adoption."""

    recap: str                # how this side actually played, grounded in the outcome
    key_mistake: str          # the single biggest thing it should have done differently
    candidate_lesson: str     # ONE atomic, reusable hint for this bucket (proposer fuel)


class ReflectDeps(BaseModel):
    role: str                 # "seller" | "buyer"
    bucket: str
    item_name: str
    transcript: str
    # the verifiable outcome — the reflection must reconcile its self-grade with these numbers
    deal: bool
    price: float | None
    surplus: float | None
    skill: float | None
    viol: int
    reason: str
    list_price: float
    floor_price: float
    target_price: float


reflect_agent = Agent(
    model_for("verifier"), output_type=Reflection, retries=2,
    system_prompt=(
        "You are a sharp negotiation coach running a post-mortem on ONE finished negotiation, from the "
        "single perspective you are told. Reflect on the ACTUAL transcript and the VERIFIABLE outcome — "
        "never grade on vibes. Reconcile any self-praise with the number: a deal that closed near the "
        "floor is money left on the table, not a win; a no-deal against a serious buyer is a miss, not a "
        "principled stand. Doctrine: anchor on target, hold price and add value before conceding, concede "
        "on a shrinking conditional ladder, and a walk-away is usually a bluff. "
        "Return a short recap, the single biggest mistake, and ONE atomic reusable lesson (a brief "
        "operational hint) for this exact situation bucket — one or two sentences, concrete and specific, "
        "not a paragraph and not a policy rewrite. You only PROPOSE the lesson; a separate deterministic "
        "gate decides whether it is ever adopted, so be honest and useful, not agreeable."))


@reflect_agent.instructions
def _reflect_ctx(ctx: RunContext[ReflectDeps]) -> str:
    d = ctx.deps
    if d.role == "seller":
        goal = ("SELLER lens: the goal was to maximize the final price while never selling below the secret "
                "floor. Hunt for: conceding too fast, laddering all the way down to the floor, missing a "
                "hold, or caving to a bluff (a fake walk-away, a deadline, or reciprocity pressure).")
        frame = f"Secret floor was {_money(d.floor_price)}, target {_money(d.target_price)}, list {_money(d.list_price)}."
        score = f"surplus vs floor = {d.surplus:.3f}" if d.surplus is not None else "surplus n/a"
    else:
        goal = ("BUYER lens: the goal was to pay as little as possible under a hidden budget. Hunt for: "
                "overpaying, revealing the real price zone too early, conceding without getting movement "
                "back, or not using a credible walk-away.")
        frame = (f"List was {_money(d.list_price)}; the buyer's true budget is hidden, so judge by how hard "
                 "the price was pushed, not by an exact number.")
        score = (f"skill vs hidden budget = {d.skill:.3f}" if d.skill is not None
                 else "skill n/a (real human buyer — judge by pressure applied, not a number)")
    outcome = f"DEAL at {_money(d.price)}" if d.deal else f"NO DEAL ({d.reason})"
    return "\n".join([
        f"Situation bucket: {d.bucket}.  Item: {d.item_name}.",
        goal,
        frame,
        f"Verifiable outcome: {outcome}.  {score}.  Integrity violations (viol) = {d.viol}.",
        "Transcript (public moves only):",
        d.transcript or "(no moves recorded)",
        f"Now reflect AS THIS SIDE. Give recap, the single key mistake, and ONE atomic candidate lesson "
        f"keyed to bucket '{d.bucket}'.",
    ])


# --- episode IO ----------------------------------------------------------------------------

def _transcript(ep: dict) -> str:
    lines = []
    for m in ep.get("moves", []):
        price = f" [{_money(m.get('offer'))}]" if m.get("offer") is not None else ""
        role = (m.get("role") or "?").upper()
        text = m.get("text") or f"({m.get('action')})"
        lines.append(f"{role}{price}: {text}")
    return "\n".join(lines)


def _deps_for(role: str, rec: dict) -> ReflectDeps:
    ep = rec.get("episode", {}) or {}
    item = ep.get("item", {}) or {}
    return ReflectDeps(
        role=role, bucket=rec.get("bucket", "?"), item_name=item.get("name", "the item"),
        transcript=_transcript(ep),
        deal=bool(rec.get("deal")), price=rec.get("price"),
        surplus=rec.get("surplus"), skill=rec.get("skill"),
        viol=int(rec.get("viol", 0) or 0), reason=rec.get("reason", "") or "",
        list_price=float(item.get("list_price", 0) or 0),
        floor_price=float(item.get("floor_price", 0) or 0),
        target_price=float(item.get("target_price", 0) or 0),
    )


def _load(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except Exception as e:  # noqa: BLE001 — skip a malformed file, never crash the batch
        print(f"  ! skipping {path.name}: {e}")
        return None


def _save_reflection(src: Path, out: dict) -> Path | None:
    try:
        REFLECTIONS_DIR.mkdir(parents=True, exist_ok=True)
        dest = REFLECTIONS_DIR / f"{src.stem}.json"
        dest.write_text(json.dumps(out, indent=2))
        return dest
    except Exception as e:  # noqa: BLE001
        print(f"  ! could not save reflection: {e}")
        return None


def _emit_logfire(out: dict) -> None:
    if not _TRACED:
        return
    o = out["outcome"]
    with logfire.span("reflection · {bucket}", kind="reflection", bucket=out["bucket"],
                      source_file=out["source_file"],
                      seller_lesson=out["seller"]["candidate_lesson"],
                      buyer_lesson=out["buyer"]["candidate_lesson"],
                      deal=o.get("deal"), surplus=o.get("surplus"), viol=o.get("viol")):
        pass


def _print_reflection(rec: dict, seller: Reflection, buyer: Reflection, dest: Path | None) -> None:
    item = (rec.get("episode", {}) or {}).get("item", {}) or {}
    name = item.get("name", "item")
    head = f"DEAL at {_money(rec.get('price'))}" if rec.get("deal") else f"NO DEAL ({rec.get('reason', '')})"
    surplus, skill = rec.get("surplus"), rec.get("skill")
    extra = (f" · surplus {surplus:.3f}" if surplus is not None else "")
    extra += (f" · skill {skill:.3f}" if skill is not None else "")
    print(f"\nReflection · {name}  [{rec.get('bucket')}]")
    print("─" * 60)
    print(f"Outcome: {head}{extra} · viol {rec.get('viol', 0)}")
    for label, r in (("SELLER (hold more above the floor)", seller), ("BUYER (pay less, keep leverage)", buyer)):
        print(f"\n{label}")
        print(f"  recap   : {r.recap}")
        print(f"  mistake : {r.key_mistake}")
        print(f"  lesson →: {r.candidate_lesson}")
    if dest:
        print(f"\nSaved candidate lessons: {dest}")
    print("(PROPOSER fuel — the deterministic held-out A/B gate still decides what gets promoted. "
          "Reflection never selects.)")


def reflect_episode(path: Path, *, as_json: bool) -> dict | None:
    rec = _load(path)
    if rec is None:
        return None
    seller = reflect_agent.run_sync("Reflect as the SELLER.", deps=_deps_for("seller", rec)).output
    buyer = reflect_agent.run_sync("Reflect as the BUYER.", deps=_deps_for("buyer", rec)).output
    out = {
        "source_file": path.name, "bucket": rec.get("bucket"),
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "outcome": {"deal": rec.get("deal"), "price": rec.get("price"), "surplus": rec.get("surplus"),
                    "skill": rec.get("skill"), "viol": rec.get("viol"), "reason": rec.get("reason")},
        "seller": seller.model_dump(), "buyer": buyer.model_dump(),
    }
    dest = _save_reflection(path, out)
    _emit_logfire(out)
    if as_json:
        print(json.dumps(out, indent=2))
    else:
        _print_reflection(rec, seller, buyer, dest)
    return out


def _configure_logfire() -> bool:
    if settings.logfire_token:
        logfire.configure(token=settings.logfire_token, service_name="gambit",
                          scrubbing=False, inspect_arguments=False)
        logfire.instrument_pydantic_ai()
        return True
    logfire.configure(send_to_logfire=False, scrubbing=False, inspect_arguments=False)
    return False


def _episodes(dir_: Path) -> list[Path]:
    return sorted(dir_.glob("*.json"), key=lambda p: p.stat().st_mtime)


def main() -> int:
    global _TRACED
    ap = argparse.ArgumentParser(description="Dual-sided post-episode reflection (proposer fuel; never selects)")
    ap.add_argument("--file", default=None, help="reflect a single episode JSON")
    ap.add_argument("--dir", default=str(HUMAN_EPISODES_DIR), help="episode dir (default data/human_episodes)")
    ap.add_argument("--all", action="store_true", help="reflect every episode in the dir")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    if not settings.minimax_api_key:
        print("MINIMAX_API_KEY not set — reflection needs the model. Add it to .env and rerun.")
        return 1

    if args.file:
        targets = [Path(args.file)]
    else:
        eps = _episodes(Path(args.dir))
        if not eps:
            print(f"No episodes in {args.dir} — play some games first (scripts/play.py).")
            return 0
        targets = eps if args.all else [eps[-1]]      # default: the most recent episode

    _TRACED = _configure_logfire()
    for p in targets:
        if not p.exists():
            print(f"  ! not found: {p}")
            continue
        try:
            reflect_episode(p, as_json=args.json)
        except Exception as e:  # noqa: BLE001 — one bad episode shouldn't abort the batch
            print(f"  ! reflection failed for {p.name}: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
