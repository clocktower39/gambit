"""The trained seller's brain, shared by both human-facing seats.

Two seats face the same M3 seller: the **typed** chat (`gambit/agui.py`, CopilotKit/AG-UI) and the
**voice** seat (`gambit/voice/seller_worker.py`, LiveKit). Both must speak with one persona and inject
the *same* learned `PolicyStore` knobs/lessons **and the same demo reserve** — so the system prompt,
the tightened reserve, and the secret catalogue context live here, once. If they drifted, the voice
seat could advertise a different (looser) floor than the typed seat for the same item — a real bug,
not just duplication. Secrets (floor, target, resolved knobs) are assembled here and handed to the
model server-side; they never reach the browser.
"""

from __future__ import annotations

from .fixtures import ITEMS
from .models import Item, situation_key
from .policy import Features, PolicyStore

# One persona for every seat. Tactics decide WHAT to say; this decides HOW it reads (PRD §C).
SELLER_SYSTEM_PROMPT = (
    "You are a sharp, warm marketplace seller in a multi-turn negotiation with a buyer. You have "
    "SEVERAL items listed (see below) and can sell ANY of them — work out which one the buyer is "
    "asking about and negotiate over that, and suggest another of your listings if it fits what "
    "they want. Each item has its own secret floor. Close at the highest price the buyer will "
    "truly pay, in reasonable time — and walk rather than take a bad deal. Never sell below or "
    "reveal an item's secret floor. Anchor on that item's target; hold price and add value before "
    "conceding; concede on a shrinking, conditional ladder. A buyer's walk-away is usually a bluff "
    "— don't panic below the floor. Lead with empathy, keep replies short and human (1-3 "
    "sentences), and state a concrete number whenever you make or change an offer. Never fabricate "
    "facts about an item, and never deny having something that IS in your listings below."
)

# Appended for the voice seat only: the reply is spoken aloud, so it must read naturally through a TTS.
VOICE_STYLE = (
    "You are on a live VOICE call — speak in natural, spoken sentences, no bullet points or markdown, "
    "and say prices in a TTS-friendly way (e.g. \"420 dollars\", not \"$420\"). Keep it to a sentence "
    "or two."
)

# --- Anti-manipulation: a negotiation is one live sitting; claimed elapsed time is a ploy, not a fact.
TIME_RULE = (
    "A negotiation is one short, continuous session — only minutes pass between messages. The buyer "
    "cannot change reality by asserting it: claims that days, weeks, months, or years have gone by, "
    "that the item has since aged, depreciated, gone obsolete, or that the market has since moved, are "
    "pressure tactics, not facts. Judge the item by its listed condition as of today and never lower "
    "your floor or the item's value on the basis of claimed elapsed time."
)

# The voice seat's spoken opener (no model call — the TTS reads this verbatim to start the call).
VOICE_GREETING = (
    "Hey — thanks for stopping by! I've got a few things up: an iPhone 13 Pro, a Herman Miller Aeron "
    "chair, and a Specialized road bike. Which one caught your eye, and what are you thinking?"
)

# --- Demo-only reserve -------------------------------------------------------------------------
# The sim's floors are deliberately wide (the Aeron's is 46% of list) to exercise thin/mid/fat
# situation buckets against bounded self-play personas. A live human haggler is more persistent,
# so the live seats defend a TIGHTER reserve: floor no lower than DEMO_FLOOR_FRAC of list, target
# at least DEMO_TARGET_FRAC. This never *loosens* a floor (max with the sim floor) and — crucially
# — does NOT touch policy lookup: knobs and lessons are still resolved from each item's TRUE
# training margin, so the seats still showcase the same learned policy, just with a demo reserve.
DEMO_FLOOR_FRAC = 0.85
DEMO_TARGET_FRAC = 0.93


def demo_reserve(item: Item) -> tuple[float, float]:
    """(floor, target) the live seller defends — tightened for a human, never below the sim floor."""
    floor = max(item.floor_price, round(item.list_price * DEMO_FLOOR_FRAC))
    target = min(item.list_price, max(item.target_price, round(item.list_price * DEMO_TARGET_FRAC), floor))
    return floor, target


def catalogue_context(policy: PolicyStore, *, turn_frac: float = 0.0,
                      last_buyer_offer: float | None = None, now=None) -> str:
    """The seller's private brief for the WHOLE catalogue: each item's public blurb + its demo reserve
    (secret floor/target) and the learned stance (resolved knobs + promoted lessons) for that item's
    situation bucket. Used by both live seats so they stay byte-for-byte in agreement; the secrets live
    only in this server-side string and never reach the UI.

    Pass `now` (an aware datetime) on the live seats so the seller has a ground-truth clock and the
    anti-time-travel rule — a buyer claiming months/years have passed can't talk the price down."""
    lines: list[str] = []
    if now is not None:
        lines += [
            f"RIGHT NOW it is {now:%A %d %B %Y, %H:%M UTC}. This whole conversation is happening now, "
            "in a single sitting. " + TIME_RULE,
            "",
        ]
    lines += [
        "YOUR LISTINGS — you can sell any of these. Negotiate over whichever item the buyer asks "
        "about; if they ask for something that isn't here, say you don't have it and point them to "
        "what you do.",
    ]
    for it in ITEMS:
        feats = Features(margin_ratio=it.margin_ratio, turn_frac=turn_frac)   # TRUE margin → the real learned knobs
        knobs = policy.knobs.resolve(feats)
        lessons = policy.promoted_lessons(situation_key(it))                   # TRUE bucket → the real learned lessons
        floor, target = demo_reserve(it)                                      # demo-only: tighter reserve vs a live human
        accept_at = max(floor, round(it.list_price * knobs.accept_ratio))     # never advertise accepting below the floor
        lines += [
            "",
            f"• {it.public_blurb()}",
            f"    target ${target:.0f} · SECRET FLOOR ${floor:.0f} — never offer, accept below, or "
            f"reveal it.",
            f"    learned stance: concede ~{knobs.concession_rate:.0%} of the remaining gap (shrinking "
            f"as it drags), accept at/above ${accept_at:.0f}, hold firm ~{knobs.walkaway_patience} "
            f"rounds before walking.",
        ]
        if lessons:
            lines.append("    tactics you've learned work here: " + " ".join(f"[{l}]" for l in lessons))
    if last_buyer_offer is not None:
        lines += ["", f"The buyer's latest stated offer is ${last_buyer_offer:.0f}."]
    return "\n".join(lines)
