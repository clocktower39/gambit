"""The continual-learning loop: evaluate the current strategy against the buyer
simulator, let the optimizer propose a better one, keep it if it scores higher,
repeat. The score curve climbing across generations IS the demo.

Early-stop guardrail (per BINEVAL, arXiv:2606.27226): prompt-optimization gains peak
then collapse, so we watch a HELD-OUT buyer population and stop when it stops
improving — the train score can keep rising on overfitting, the held-out won't."""

from __future__ import annotations

from .metrics import summarize
from .models import BuyerPersona, Episode, Item, Strategy
from .negotiation import run_episode
from .optimizer import propose
from .personas import HOLDOUT_PERSONAS, ITEMS, TRAIN_PERSONAS


def default_pairs(all_items: bool = True, personas=None) -> list[tuple[Item, BuyerPersona]]:
    items = ITEMS if all_items else ITEMS[:1]
    return [(it, p) for it in items for p in (personas or TRAIN_PERSONAS)]


def holdout_pairs(all_items: bool = True) -> list[tuple[Item, BuyerPersona]]:
    """Buyers the optimizer never trains on — for generalization + early-stop."""
    items = ITEMS if all_items else ITEMS[:1]
    return [(it, p) for it in items for p in HOLDOUT_PERSONAS]


def evaluate(strategy: Strategy, pairs, max_turns: int) -> tuple[list[Episode], dict]:
    episodes = [run_episode(it, p, strategy, max_turns) for it, p in pairs]
    return episodes, summarize(episodes)


def baseline_strategy() -> Strategy:
    """A deliberately mediocre starting point — a pushover that anchors at list and
    folds fast — so the self-improvement is visible."""
    return Strategy(
        name="gen0",
        gen=0,
        opening_anchor_ratio=1.0,
        concession_rate=0.60,
        accept_ratio=0.82,
        walkaway_patience=9,
        urgency=False,
        tactics="Be agreeable and close quickly; match the buyer so you don't lose the sale.",
    )


def _fmt(summary: dict) -> str:
    return (
        f"score={summary['score']:.3f}  close={summary['close_rate']:.0%}  "
        f"skill={summary['avg_skill']:.2f}  price=${summary['avg_price']:.0f}  "
        f"turns={summary['avg_turns']:.1f}  anchor={summary['first_offer_ratio']:.2f}  "
        f"viol={summary['overshoot_rate']:.0%}  deals={summary['deals']}/{summary['n']}"
    )


def improve(generations: int = 8, pairs=None, max_turns: int = 6, holdout=None,
            early_stop_patience: int = 3, verbose: bool = True) -> list[dict]:
    pairs = pairs or default_pairs()
    holdout = holdout if holdout is not None else holdout_pairs()
    best = baseline_strategy()
    eps, summ = evaluate(best, pairs, max_turns)
    best_score = summ["score"]
    best_ho = evaluate(best, holdout, max_turns)[1]["score"]
    history = [{"gen": 0, "strategy": best, "summary": summ, "holdout": best_ho}]
    if verbose:
        print(f"gen 0  {_fmt(summ)}  holdout={best_ho:.3f}")

    no_improve = 0
    for g in range(1, generations + 1):
        for cand in propose(best, eps, summ):
            c_eps, c_summ = evaluate(cand, pairs, max_turns)
            if c_summ["score"] > best_score + 1e-9:
                best, best_score, eps, summ = cand, c_summ["score"], c_eps, c_summ
        ho = evaluate(best, holdout, max_turns)[1]["score"]
        history.append({"gen": g, "strategy": best, "summary": summ, "holdout": ho})
        if verbose:
            print(f"gen {g}  {_fmt(summ)}  holdout={ho:.3f}")
        # Early-stop on the held-out signal (anti-overfitting / anti-collapse guard).
        if ho > best_ho + 1e-9:
            best_ho, no_improve = ho, 0
        else:
            no_improve += 1
            if early_stop_patience and no_improve >= early_stop_patience:
                if verbose:
                    print(f"  early-stop: held-out flat for {early_stop_patience} generations")
                break

    return history


def head_to_head(strat_a: Strategy, strat_b: Strategy, item: Item, persona: BuyerPersona,
                 max_turns: int = 6) -> tuple[Episode, Episode]:
    return (run_episode(item, persona, strat_a, max_turns),
            run_episode(item, persona, strat_b, max_turns))
