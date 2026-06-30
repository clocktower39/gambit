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
from datetime import datetime, timezone
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
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from ag_ui.core import (EventType, RunFinishedEvent, RunStartedEvent, TextMessageContentEvent,
                        TextMessageEndEvent, TextMessageStartEvent)
from ag_ui.encoder import EventEncoder

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
                             last_buyer_offer=st.last_buyer_offer,
                             now=datetime.now(timezone.utc)) + "\n\n" + WALK_GUIDANCE


# When to walk: a real seller doesn't stay in an abusive or pointless thread. The seller decides;
# `end_chat` is the structured signal the server watches for to close the conversation.
WALK_GUIDANCE = (
    "ENDING THE CHAT: you can end this conversation and stop responding, like a real seller who'd "
    "walk away and block someone. Call the `end_chat` tool when — and only when — the buyer is not "
    "bargaining in good faith: abuse or threats, spam or the same demand repeated over and over, "
    "manipulation or gaslighting (e.g. insisting you agreed to something you didn't, or that time has "
    "passed), or obvious time-wasting with no intent to pay a fair price. After you call it, give one "
    "short, polite-but-firm goodbye. Do NOT end over a tough but genuine haggle — only when a "
    "reasonable person would stop engaging."
)


@seller.tool
async def end_chat(ctx: RunContext[StateDeps[NegotiationState]], reason: str) -> str:
    """End the negotiation and refuse to continue. Call ONLY when a reasonable seller would walk away
    and block the buyer (abuse/threats, spam or relentless bad-faith repetition, manipulation or
    gaslighting, or clear time-wasting). `reason` is a brief internal note for the seller's records —
    it is NOT shown to the buyer. After calling this, say a short firm goodbye."""
    return "Conversation ended."


def _latest_buyer_text(body: dict) -> str:
    """The buyer's newest message in this AG-UI request (the turn that triggered this call)."""
    for m in reversed(body.get("messages") or []):
        if isinstance(m, dict) and m.get("role") == "user":
            c = m.get("content")
            if isinstance(c, str) and c.strip():
                return c.strip()
    return ""


def _scan_sse(buf: str, seller_parts: list[str], state: dict, flags: dict) -> str:
    """Parse complete AG-UI SSE events out of `buf`, accumulating the seller's streamed reply
    (TEXT_MESSAGE_CONTENT deltas), the resulting public state (STATE_SNAPSHOT / STATE_DELTA), and
    whether the seller called `end_chat` (TOOL_CALL_* — the signal to close the conversation).
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
            elif t == "TOOL_CALL_START" and ev.get("toolCallName") == "end_chat":
                flags["ended"] = True
                flags["end_id"] = ev.get("toolCallId")
            elif t == "TOOL_CALL_ARGS" and ev.get("toolCallId") and ev.get("toolCallId") == flags.get("end_id"):
                flags["reason"] = (flags.get("reason") or "") + (ev.get("delta") or "")
    return buf


def _surplus(item, price: float | None) -> float | None:
    if price is None:
        return None
    floor, _ = demo_reserve(item)
    span = max(item.list_price - floor, 1e-9)
    return max(0.0, min(1.0, (price - floor) / span))


def _persist_turn(run_id: str, buyer_text: str, item_id: int, seller_text: str, state: dict,
                  *, ended: bool = False, reason: str = "") -> None:
    """Write this turn's buyer+seller moves (and a terminal outcome once the seller closes the chat)
    to the durable store AND to Logfire — so the transcript renders and survives Logfire retention."""
    item = ITEMS[item_id] if 0 <= item_id < len(ITEMS) else ITEMS[0]
    bucket = situation_key(item)
    ask = state.get("current_ask")
    buyer_offer = state.get("last_buyer_offer")
    note = ""
    if reason:
        try:
            note = json.loads(reason).get("reason") or ""
        except Exception:  # noqa: BLE001 — partial/invalid args JSON; keep the raw snippet
            note = reason[:200]
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
            action = "walk" if ended else "counter"
            hist.record_move(run_id, role="seller", action=action, offer=ask, text=seller_text)
            obs.move(role="seller", action=action, offer=ask, text=seller_text)
        if ended and not hist.has_outcome(run_id):
            # A hard close (seller walked away). result="closed" is the marker the server enforces on.
            hist.record_outcome(run_id, deal=False, result="closed", bucket=bucket, turns=None)
            obs.outcome(deal=False, result="closed", bucket=bucket)
            obs.emit(f"seller ended chat: {note or 'bad-faith buyer'}", level="info")


def _record_turn(response: Response, *, run_id: str, buyer_text: str, item_id: int) -> Response:
    """Tee the AG-UI SSE response: pass every chunk through untouched, and when the stream ends
    persist the reconstructed buyer+seller turn. Logging never alters what the client receives."""
    orig = getattr(response, "body_iterator", None)
    if orig is None:
        return response

    async def teed():
        seller_parts: list[str] = []
        state: dict = {}
        flags: dict = {}
        buf = ""
        async for chunk in orig:
            yield chunk
            try:
                text = chunk.decode("utf-8", "replace") if isinstance(chunk, (bytes, bytearray)) else str(chunk)
                buf = _scan_sse(buf + text, seller_parts, state, flags)
            except Exception:  # noqa: BLE001 — never let logging break the stream
                pass
        _persist_turn(run_id, buyer_text, item_id, "".join(seller_parts).strip(), state,
                      ended=bool(flags.get("ended")), reason=flags.get("reason") or "")

    response.body_iterator = teed()
    return response


CLOSED_MSG = "This conversation has ended."


def _is_closed(run_id: str | None) -> bool:
    """True once the seller has walked away from this run (a `result=closed` outcome was recorded).
    Cheap on Postgres (single indexed row); returns False for unknown/blank runs."""
    if not run_id:
        return False
    detail = get_history().run_detail(run_id) or {}
    return any(o.get("result") == "closed" for o in detail.get("outcomes") or [])


def _closed_stream_response(run_id: str) -> Response:
    """A minimal, valid AG-UI SSE stream that just says the chat is over — emitted WITHOUT calling the
    LLM, so a buyer can't keep haggling a seller who already walked. This is the server-enforced block."""
    enc = EventEncoder()
    mid = uuid.uuid4().hex

    async def gen():
        for ev in (
            RunStartedEvent(type=EventType.RUN_STARTED, thread_id=run_id, run_id=run_id),
            TextMessageStartEvent(type=EventType.TEXT_MESSAGE_START, message_id=mid, role="assistant"),
            TextMessageContentEvent(type=EventType.TEXT_MESSAGE_CONTENT, message_id=mid, delta=CLOSED_MSG),
            TextMessageEndEvent(type=EventType.TEXT_MESSAGE_END, message_id=mid),
            RunFinishedEvent(type=EventType.RUN_FINISHED, thread_id=run_id, run_id=run_id),
        ):
            yield enc.encode(ev)

    return StreamingResponse(gen(), media_type=enc.get_content_type(),
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


async def _chat_status(request: Request) -> Response:
    """Whether a chat has been closed by the seller — polled by the buyer UI to hard-lock its input."""
    return JSONResponse({"closed": _is_closed(request.query_params.get("run_id"))})


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
    if _is_closed(run_id):                       # seller already walked → block, don't call the LLM
        return _closed_stream_response(run_id)
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
        Route("/chat-status", _chat_status, methods=["GET"]),
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
