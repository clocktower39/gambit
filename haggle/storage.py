"""Persistence for episodes, strategies, and run metrics.

Two backends behind one tiny interface:
  - InMemoryStore (default): everything in RAM, optional JSON dump under runs/.
  - PostgresStore: DigitalOcean managed Postgres + pgvector, used when DATABASE_URL is set.

get_store() returns PostgresStore when DATABASE_URL is present and psycopg imports cleanly,
otherwise InMemoryStore — so the self-improvement loop runs before the DB is provisioned.

The vector `memory` table is Phase-2 (continual-learning retrieval); the rest is MVP.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import asdict

from .models import Episode, Strategy


def _episode_row(ep: Episode, generation: int) -> dict:
    return {
        "generation": generation,
        "item": asdict(ep.item),
        "persona": asdict(ep.persona),
        "strategy_name": ep.strategy_name,
        "messages": [asdict(m) for m in ep.messages],
        "outcome": asdict(ep.outcome) if ep.outcome else None,
    }


def _strategy_parts(strat: Strategy) -> tuple[str, int, str, dict]:
    d = asdict(strat)
    name, gen, tactics = d.pop("name"), d.pop("gen"), d.pop("tactics")
    return name, gen, tactics, d  # d == the numeric knobs


# ---------------------------------------------------------------------------
class InMemoryStore:
    """Zero-dependency default. Good enough to run the whole loop locally."""

    def __init__(self):
        self.episodes: list[dict] = []
        self.strategies: list[dict] = []
        self.generations: dict[int, dict] = {}
        self.memories: list[dict] = []

    def save_episode(self, ep: Episode, generation: int = 0) -> None:
        self.episodes.append(_episode_row(ep, generation))

    def save_strategy(self, strat: Strategy, score: float) -> None:
        self.strategies.append({**asdict(strat), "score": score})

    def save_generation(self, generation: int, summary: dict) -> None:
        self.generations[generation] = summary

    def metrics_curve(self) -> list[dict]:
        return [{"generation": g, **s} for g, s in sorted(self.generations.items())]

    def add_memory(self, text: str, embedding: list[float], meta: dict | None = None) -> None:
        self.memories.append({"text": text, "embedding": embedding, "meta": meta or {}})

    def search_memory(self, embedding: list[float], k: int = 5) -> list[dict]:
        def cos(a, b):
            dot = sum(x * y for x, y in zip(a, b))
            na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
            return dot / (na * nb) if na and nb else 0.0

        ranked = sorted(self.memories, key=lambda m: cos(m["embedding"], embedding), reverse=True)
        return [{"text": m["text"], "meta": m["meta"]} for m in ranked[:k]]

    def dump_json(self, path: str = "runs/run.json") -> str:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump({"episodes": self.episodes, "strategies": self.strategies,
                       "generations": self.generations}, f, indent=2)
        return path


# ---------------------------------------------------------------------------
_SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS episodes (
    id BIGSERIAL PRIMARY KEY,
    generation INT,
    item JSONB, persona JSONB, strategy_name TEXT,
    messages JSONB, outcome JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS strategies (
    id BIGSERIAL PRIMARY KEY,
    name TEXT, gen INT, knobs JSONB, tactics TEXT, score DOUBLE PRECISION,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS generations (
    generation INT PRIMARY KEY, summary JSONB, created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS memory (
    id BIGSERIAL PRIMARY KEY, text TEXT, embedding vector({dim}), meta JSONB
);
"""


class PostgresStore:
    """DigitalOcean managed Postgres + pgvector. Same interface as InMemoryStore."""

    def __init__(self, dsn: str, embed_dim: int = 1024):
        import psycopg
        from pgvector.psycopg import register_vector

        self._psycopg = psycopg
        self.conn = psycopg.connect(dsn, autocommit=True)
        with self.conn.cursor() as cur:
            cur.execute(_SCHEMA.format(dim=embed_dim))
        register_vector(self.conn)

    def _jsonb(self, value):
        from psycopg.types.json import Jsonb

        return Jsonb(value)

    def save_episode(self, ep: Episode, generation: int = 0) -> None:
        row = _episode_row(ep, generation)
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO episodes (generation, item, persona, strategy_name, messages, outcome)"
                " VALUES (%s, %s, %s, %s, %s, %s)",
                (generation, self._jsonb(row["item"]), self._jsonb(row["persona"]),
                 row["strategy_name"], self._jsonb(row["messages"]),
                 self._jsonb(row["outcome"])),
            )

    def save_strategy(self, strat: Strategy, score: float) -> None:
        name, gen, tactics, knobs = _strategy_parts(strat)
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO strategies (name, gen, knobs, tactics, score) VALUES (%s, %s, %s, %s, %s)",
                (name, gen, self._jsonb(knobs), tactics, score),
            )

    def save_generation(self, generation: int, summary: dict) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO generations (generation, summary) VALUES (%s, %s)"
                " ON CONFLICT (generation) DO UPDATE SET summary = EXCLUDED.summary",
                (generation, self._jsonb(summary)),
            )

    def metrics_curve(self) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT generation, summary FROM generations ORDER BY generation")
            return [{"generation": g, **s} for g, s in cur.fetchall()]

    def add_memory(self, text: str, embedding: list[float], meta: dict | None = None) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO memory (text, embedding, meta) VALUES (%s, %s, %s)",
                (text, embedding, self._jsonb(meta or {})),
            )

    def search_memory(self, embedding: list[float], k: int = 5) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT text, meta, 1 - (embedding <=> %s) AS score FROM memory"
                " ORDER BY embedding <=> %s LIMIT %s",
                (embedding, embedding, k),
            )
            return [{"text": t, "meta": m, "score": s} for t, m, s in cur.fetchall()]


def get_store():
    """Pick a backend: Postgres if DATABASE_URL is set and usable, else in-memory."""
    dsn = os.getenv("DATABASE_URL")
    if dsn:
        try:
            return PostgresStore(dsn, embed_dim=int(os.getenv("EMBED_DIM", "1024")))
        except Exception as exc:  # missing driver, unreachable DB, etc.
            print(f"[storage] Postgres unavailable ({exc}); falling back to in-memory store.")
    return InMemoryStore()
