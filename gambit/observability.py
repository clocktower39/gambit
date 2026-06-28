"""One Logfire seam for the whole project — configure once, tag every job natively.

Why this exists: tracing was duplicated across ~6 scripts with an inconsistent `kind=`/`source=`
vocabulary, and the self-play / RL jobs emitted nothing. This module centralizes it so the trace
tree separates **human-vs-agent** play from **agent RL** jobs at one click, and so iterative jobs
are comparable across **generations** and **checkpoints**.

The keystone is Logfire **baggage**: `configure(add_baggage_to_attributes=True)` (the default) copies
whatever `set_baggage(...)` holds onto *every* span started while it's active — including the
pydantic-ai model-call spans and httpx spans. So `job()` sets the run grouping once and all
descendants inherit `gambit.run_id / job_type / source / generation / checkpoint` with no threading.

Taxonomy (all keys namespaced `gambit.`; bold ones also ride baggage):
  **job_type**  human-vs-agent · self-play · offline-rl · reflection · harvest · overview · spike
  **source**    human · agent            (provenance only — never a matchup string)
  **run_id**    uuid hex per invocation  (groups one job's whole tree)
  **checkpoint**/**generation**          (the iterative-comparison pivots)
  bucket · seat · split(train|gate|locked) · seed · result   (per-episode slices)

Everything is **no-op-safe**: if Logfire isn't installed or `configure()` hasn't run, the context
managers yield None, metrics/emit do nothing, and `span()` returns a nullcontext — so engine and
scripts can call freely without guarding, and offline/no-token runs never break.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager, nullcontext
from typing import Iterator, Literal

from gambit.settings import settings

try:  # Logfire is optional at import time; the whole module degrades to no-ops without it.
    import logfire
    _HAVE = True
except ImportError:  # pragma: no cover
    logfire = None  # type: ignore
    _HAVE = False

JobType = Literal["human-vs-agent", "self-play", "offline-rl", "reflection", "harvest", "overview", "spike"]
Source = Literal["human", "agent"]

_configured = False
_sending = False


def configure(*, service: str = "gambit", console: bool = False,
              send: bool | None = None, environment: str | None = None) -> bool:
    """Configure Logfire once for this process. Returns True iff actually shipping to the cloud.

    `send=None` ships when a LOGFIRE_TOKEN is set. scrubbing is OFF (our prompts say "secret floor"/
    "budget" — negotiation terms, not credentials) and inspect_arguments is OFF (we pass explicit
    kwargs; f-string introspection fails under the scripts' sys.path shim). Idempotent."""
    global _configured, _sending
    if not _HAVE:
        return False
    if _configured:
        return _sending
    send = bool(settings.logfire_token) if send is None else send
    console_opt = logfire.ConsoleOptions(span_style="indented") if console else False
    logfire.configure(
        service_name=service,
        token=settings.logfire_token or None,
        send_to_logfire=send,
        environment=environment,
        console=console_opt,
        scrubbing=False,
        inspect_arguments=False,
    )
    if send or console:
        logfire.instrument_pydantic_ai()      # model-call spans inherit the job baggage automatically
    _configured, _sending = True, bool(send)
    return _sending


def is_on() -> bool:
    return _HAVE and _configured


def _attrs(prefix_all: bool = True, **kv) -> dict:
    """Namespace non-None values under `gambit.` for consistent filtering in the picker."""
    return {(f"gambit.{k}" if prefix_all else k): v for k, v in kv.items() if v is not None}


def _baggage(**kv) -> dict:
    """Baggage values must be strings; only the run-grouping keys ride along to descendants."""
    return {f"gambit.{k}": str(v) for k, v in kv.items() if v is not None}


@contextmanager
def job(job_type: JobType, *, source: Source, run_id: str | None = None,
        checkpoint: str | None = None, generation: int | None = None,
        bucket: str | None = None, title: str | None = None, **attrs) -> Iterator[object | None]:
    """The root span for one invocation (`gambit.kind=job`). Tags [job_type, source] and sets baggage
    so every child span (turns, model calls, http) inherits run_id/job_type/source/checkpoint/generation.
    `title` is the human-readable run name the UI shows (e.g. 'iPhone — you vs trained seller')."""
    if not is_on():
        yield None
        return
    run_id = run_id or uuid.uuid4().hex
    span_attrs = _attrs(kind="job", job_type=job_type, source=source, run_id=run_id,
                        checkpoint=checkpoint, generation=generation, bucket=bucket, title=title, **attrs)
    bag = _baggage(job_type=job_type, source=source, run_id=run_id,
                   checkpoint=checkpoint, generation=generation)
    with logfire.set_baggage(**bag), \
         logfire.span(title or f"job: {job_type}", _tags=[job_type, source], **span_attrs) as span:
        yield span


@contextmanager
def generation(gen: int, *, checkpoint: str | None = None, **attrs) -> Iterator[object | None]:
    """A per-generation span inside a job — the comparable unit for gen-over-gen pivots."""
    if not is_on():
        yield None
        return
    span_attrs = _attrs(kind="generation", generation=gen, checkpoint=checkpoint, **attrs)
    with logfire.set_baggage(**_baggage(generation=gen, checkpoint=checkpoint)), \
         logfire.span(f"generation {gen}", **span_attrs) as span:
        yield span


@contextmanager
def episode(*, bucket: str, seat: str | None = None, split: str | None = None,
            seed: int | None = None, **attrs) -> Iterator[object | None]:
    """One negotiation episode — carries the per-situation / per-split slice attributes."""
    if not is_on():
        yield None
        return
    span_attrs = _attrs(kind="episode", bucket=bucket, seat=seat, split=split, seed=seed, **attrs)
    with logfire.span(f"episode {bucket}", **span_attrs) as span:
        yield span


def _bag(key: str) -> str | None:
    """Read a `gambit.<key>` value out of the active baggage (set by job())."""
    if not is_on():
        return None
    try:
        return (logfire.get_baggage() or {}).get(f"gambit.{key}")
    except Exception:  # noqa: BLE001
        return None


def move(*, role: str, action: str, offer: float | None = None, text: str = "",
         reasoning: str | None = None) -> None:
    """A structured negotiation move (`gambit.kind=move`) — the transcript, queryable by attribute
    instead of regex-parsed from a message. High-volume; use on human-facing seats, not RL inner loops."""
    if not is_on():
        return
    logfire.info("move", **_attrs(kind="move", role=role, action=action, offer=offer,
                                  text=text, reasoning=reasoning))


def outcome(*, deal: bool, result: str | None = None, price: float | None = None,
            reward: float | None = None, surplus: float | None = None, skill: float | None = None,
            viol: int = 0, turns: int | None = None, bucket: str | None = None) -> None:
    """The terminal outcome of one episode (`gambit.kind=outcome`) AND the metric records in one call.
    job_type/source come from the active job's baggage, so callers don't repeat them."""
    if not is_on():
        return
    logfire.info("outcome", **_attrs(kind="outcome", deal=deal, result=result, price=price, reward=reward,
                                     surplus=surplus, skill=skill, viol=viol, turns=turns, bucket=bucket))
    jt, src = _bag("job_type"), _bag("source")
    if jt and src:
        if reward is not None:
            record_reward(reward, job_type=jt, source=src, bucket=bucket)
        if deal and surplus is not None:
            record_surplus(surplus, job_type=jt, source=src, bucket=bucket)
        if deal and skill is not None:
            record_skill(skill, job_type=jt, source=src, bucket=bucket)
        record_episode(deal=bool(deal), viol=int(viol or 0), job_type=jt, source=src, bucket=bucket)


def reflection(*, bucket: str, seller_lesson: str | None = None, buyer_lesson: str | None = None,
               surplus: float | None = None, viol: int = 0) -> None:
    """A Gemini-proposed lesson event (`gambit.kind=reflection`)."""
    if not is_on():
        return
    logfire.info("reflection", **_attrs(kind="reflection", bucket=bucket, seller_lesson=seller_lesson,
                                        buyer_lesson=buyer_lesson, surplus=surplus, viol=viol))


def emit(msg: str, *, level: Literal["debug", "info", "warn", "error"] = "info",
         tags: list[str] | None = None, kind: str | None = None, **attrs) -> None:
    """The single structured-log helper. No-op when unconfigured. Job baggage is inherited, so the
    event already carries job_type/source/run_id; `attrs` are the raw event payload (so `{...}`
    placeholders in `msg` resolve). `kind` stamps `gambit.kind` so the reader can categorize it."""
    if not is_on():
        return
    payload = dict(attrs)
    if kind is not None:
        payload["gambit.kind"] = kind
    getattr(logfire, level)(msg, _tags=tags, **payload)


def span(msg: str, **attrs):
    """Thin passthrough to logfire.span (namespacing attrs); a nullcontext when unconfigured."""
    if not is_on():
        return nullcontext()
    return logfire.span(msg, **_attrs(**attrs))


def current_trace_id() -> str | None:
    """The 32-hex trace id of the active span, for a 'walk this run' deep link — or None."""
    if not is_on():
        return None
    try:
        from opentelemetry import trace
        ctx = trace.get_current_span().get_span_context()
        return format(ctx.trace_id, "032x") if ctx and ctx.trace_id else None
    except Exception:  # noqa: BLE001 — tracing must never break a job
        return None


# --- metrics: first-class reward / viol / latency curves (low-cardinality dims only) -------
# run_id / seed / generation are span attributes, NEVER metric dimensions (cardinality blowup).

_metrics: dict[str, object] = {}


def _counter(name: str):
    if not is_on():
        return None
    if name not in _metrics:
        _metrics[name] = logfire.metric_counter(name)
    return _metrics[name]


def _histogram(name: str, unit: str = ""):
    if not is_on():
        return None
    if name not in _metrics:
        _metrics[name] = logfire.metric_histogram(name, unit=unit)
    return _metrics[name]


def _gauge(name: str):
    if not is_on():
        return None
    if name not in _metrics:
        _metrics[name] = logfire.metric_gauge(name)
    return _metrics[name]


def _dims(job_type: str, source: str, bucket: str | None) -> dict:
    d = {"job_type": job_type, "source": source}
    if bucket is not None:
        d["bucket"] = bucket
    return d


def record_reward(value: float, *, job_type: str, source: str, bucket: str | None = None) -> None:
    if (h := _histogram("gambit.reward")):
        h.record(value, attributes=_dims(job_type, source, bucket))


def record_surplus(value: float, *, job_type: str, source: str, bucket: str | None = None) -> None:
    if (h := _histogram("gambit.surplus")):
        h.record(value, attributes=_dims(job_type, source, bucket))


def record_skill(value: float, *, job_type: str, source: str, bucket: str | None = None) -> None:
    if (h := _histogram("gambit.skill")):
        h.record(value, attributes=_dims(job_type, source, bucket))


def record_latency(seconds: float, *, job_type: str, source: str, bucket: str | None = None) -> None:
    if (h := _histogram("gambit.episode_latency", unit="s")):
        h.record(seconds, attributes=_dims(job_type, source, bucket))


def record_episode(*, deal: bool, viol: int, job_type: str, source: str, bucket: str | None = None) -> None:
    """One call bundles episodes + deals + violations so deal-rate and the integrity counter can't drift."""
    dims = _dims(job_type, source, bucket)
    if (c := _counter("gambit.episodes")):
        c.add(1, attributes=dims)
    if deal and (c := _counter("gambit.deals")):
        c.add(1, attributes=dims)
    if viol and (c := _counter("gambit.violations")):
        c.add(viol, attributes=dims)


def record_gate_delta(delta: float, *, job_type: str = "offline-rl") -> None:
    if (g := _gauge("gambit.gate_delta")):
        g.set(delta, attributes={"job_type": job_type})


def record_promotion(*, job_type: str, generation: int) -> None:
    if (c := _counter("gambit.promotions")):
        c.add(1, attributes={"job_type": job_type})
