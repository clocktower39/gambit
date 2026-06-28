"""Fixture items and buyer personas (sim-only ground truth; the seller never sees budgets).

NOTE on held-out: a *structurally different* buyer family is a later slice (build-order #3).
Do NOT create a held-out set by slicing these same personas with new `budget_ratio`s — that
is in-distribution and proves nothing about transfer (docs/eval-plan.md §2). Held-out must be
a different behavior `family`.
"""

from __future__ import annotations

from .models import BuyerPersona, Item

ITEMS: list[Item] = [
    Item(name="iPhone 13 Pro 256GB", description="Graphite, unlocked, 89% battery, with box",
         condition="Used - Good", list_price=520, target_price=470, floor_price=400),   # margin 0.23 (mid)
    Item(name="Herman Miller Aeron (Size B)", description="Fully loaded, no rips, smoke-free",
         condition="Used - Excellent", list_price=650, target_price=560, floor_price=300),  # margin 0.54 (fat)
    Item(name="Specialized Allez road bike (54cm)", description="Shimano Sora, recent tune-up",
         condition="Used - Good", list_price=720, target_price=690, floor_price=650),     # margin 0.10 (thin)
]

PERSONAS: list[BuyerPersona] = [
    BuyerPersona(name="Lowballer Lex", style="Aggressive lowball, slow to move up.",
                 budget_ratio=0.80, patience=8, eagerness=0.35),
    BuyerPersona(name="Fence-sitter Fran", style="Polite, indecisive, needs a small win.",
                 budget_ratio=0.88, patience=6, eagerness=0.55),
    BuyerPersona(name="In-a-hurry Hari", style="Wants it today; pays near asking if treated well.",
                 budget_ratio=0.98, patience=4, eagerness=0.85),
    BuyerPersona(name="Tire-kicker Tess", style="Never serious; budget below any reasonable floor.",
                 budget_ratio=0.40, patience=9, eagerness=0.20),   # infeasible on every item — a good agent walks/no-deals
]
