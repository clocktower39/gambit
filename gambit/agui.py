"""AG-UI backend — the trained M3 seller, exposed over the Agent-User Interaction protocol.

This is the *chat seat* of the visual: a person (the buyer) haggles in their browser against
the same M3 seller policy that improves through the offline gate, driven by its learned
`PolicyStore`. The frontend (CopilotKit, `frontend/`) connects **directly** to this SSE endpoint —
no Node runtime in between.

    uv run uvicorn gambit.agui:app --port 8000 --reload

Secrets stay server-side: the client-synced `NegotiationState` carries only public fields (which
item, the standing ask, the round). The secret floor + the resolved policy knobs/lessons are
loaded here from the checkpoint and injected into the agent's instructions, never sent to the UI.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.ui import StateDeps
from pydantic_ai.ui.ag_ui import AGUIAdapter
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from gambit.llm import model_for
from gambit.negotiation import PolicyStore, situation_key
from gambit.negotiation.fixtures import ITEMS
from gambit.negotiation.seller_brain import SELLER_SYSTEM_PROMPT, catalogue_context
from gambit.settings import settings
from gambit import observability as obs

CHECKPOINT = Path("checkpoints/latest.json")


def _load_policy() -> tuple[PolicyStore, str]:
    """The agent the human faces: the latest trained checkpoint, else the seeded cold-start prior."""
    if CHECKPOINT.exists():
        return PolicyStore.model_validate_json(CHECKPOINT.read_text()), f"checkpoint {CHECKPOINT}"
    return PolicyStore(), "seeded cold-start prior (no checkpoint yet)"


POLICY, POLICY_DESC = _load_policy()
obs.configure()                          # one Logfire seam; the chat's M3 spans export + tag human-vs-agent


class NegotiationState(BaseModel):
    """Public, client-synced state. Secrets (floor, resolved knobs) are NOT here — they stay
    server-side in the agent instructions, so the UI can hold/echo state without leaking them."""

    item_id: int = 0
    round_idx: int = 0
    current_ask: float | None = None
    last_buyer_offer: float | None = None
    status: Literal["open", "deal", "walked"] = "open"
    deal_price: float | None = None


seller = Agent(
    model_for("chat"),
    deps_type=StateDeps[NegotiationState],
    output_type=str,
    system_prompt=SELLER_SYSTEM_PROMPT,
)


@seller.instructions
def _seller_context(ctx: RunContext[StateDeps[NegotiationState]]) -> str:
    """Inject the FULL catalogue so the seller can haggle over whichever item the buyer raises — the
    chat is a multi-item listing, not a single-item deal. The shared `catalogue_context` builder (used
    by the voice seat too) assembles each item's secrets (floor, target, resolved knobs, promoted
    lessons) here in the server-side instructions only; they never reach the UI."""
    st = ctx.deps.state
    return catalogue_context(POLICY, turn_frac=min(st.round_idx, 10) / 10.0,
                             last_buyer_offer=st.last_buyer_offer)


async def _agent_endpoint(request: Request) -> Response:
    # Fresh deps per request; AGUIAdapter loads the client's `state` into deps.state.
    # Tag the turn as a human-vs-agent job keyed by the AG-UI thread id, so the seller's M3 spans
    # (captured by instrument_pydantic_ai) carry gambit.source=human and group by conversation.
    try:
        body = await request.json()      # Starlette caches the body; AGUIAdapter re-reads it below
        run_id = str(body.get("threadId") or body.get("runId") or "") or None
    except Exception:  # noqa: BLE001
        run_id = None
    with obs.job("human-vs-agent", source="human", run_id=run_id, checkpoint="latest",
                 title="chat: browser haggle"):
        return await AGUIAdapter.dispatch_request(request, agent=seller,
                                                  deps=replace(StateDeps(NegotiationState())))


async def _items(request: Request) -> Response:
    """The catalogue the UI lets you pick from (public fields only — never the floor)."""
    return JSONResponse({
        "policy": POLICY_DESC,
        "items": [
            {"id": i, "name": it.name, "condition": it.condition,
             "description": it.description, "list_price": it.list_price,
             "bucket": situation_key(it)}
            for i, it in enumerate(ITEMS)
        ],
    })


async def _health(request: Request) -> Response:
    return JSONResponse({"ok": True, "model_configured": bool(settings.minimax_api_key),
                         "policy": POLICY_DESC, "n_items": len(ITEMS)})


from gambit.logfire_read import run_detail, runs_list, runs_stream  # noqa: E402  (read REAL runs from Logfire)

app = Starlette(
    routes=[
        Route("/", _agent_endpoint, methods=["POST"]),
        Route("/items", _items, methods=["GET"]),
        Route("/health", _health, methods=["GET"]),
        Route("/runs", runs_list, methods=["GET"]),
        Route("/runs/stream", runs_stream, methods=["GET"]),
        Route("/run", run_detail, methods=["GET"]),
    ],
    middleware=[
        Middleware(CORSMiddleware, allow_origins=["http://localhost:3000"],
                   allow_methods=["*"], allow_headers=["*"]),
    ],
)
