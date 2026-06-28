"""Opponent modeling + belief calibration.

The 2026 negotiation-eval frontier (TERMS-Bench arXiv:2605.13909, AgenticPay
arXiv:2602.06008) says "deal rate" is too weak a metric: a strong agent must
*infer the counterparty's latent type and reservation price from early turns* and
calibrate its beliefs, not just agree. This module gives Gambit that capability
and the eval dimension that measures it.

A buyer's successive offers ascend toward their hidden reservation price with
shrinking increments (a concave approach). We extrapolate that asymptote to
estimate the reservation, classify the buyer's type/urgency, and report a
belief-calibration error against the simulator's ground truth (sim-only — the
live agent never sees the true budget).

Self-contained and deterministic, so it runs offline with no API key:
    python3 -m gambit.opponent
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

from .models import Episode, Item, Strategy, budget_of

# Heuristic prior: offline/LLM buyers open at roughly this fraction of their
# reservation, used to estimate the reservation from a single observed offer.
_OPEN_FRACTION_PRIOR = 0.62


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


@dataclass
class Belief:
    reservation_est: float   # estimated max the buyer will pay
    urgency_est: float       # 0 = patient lowballer, 1 = eager / wants it now
    type_label: str          # "eager" | "measured" | "lowballer" | "unknown"
    confidence: float        # 0..1, grows with the number of observed offers


def estimate_from_offers(buyer_offers: list[float], list_price: float) -> Belief:
    """Infer the buyer's reservation price from their offer sequence."""
    offers = [o for o in buyer_offers if o is not None]
    if not offers:
        return Belief(reservation_est=list_price * 0.85, urgency_est=0.5,
                      type_label="unknown", confidence=0.0)

    if len(offers) == 1:
        reservation = offers[0] / _OPEN_FRACTION_PRIOR
        increments: list[float] = []
        confidence = 0.25
    else:
        increments = [max(offers[i + 1] - offers[i], 0.0) for i in range(len(offers) - 1)]
        last = offers[-1]
        # Geometric extrapolation of the shrinking increments -> remaining headroom.
        if len(increments) >= 2 and increments[-2] > 1e-6:
            ratio = _clamp(increments[-1] / increments[-2], 0.0, 0.95)
        else:
            ratio = 0.5
        remaining = increments[-1] * ratio / (1.0 - ratio) if ratio < 1.0 else 0.0
        reservation = last + remaining
        confidence = min(0.3 + 0.2 * len(increments), 0.9)

    span = max(reservation - offers[0], 1.0)
    # Big jumps relative to the journey, or reaching the asymptote in few steps,
    # both signal eagerness.
    urgency = _clamp(mean(increments) / span) if increments else 0.4
    if urgency > 0.45:
        type_label = "eager"
    elif offers[0] < 0.60 * reservation:
        type_label = "lowballer"
    else:
        type_label = "measured"

    return Belief(reservation_est=round(reservation, 1), urgency_est=round(urgency, 2),
                  type_label=type_label, confidence=round(confidence, 2))


def infer(ep: Episode) -> Belief:
    """Estimate the buyer's reservation from what's observable in the transcript."""
    offers = [m.offer for m in ep.messages if m.role == "buyer" and m.offer is not None]
    return estimate_from_offers(offers, ep.item.list_price)


def recommend_ask(belief: Belief, item: Item) -> float:
    """How an opponent-aware seller would price: hold just under the estimated
    reservation, never below the floor or above the list price."""
    target = belief.reservation_est * 0.98
    return round(max(item.floor_price, min(item.list_price, target)))


def calibration_report(episodes: list[Episode]) -> dict:
    """TERMS-Bench-style belief-calibration metric: how close our reservation
    estimate is to the buyer's true hidden budget, normalized by list price."""
    rows = []
    for ep in episodes:
        belief = infer(ep)
        truth = budget_of(ep.item, ep.persona)
        err = abs(belief.reservation_est - truth) / ep.item.list_price
        rows.append({"persona": ep.persona.name, "item": ep.item.name,
                     "est": belief.reservation_est, "true": truth,
                     "err": round(err, 3), "type": belief.type_label,
                     "urgency": belief.urgency_est})
    mean_err = mean(r["err"] for r in rows) if rows else 0.0
    return {"n": len(rows), "mean_abs_err": round(mean_err, 3),
            "accuracy": round(_clamp(1.0 - mean_err), 3), "rows": rows}


def _demo() -> None:
    from .negotiation import run_episode
    from .personas import ITEMS, PERSONAS

    strategy = Strategy(name="probe", opening_anchor_ratio=0.98, concession_rate=0.30,
                        accept_ratio=0.93, walkaway_patience=6)
    episodes = [run_episode(it, p, strategy, max_turns=6) for it in ITEMS for p in PERSONAS]
    report = calibration_report(episodes)

    print("=== Gambit — opponent modeling / belief calibration (offline) ===\n")
    print(f"{'buyer':<18}{'item':<28}{'est':>7}{'true':>7}{'err':>7}  type")
    for r in report["rows"]:
        print(f"{r['persona']:<18}{r['item']:<28}{r['est']:>7.0f}{r['true']:>7.0f}"
              f"{r['err']:>7.0%}  {r['type']}")
    print(f"\nbelief accuracy: {report['accuracy']:.0%}  "
          f"(mean reservation error {report['mean_abs_err']:.0%} of list price, n={report['n']})")


if __name__ == "__main__":
    _demo()
