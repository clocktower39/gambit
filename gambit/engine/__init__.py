"""Domain-agnostic self-improvement engine. Negotiation is a plug-in (see gambit.negotiation)."""

from .run import run_batch, summarize
from .seam import Counterparty, Domain, EpisodeResult, Policy

__all__ = ["EpisodeResult", "Domain", "Policy", "Counterparty", "run_batch", "summarize"]
