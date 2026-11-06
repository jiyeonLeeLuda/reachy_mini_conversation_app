"""Track B (M3): URL fetch + per-bookmark summary written into ``## 요약`` (§2.5 steps 1–2).

Public entry point:

    summarize_bookmarks(settings, llm, bookmarks, *, now=None) -> SummarizeReport

Rules the implementation must keep (see design doc): fetch-stage 2MB cap,
binary content types fail fast, redirect limit 5, meta-charset first, bodies
under ``MIN_BODY_CHARS`` count as ``fetch_failed``, excluded URL patterns are
never fetched, ``fetch_failed`` retries back off (1 → 3 → 7 days, max 3),
``ok`` bookmarks are never re-summarized, every write goes through
``deskmate.store.modify_bookmark``.
"""

from __future__ import annotations
from datetime import datetime
from dataclasses import field, dataclass

from deskmate.llm import BatchLLM
from deskmate.models import Bookmark
from deskmate.settings import DeskmateSettings


# --- tuning constants (§2.3: module constants until M7 promotes them to .env) ---
FETCH_MAX_BYTES = 2 * 1024 * 1024
FETCH_TIMEOUT_S = 10.0
FETCH_MAX_REDIRECTS = 5
MIN_BODY_CHARS = 200
DAILY_MAX_SUMMARIES = 100
CALL_INTERVAL_S = 6.0
RETRY_BACKOFF_DAYS: tuple[int, ...] = (1, 3, 7)


@dataclass
class SummarizeReport:
    """Outcome of one summarize run."""

    summarized: list[str] = field(default_factory=list)  # guids now ok
    failed: list[str] = field(default_factory=list)  # guids marked fetch_failed this run
    skipped: list[str] = field(default_factory=list)  # already ok / excluded / backoff
    warnings: list[str] = field(default_factory=list)


def summarize_bookmarks(
    settings: DeskmateSettings,
    llm: BatchLLM,
    bookmarks: list[Bookmark],
    *,
    now: datetime | None = None,
) -> SummarizeReport:
    """Fetch and summarize every bookmark that still needs it. Implemented in track B."""
    raise NotImplementedError("track B: deskmate.summarize is not implemented yet")
