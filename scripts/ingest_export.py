"""Ingest a Logfire dashboard export (CSV or JSON) into the durable history store — fully offline.

Once you have project access you can run the export query in Logfire's **Explore** view and download
the result, sidestepping the read-API rate limit entirely. This script turns that one file into the
complete local store: it does the same work as `backfill_history.py` + `recover_transcripts.py`
combined (run summaries + curves, Tier-A CLI transcripts, Tier-B browser transcripts), with zero
network calls. Then migrate to Postgres with `scripts/migrate_to_postgres.py`.

    uv run python scripts/ingest_export.py path/to/export.csv      # or .json

The export query is printed by `--show-query` (paste it into Explore, download CSV or JSON).
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make `gambit` importable

from gambit import history, logfire_read as lr  # noqa: E402
from scripts.recover_transcripts import _parse_input_messages, _role_from_span, _to_seconds  # noqa: E402

_TURN_SPANS = {"seller turn {round}", "buyer turn {round} (human)", "seller opening"}
_SKIP_RUN_IDS = {"t1", "thread-abc"}          # local smoke-test artifacts, never real conversations
_MAP_WINDOW_S = 90.0                           # a turn's model span vs its run's job span (same request)
# The browser seat's SELLER_SYSTEM_PROMPT — unique vs the league/verifier agents, so it isolates the
# real human chats from the thousands of self-improvement LLM calls that share the `chat`/`agent run` spans.
_BROWSER_MARK = "marketplace seller in a multi-turn"


def _export_query() -> str:
    # Filter the model spans to the BROWSER seat only — otherwise the league's thousands of LLM calls
    # flood the export (and blow Logfire's 10k-row cap). Browser chat spans carry SELLER_SYSTEM_PROMPT
    # in their input messages; browser agent-run spans carry the catalogue ("YOUR LISTINGS").
    extra = (", span_name, attributes->>'gen_ai.conversation.id' conv, "
             "attributes->>'final_result' final_result, attributes->>'gen_ai.input.messages' msgs")
    return (f"SELECT {lr._DETAIL_SELECT}{extra}\nFROM records\n"
            f"WHERE attributes->>'gambit.kind' IN ({lr._DETAIL_KINDS})\n"
            f"   OR span_name IN ('seller turn {{round}}','buyer turn {{round}} (human)','seller opening')\n"
            f"   OR (span_name = 'chat MiniMax-M3' AND attributes->>'gen_ai.input.messages' LIKE '%{_BROWSER_MARK}%')\n"
            f"   OR (span_name = 'agent run' AND attributes->>'gen_ai.system_instructions' LIKE '%YOUR LISTINGS%')\n"
            f"ORDER BY start_timestamp ASC")


def _read_rows(path: Path) -> list[dict]:
    text = path.read_text()
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        if isinstance(data, dict) and "columns" in data:                 # Logfire columnar shape
            cols = data["columns"]
            names = [c["name"] for c in cols]
            vals = [c["values"] for c in cols]
            n = len(vals[0]) if vals else 0
            return [{names[j]: vals[j][i] for j in range(len(names))} for i in range(n)]
        if isinstance(data, dict) and "rows" in data:
            return data["rows"]
        return data if isinstance(data, list) else []
    # CSV — large JSON cells (input.messages) survive as quoted fields
    csv.field_size_limit(1 << 24)
    return list(csv.DictReader(text.splitlines()))


def _build(rows: list[dict]) -> dict[str, dict]:
    renderable = {"job", "move", "outcome", "human_episode", "reflection", "league_gen",
                  "generation", "sample_episode", "promotion", "rejection", "integrity", "escalate"}

    # --- backfill: run summaries/curves/outcomes from the kind-bearing records ---
    by_run: dict[str, list[dict]] = {}
    for r in rows:
        rid = r.get("rid")
        if rid and rid not in _SKIP_RUN_IDS and r.get("kind") in renderable:
            by_run.setdefault(rid, []).append(r)
    details: dict[str, dict] = {}
    for rid, rrows in by_run.items():
        d = lr.reconstruct_detail(rid, rrows)
        job = next((r for r in rrows if r.get("kind") == "job"), {})
        d["category"] = job.get("jt") or (rrows[0].get("jt") if rrows else None) or "other"
        d["source"] = job.get("src") or (rrows[0].get("src") if rrows else None)
        d["checkpoint"] = job.get("ckpt")
        d["ts"] = job.get("ts") or min((r.get("ts") for r in rrows if r.get("ts")), default=None)
        details[rid] = d

    # --- Tier A: exact CLI transcripts by run_id ---
    tier_a: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("span_name") in _TURN_SPANS and r.get("rid") and r["rid"] not in _SKIP_RUN_IDS:
            tier_a.setdefault(r["rid"], []).append({
                "role": _role_from_span(r["span_name"]), "action": r.get("action") or "counter",
                "offer": lr._f(r.get("offer")), "text": (r.get("text") or "").strip(), "_ts": r.get("ts")})
    for moves in tier_a.values():
        moves.sort(key=lambda m: m.get("_ts") or "")
        for m in moves:
            m.pop("_ts", None)

    # --- Tier B: browser seat, grouped by the (session-stable) conversation.id ---
    # The browser model calls carry a `gen_ai.conversation.id` that is STABLE across a chat session
    # (it equals the AG-UI thread/run id), so it's the grouping key — no temporal mapping needed. We
    # keep ONLY the browser seat (its SELLER_SYSTEM_PROMPT is unique vs the league/verifier agents),
    # take each turn's buyer line from the chat span's input.messages and the seller line from that
    # turn's `agent run` final_result, then order every turn by time to rebuild the whole chat.
    browser_convs: set[str] = set()
    events: dict[str, list[tuple[str, str, str]]] = {}     # conv -> [(ts, role, text)]
    for r in rows:
        if r.get("span_name") == "chat MiniMax-M3" and r.get("conv") and r.get("msgs") \
                and _BROWSER_MARK in r["msgs"]:
            browser_convs.add(r["conv"])
            buyers = [m for m in _parse_input_messages(r["msgs"]) if m["role"] == "buyer"]
            if buyers:
                events.setdefault(r["conv"], []).append((r.get("ts") or "", "buyer", buyers[-1]["text"]))
    for r in rows:
        if r.get("span_name") == "agent run" and r.get("final_result") and r.get("conv") in browser_convs:
            events.setdefault(r["conv"], []).append((r.get("ts") or "", "seller", r["final_result"].strip()))

    def _moves(evs: list[tuple[str, str, str]]) -> list[dict]:
        out: list[dict] = []
        for _ts, role, text in sorted(evs):
            if text and not (out and out[-1]["role"] == role and out[-1]["text"] == text):
                out.append({"role": role, "action": "counter", "offer": None, "text": text})
        return out

    tier_b = {conv: _moves(evs) for conv, evs in events.items()}

    # --- merge: Tier A (exact) takes precedence; Tier B fills the browser runs ---
    a = b = bn = 0
    for rid, moves in tier_a.items():
        d = details.setdefault(rid, {"run_id": rid, "title": "chat (CLI, recovered)", "source": "human",
                                     "category": "human-vs-agent", "moves": [], "outcomes": [],
                                     "reflections": [], "curve": []})
        if not d.get("moves"):
            d["moves"] = moves
            a += 1
    for conv, moves in tier_b.items():
        if not moves:
            continue
        d = details.get(conv)                                   # conv == run_id for real browser sessions
        if d is not None:
            if not d.get("moves"):
                d["moves"] = moves
                d["title"] = d.get("title") or "chat: browser haggle (recovered)"
                b += 1
        elif sum(1 for m in moves if m["role"] == "buyer") >= 2:   # no job span captured, but a real exchange
            details[f"recovered-{conv[:12]}"] = {
                "run_id": f"recovered-{conv[:12]}", "title": "chat: browser haggle (recovered)",
                "source": "human", "category": "human-vs-agent", "moves": moves,
                "outcomes": [], "reflections": [], "curve": []}
            bn += 1

    print(f"  backfill: {len(by_run)} runs · Tier A (CLI): {a} · Tier B (browser): {b} "
          f"· Tier B standalone: {bn}")
    return details


def main() -> None:
    if "--show-query" in sys.argv:
        print(_export_query())
        return
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not args:
        print("Usage: uv run python scripts/ingest_export.py <export.csv|export.json> [more files…]")
        print("       uv run python scripts/ingest_export.py --show-query   # SQL to paste into Explore")
        return
    rows: list[dict] = []
    for a in args:
        p = Path(a)
        if not p.exists():
            print(f"File not found: {p}")
            return
        these = _read_rows(p)
        print(f"Read {len(these)} rows from {p}")
        rows.extend(these)
    details = _build(rows)
    store = history.get_history()
    store.bulk_replace([(history.summarize(rid, d), d) for rid, d in details.items()])
    with_moves = sum(1 for d in details.values() if d.get("moves"))
    print(f"\nDone → {type(store).__name__}: {len(details)} runs, {with_moves} with transcripts.")


if __name__ == "__main__":
    main()
