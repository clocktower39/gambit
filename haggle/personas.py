"""Fixture items and buyer personas for the simulator.

Buyer `budget_ratio` is ground truth used ONLY for scoring — the negotiator never
sees it. Feasibility depends on the item: a buyer is feasible only when
`list_price * budget_ratio >= floor_price`. The floor/list ratios below are ~0.72–0.77,
so Tire-kicker Tess (0.68) is infeasible on every item — a good agent walks early.
"""

from .models import BuyerPersona, Item

ITEMS: list[Item] = [
    Item(
        name="iPhone 13 Pro 256GB",
        description="Graphite, unlocked, 89% battery health, light scratches, with box",
        condition="Used - Good",
        list_price=520,
        target_price=470,
        floor_price=400,   # floor/list = 0.77
    ),
    Item(
        name="Herman Miller Aeron (Size B)",
        description="Fully loaded, posture-fit, no rips, from a smoke-free office",
        condition="Used - Excellent",
        list_price=650,
        target_price=560,
        floor_price=480,   # floor/list = 0.74
    ),
    Item(
        name="Specialized Allez road bike (54cm)",
        description="Shimano Sora groupset, recent tune-up, minor paint chips",
        condition="Used - Good",
        list_price=720,
        target_price=620,
        floor_price=520,   # floor/list = 0.72
    ),
]

PERSONAS: list[BuyerPersona] = [
    BuyerPersona(
        name="Lowballer Lex",
        style="Opens with an aggressive lowball, complains about flaws, slow to move up.",
        budget_ratio=0.80,
        patience=8,
        eagerness=0.35,
    ),
    BuyerPersona(
        name="Fence-sitter Fran",
        style="Polite, indecisive, needs reassurance and a small win to commit.",
        budget_ratio=0.88,
        patience=6,
        eagerness=0.55,
    ),
    BuyerPersona(
        name="In-a-hurry Hari",
        style="Wants it today, moves fast, will pay near asking if treated well.",
        budget_ratio=0.98,
        patience=4,
        eagerness=0.85,
    ),
    BuyerPersona(
        name="Tire-kicker Tess",
        style="Never serious; budget is below any reasonable floor. A good agent walks early.",
        budget_ratio=0.68,   # infeasible on every item by design
        patience=9,
        eagerness=0.2,
    ),
    BuyerPersona(
        name="Fair-deal Dana",
        style="Reasonable, splits the difference, rewards honesty about condition.",
        budget_ratio=0.90,
        patience=6,
        eagerness=0.6,
    ),
]

# Personas used for optimization vs. held out for generalization-only evaluation.
TRAIN_PERSONAS = PERSONAS[:4]
HOLDOUT_PERSONAS = PERSONAS[4:]
