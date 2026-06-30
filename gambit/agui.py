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

import base64
import json
import uuid
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
from gambit.negotiation.seller_brain import SELLER_SYSTEM_PROMPT, catalogue_context, demo_reserve
from gambit.settings import settings
from gambit import observability as obs
from gambit.history import get_history

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


def _latest_buyer_text(body: dict) -> str:
    """The buyer's newest message in this AG-UI request (the turn that triggered this call)."""
    for m in reversed(body.get("messages") or []):
        if isinstance(m, dict) and m.get("role") == "user":
            c = m.get("content")
            if isinstance(c, str) and c.strip():
                return c.strip()
    return ""


def _scan_sse(buf: str, seller_parts: list[str], state: dict) -> str:
    """Parse complete AG-UI SSE events out of `buf`, accumulating the seller's streamed reply
    (TEXT_MESSAGE_CONTENT deltas) and the resulting public state (STATE_SNAPSHOT / STATE_DELTA).
    Returns the unconsumed tail (a partial event still being written)."""
    while "\n\n" in buf:
        block, buf = buf.split("\n\n", 1)
        for line in block.splitlines():
            if not line.startswith("data:"):
                continue
            try:
                ev = json.loads(line[5:].strip())
            except json.JSONDecodeError:
                continue
            t = ev.get("type")
            if t == "TEXT_MESSAGE_CONTENT" and ev.get("delta"):
                seller_parts.append(ev["delta"])
            elif t == "STATE_SNAPSHOT" and isinstance(ev.get("snapshot"), dict):
                state.update(ev["snapshot"])
            elif t == "STATE_DELTA":
                for op in ev.get("delta") or []:
                    if op.get("op") in ("add", "replace") and isinstance(op.get("path"), str):
                        state[op["path"].strip("/").split("/")[0]] = op.get("value")
    return buf


def _surplus(item, price: float | None) -> float | None:
    if price is None:
        return None
    floor, _ = demo_reserve(item)
    span = max(item.list_price - floor, 1e-9)
    return max(0.0, min(1.0, (price - floor) / span))


def _persist_turn(run_id: str, buyer_text: str, item_id: int, seller_text: str, state: dict) -> None:
    """Write this turn's buyer+seller moves (and the outcome, once closed) to the durable local
    store AND to Logfire — so the transcript renders and survives Logfire retention/rate limits."""
    item = ITEMS[item_id] if 0 <= item_id < len(ITEMS) else ITEMS[0]
    bucket = situation_key(item)
    status = str(state.get("status") or "open")
    price = state.get("deal_price")
    ask = state.get("current_ask")
    buyer_offer = state.get("last_buyer_offer")
    hist = get_history()
    hist.ensure_job(run_id, source="human", title=f"chat: {item.name}", checkpoint="latest")
    # Re-open the job span at record time so obs.move/outcome carry this run_id in Logfire (the
    # adapter streams the agent AFTER dispatch_request returns, so the outer span is already closed).
    with obs.job("human-vs-agent", source="human", run_id=run_id, checkpoint="latest",
                 title=f"chat: {item.name}", bucket=bucket):
        if buyer_text:
            hist.record_move(run_id, role="buyer", action="counter", offer=buyer_offer, text=buyer_text)
            obs.move(role="buyer", action="counter", offer=buyer_offer, text=buyer_text)
        if seller_text:
            action = "accept" if status == "deal" else "walk" if status == "walked" else "counter"
            hist.record_move(run_id, role="seller", action=action, offer=ask, text=seller_text)
            obs.move(role="seller", action=action, offer=ask, text=seller_text)
        if status in ("deal", "walked") and not hist.has_outcome(run_id):
            deal = status == "deal"
            surplus = _surplus(item, price) if deal else None
            hist.record_outcome(run_id, deal=deal, price=price, surplus=surplus, bucket=bucket,
                                result=f"{'deal' if deal else 'no-deal'}")
            obs.outcome(deal=deal, price=price, reward=surplus, surplus=surplus, bucket=bucket)


def _record_turn(response: Response, *, run_id: str, buyer_text: str, item_id: int) -> Response:
    """Tee the AG-UI SSE response: pass every chunk through untouched, and when the stream ends
    persist the reconstructed buyer+seller turn. Logging never alters what the client receives."""
    orig = getattr(response, "body_iterator", None)
    if orig is None:
        return response

    async def teed():
        seller_parts: list[str] = []
        state: dict = {}
        buf = ""
        async for chunk in orig:
            yield chunk
            try:
                text = chunk.decode("utf-8", "replace") if isinstance(chunk, (bytes, bytearray)) else str(chunk)
                buf = _scan_sse(buf + text, seller_parts, state)
            except Exception:  # noqa: BLE001 — never let logging break the stream
                pass
        _persist_turn(run_id, buyer_text, item_id, "".join(seller_parts).strip(), state)

    response.body_iterator = teed()
    return response


async def _agent_endpoint(request: Request) -> Response:
    # Fresh deps per request; AGUIAdapter loads the client's `state` into deps.state.
    # We capture the buyer's message + item up front, then tee the streamed reply so each turn is
    # logged as structured buyer/seller `move`s (the transcript) to a durable local store + Logfire.
    try:
        body = await request.json()      # Starlette caches the body; AGUIAdapter re-reads it below
    except Exception:  # noqa: BLE001
        body = {}
    run_id = str(body.get("threadId") or body.get("runId") or "") or None
    buyer_text = _latest_buyer_text(body)
    try:
        item_id = int((body.get("state") or {}).get("item_id") or 0)
    except (TypeError, ValueError):
        item_id = 0
    response = await AGUIAdapter.dispatch_request(request, agent=seller,
                                                  deps=replace(StateDeps(NegotiationState())))
    if run_id:
        response = _record_turn(response, run_id=run_id, buyer_text=buyer_text, item_id=item_id)
    return response


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


def _check_basic_auth(request: Request) -> bool:
    """HTTP Basic Auth against ADMIN_USERS (.env). Constant-time password compare; no creds → no access."""
    header = request.headers.get("authorization", "")
    if not header.startswith("Basic "):
        return False
    try:
        user, _, pw = base64.b64decode(header[6:]).decode("utf-8").partition(":")
    except Exception:  # noqa: BLE001 — malformed header → unauthorized, not 500
        return False
    return settings.check_admin(user, pw)


def _unauthorized() -> Response:
    return JSONResponse({"error": "unauthorized"}, status_code=401,
                        headers={"WWW-Authenticate": 'Basic realm="gambit-admin"'})


async def _admin_floors(request: Request) -> Response:
    """ADMIN ONLY: the secret reserve the live seller defends — demo floor/target per item, plus the
    wider sim floor and difficulty bucket. The floor never leaves the server on any public route; this
    one is gated by Basic Auth (ADMIN_USERS in .env)."""
    if not settings.admin_available():
        return JSONResponse({"error": "admin not configured", "detail": "set ADMIN_USERS in .env"},
                            status_code=503)
    if not _check_basic_auth(request):
        return _unauthorized()
    items = []
    for i, it in enumerate(ITEMS):
        floor, target = demo_reserve(it)
        floor, target = round(floor), round(target)
        items.append({
            "id": i, "name": it.name, "condition": it.condition, "description": it.description,
            "list_price": it.list_price, "target": target, "floor": floor,
            "sim_floor": it.floor_price, "sim_target": it.target_price,
            "bucket": situation_key(it),
            "margin_pct": round((it.list_price - floor) / it.list_price * 100),
        })
    return JSONResponse({"policy": POLICY_DESC, "items": items})


async def _health(request: Request) -> Response:
    return JSONResponse({"ok": True, "model_configured": bool(settings.minimax_api_key),
                         "policy": POLICY_DESC, "n_items": len(ITEMS),
                         "voice_available": settings.voice_available()})


async def _voice_token(request: Request) -> Response:
    """Mint a LiveKit join token for the browser's voice seat. The secret (LIVEKIT_API_SECRET) signs
    the JWT here and never leaves the server; the buyer joins a fresh room and the running voice worker
    (gambit.voice.seller_worker) auto-dispatches into it as the trained M3 seller. 503 (not 500) when
    voice isn't configured/installed, so the UI can simply hide the button."""
    if not settings.voice_available():
        return JSONResponse({"error": "voice not configured",
                             "detail": "set LIVEKIT_URL/API_KEY/API_SECRET + GEMINI_API_KEY"}, status_code=503)
    try:
        from livekit import api as lk_api      # lazy: only the voice feature-layer needs livekit installed
    except ImportError:
        return JSONResponse({"error": "voice deps not installed",
                             "detail": "uv sync --group feature-layer"}, status_code=503)
    room = f"gambit-voice-{uuid.uuid4().hex[:12]}"
    identity = f"buyer-{uuid.uuid4().hex[:8]}"
    token = (lk_api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
             .with_identity(identity).with_name("Buyer")
             .with_grants(lk_api.VideoGrants(room_join=True, room=room,
                                             can_publish=True, can_subscribe=True))
             .to_jwt())
    return JSONResponse({"serverUrl": settings.livekit_url, "token": token,
                         "room": room, "identity": identity})


from gambit.logfire_read import run_detail, runs_list, runs_stream  # noqa: E402  (Logfire — history browsing)
from gambit.watch import watch_start, watch_stream  # noqa: E402  (local JSONL bus — the LIVE climb view)

app = Starlette(
    routes=[
        Route("/", _agent_endpoint, methods=["POST"]),
        Route("/items", _items, methods=["GET"]),
        Route("/voice-token", _voice_token, methods=["GET", "POST"]),
        Route("/health", _health, methods=["GET"]),
        # ADMIN: secret reserve prices (Basic Auth, ADMIN_USERS in .env)
        Route("/admin/floors", _admin_floors, methods=["GET"]),
        # LIVE runs view: the fast, rate-limit-free JSONL bus (curve + spotlight + held-out transfer)
        Route("/watch/stream", watch_stream, methods=["GET"]),
        Route("/watch/start", watch_start, methods=["POST"]),
        # HISTORY browsing: Logfire read API (behind the 7s rate-gate, slow poll)
        Route("/runs", runs_list, methods=["GET"]),
        Route("/runs/stream", runs_stream, methods=["GET"]),
        Route("/run", run_detail, methods=["GET"]),
    ],
    middleware=[
        Middleware(CORSMiddleware, allow_origins=["http://localhost:3000"],
                   allow_methods=["*"], allow_headers=["*"]),
    ],
)
