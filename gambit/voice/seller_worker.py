"""LiveKit voice seat for the /chat page — speak to the trained M3 seller.

The browser (the BUYER) joins a LiveKit room and talks; this worker is the SELLER. LiveKit owns the
audio plane; Gemini is the ears + mouth (STT + TTS, on the GEMINI_API_KEY); and the BRAIN is the same
trained MiniMax-M3 seller the typed chat faces — same persona, same learned `PolicyStore` knobs and
lessons, same demo reserve (all from `gambit.negotiation.seller_brain`). So you genuinely haggle the
self-taught negotiator out loud, not a generic voice bot.

    pipeline:  mic ─▶ LiveKit ─▶ Gemini STT ─▶ MiniMax-M3 seller (learned policy) ─▶ Gemini TTS ─▶ LiveKit ─▶ speaker

Run it (it auto-dispatches to any room the token route creates):

    uv run python -m gambit.voice.seller_worker dev      # dev: hot-reload, connects to LIVEKIT_URL

Config-gated: needs LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET + GEMINI_API_KEY +
MINIMAX_API_KEY (all already in .env). The browser side mints a join token via the Next.js route
`/api/livekit-token`; this worker joins the same room.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Populate os.environ from .env BEFORE the LiveKit CLI reads LIVEKIT_* (pydantic-settings only feeds
# `settings`, not the process env the agents CLI inspects).
load_dotenv()

from anthropic import AsyncAnthropic
from google import genai
from google.genai import types as genai_types
from livekit import agents, rtc
from livekit.agents import Agent, AgentSession, JobContext, WorkerOptions, cli, llm, stt
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, NOT_GIVEN, NotGivenOr
from livekit.plugins import google, silero

from gambit import observability as obs
from gambit.history import get_history
from gambit.negotiation import PolicyStore
from gambit.negotiation.seller_brain import (
    SELLER_SYSTEM_PROMPT,
    VOICE_GREETING,
    VOICE_STYLE,
    catalogue_context,
)
from gambit.settings import settings

logger = logging.getLogger("gambit.voice")
obs.configure()                                       # same Logfire seam as the typed seat

CHECKPOINT = Path("checkpoints/latest.json")          # same checkpoint the typed seat loads
STT_MODEL = "gemini-2.5-flash"                         # audio understanding (verbatim transcription)


def _load_policy() -> tuple[PolicyStore, str]:
    """The seller the human faces by voice: the latest trained checkpoint, else the cold-start prior."""
    if CHECKPOINT.exists():
        return PolicyStore.model_validate_json(CHECKPOINT.read_text()), f"checkpoint {CHECKPOINT}"
    return PolicyStore(), "seeded cold-start prior (no checkpoint yet)"


# --- Ears: Gemini STT (Gemini API key, no Google Cloud service account needed) ------------------
class GeminiSTT(stt.STT):
    """Non-streaming STT: silero VAD (via StreamAdapter) cuts the buyer's speech into utterances, and
    each utterance is transcribed verbatim by Gemini. Uses only GEMINI_API_KEY — unlike the plugin's
    `google.STT`, which is Google *Cloud* Speech and needs a service account we don't have."""

    def __init__(self, *, api_key: str, model: str = STT_MODEL) -> None:
        super().__init__(capabilities=stt.STTCapabilities(streaming=False, interim_results=False))
        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def _recognize_impl(
        self,
        buffer: rtc.AudioFrame | list[rtc.AudioFrame],
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options=DEFAULT_API_CONNECT_OPTIONS,
    ) -> stt.SpeechEvent:
        wav = rtc.combine_audio_frames(buffer).to_wav_bytes()
        text = ""
        try:
            resp = await self._client.aio.models.generate_content(
                model=self._model,
                contents=[
                    genai_types.Part.from_bytes(data=wav, mime_type="audio/wav"),
                    "Transcribe the buyer's speech to text, verbatim. Return only the words they said "
                    "— no quotes, labels, or commentary. If there is no clear speech, return nothing.",
                ],
                config=genai_types.GenerateContentConfig(temperature=0.0),
            )
            text = (resp.text or "").strip()
        except Exception as e:  # noqa: BLE001 — a failed transcription must not kill the call
            logger.warning("Gemini STT failed: %s", e)
        lang = language if isinstance(language, str) else "en-US"
        return stt.SpeechEvent(
            type=stt.SpeechEventType.FINAL_TRANSCRIPT,
            alternatives=[stt.SpeechData(language=lang, text=text)],
        )


# --- Brain: the trained MiniMax-M3 seller (same model + learned policy as the typed seat) -------
def _to_anthropic_messages(chat_ctx: llm.ChatContext) -> list[dict]:
    """LiveKit's running `ChatContext` → Anthropic message list. The seller's system prompt + secret
    catalogue are supplied separately (server-side), so here we keep only the user/assistant turns,
    drop any leading assistant turn (Anthropic requires the first message to be 'user'), and merge
    consecutive same-role turns (Anthropic rejects two in a row)."""
    raw: list[tuple[str, str]] = []
    for item in chat_ctx.items:
        if getattr(item, "type", None) != "message" or item.role not in ("user", "assistant"):
            continue
        text = (item.text_content or "").strip()
        if text:
            raw.append((item.role, text))
    while raw and raw[0][0] == "assistant":
        raw.pop(0)
    merged: list[tuple[str, str]] = []
    for role, text in raw:
        if merged and merged[-1][0] == role:
            merged[-1] = (role, merged[-1][1] + "\n" + text)
        else:
            merged.append((role, text))
    return [{"role": r, "content": t} for r, t in merged]


class MiniMaxSellerLLM(llm.LLM):
    """The trained seller as a LiveKit LLM. Same MiniMax-M3 model + same learned-policy instructions as
    the typed chat (`gambit.agui`), so the voice and text seats are the same negotiator."""

    def __init__(self, *, policy: PolicyStore, run_id: str = "") -> None:
        super().__init__()
        self._policy = policy
        self._run_id = run_id          # the LiveKit room — groups this call's transcript in history
        self._client = AsyncAnthropic(api_key=settings.minimax_api_key, base_url=settings.minimax_base_url)

    def system_text(self) -> str:
        # Persona + voice-style + the secret catalogue (floors/targets/learned knobs) — all server-side.
        # `now` gives the seller a ground-truth clock so a caller can't haggle by claiming time passed.
        return "\n\n".join((SELLER_SYSTEM_PROMPT, VOICE_STYLE,
                            catalogue_context(self._policy, now=datetime.now(timezone.utc))))

    def chat(self, *, chat_ctx, tools=None, conn_options=DEFAULT_API_CONNECT_OPTIONS,
             parallel_tool_calls=NOT_GIVEN, tool_choice=NOT_GIVEN, extra_kwargs=NOT_GIVEN):
        return _SellerStream(self, chat_ctx=chat_ctx, tools=tools or [], conn_options=conn_options)


class _SellerStream(llm.LLMStream):
    async def _run(self) -> None:
        messages = _to_anthropic_messages(self._chat_ctx)
        if not messages:
            return  # nothing the buyer said yet — produce no reply
        assert isinstance(self._llm, MiniMaxSellerLLM)
        text, chunk_id = "", "seller"
        try:
            resp = await self._llm._client.messages.create(
                model=settings.minimax_model,
                max_tokens=400,
                system=self._llm.system_text(),
                messages=messages,
            )
            chunk_id = getattr(resp, "id", None) or "seller"
            text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
        except Exception as e:  # noqa: BLE001 — keep the call alive; ask the buyer to repeat
            logger.warning("MiniMax seller call failed: %s", e)
            text = "Sorry, I didn't catch that — could you say that again?"
        if text:
            self._event_ch.send_nowait(
                llm.ChatChunk(id=chunk_id, delta=llm.ChoiceDelta(role="assistant", content=text))
            )
        self._log_turn(messages, text)

    def _log_turn(self, messages: list[dict], seller_text: str) -> None:
        """Persist this voice exchange (buyer utterance + seller reply) move-by-move, so the voice
        seat shows transcripts in history just like the typed seat. Best-effort; never breaks a call."""
        run_id = getattr(self._llm, "_run_id", "") or ""
        if not run_id:
            return
        buyer_text = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        try:
            hist = get_history()
            hist.ensure_job(run_id, source="human", title="voice: phone haggle", checkpoint="latest")
            with obs.job("human-vs-agent", source="human", run_id=run_id, checkpoint="latest",
                         title="voice: phone haggle"):
                if buyer_text:
                    hist.record_move(run_id, role="buyer", action="counter", text=buyer_text)
                    obs.move(role="buyer", action="counter", text=buyer_text)
                if seller_text:
                    hist.record_move(run_id, role="seller", action="counter", text=seller_text)
                    obs.move(role="seller", action="counter", text=seller_text)
        except Exception as e:  # noqa: BLE001
            logger.warning("voice transcript logging failed: %s", e)


def prewarm(proc: agents.JobProcess) -> None:
    """Load the silero VAD model once per worker process (reused across rooms)."""
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext) -> None:
    policy, desc = _load_policy()
    logger.info("voice seller joining room %s — brain: MiniMax-M3, policy: %s", ctx.room.name, desc)

    vad = ctx.proc.userdata.get("vad") or silero.VAD.load()
    session = AgentSession(
        stt=stt.StreamAdapter(stt=GeminiSTT(api_key=settings.gemini_api_key), vad=vad),
        llm=MiniMaxSellerLLM(policy=policy, run_id=ctx.room.name),
        tts=google.beta.GeminiTTS(api_key=settings.gemini_api_key),   # voice "Kore" by default
        vad=vad,
    )
    await ctx.connect()
    await session.start(agent=Agent(instructions=SELLER_SYSTEM_PROMPT), room=ctx.room)
    # Spoken opener — no model call, so there's instant audio the moment the buyer connects.
    await session.say(VOICE_GREETING, allow_interruptions=True)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
