"""Track B (M3): URL fetch + per-bookmark summary written into ``## 요약`` (§2.5 steps 1–2).

Public entry point:

    summarize_bookmarks(settings, llm, bookmarks, *, now=None, client=None) -> SummarizeReport

Rules the implementation keeps (see design doc): fetch-stage 2MB cap,
binary content types fail fast, redirect limit 5, meta-charset first, bodies
under ``MIN_BODY_CHARS`` count as ``fetch_failed``, excluded URL patterns are
never fetched, ``fetch_failed`` retries back off (1 → 3 → 7 days, max 3),
``ok`` bookmarks are never re-summarized, every write goes through
``deskmate.store.modify_bookmark``.

Submodules: ``fetch`` (HTTP + text extraction, injectable client), ``sections``
(``## 요약`` section edits), ``usage`` (token usage JSONL), ``runner`` (the run
itself; ``runner._sleep`` is the monkeypatch point for the call interval).
"""

from __future__ import annotations
from dataclasses import field, dataclass


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


# The runner reads the constants above, so it is imported once they exist.
from deskmate.summarize.runner import summarize_bookmarks  # noqa: E402


__all__ = [
    "CALL_INTERVAL_S",
    "DAILY_MAX_SUMMARIES",
    "FETCH_MAX_BYTES",
    "FETCH_MAX_REDIRECTS",
    "FETCH_TIMEOUT_S",
    "MIN_BODY_CHARS",
    "RETRY_BACKOFF_DAYS",
    "SummarizeReport",
    "summarize_bookmarks",
]
