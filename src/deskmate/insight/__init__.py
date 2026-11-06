"""Track B (M4): summaries → clusters → insight note (§2.5 steps 3–4) and the note lifecycle.

Public entry points:

    build_insight(settings, llm, profile, period, *, now=None) -> InsightNote
    load_insight(settings, profile, period) -> tuple[InsightNote, str] | None
    render_note_body(note, bookmarks) -> str

``build_insight`` runs the whole pipeline for one profile and period:
sync is NOT part of it (callers run ``deskmate.sync.sync_profiles`` first),
then ``deskmate.summarize.summarize_bookmarks`` for bookmarks in the period,
then clustering via ``llm.cluster`` and note rendering. It preserves existing
``## 대화 기록`` sections when regenerating a stale note.
"""

from __future__ import annotations
from datetime import datetime

from deskmate.llm import BatchLLM
from deskmate.models import Bookmark, InsightNote
from deskmate.periods import Period
from deskmate.settings import DeskmateSettings


def load_insight(settings: DeskmateSettings, profile: str, period: Period) -> tuple[InsightNote, str] | None:
    """Return the stored note (and its rendered body) for ``profile``/``period`` if it exists."""
    raise NotImplementedError("track B: deskmate.insight is not implemented yet")


def render_note_body(note: InsightNote, bookmarks: list[Bookmark]) -> str:
    """Render the human-readable Obsidian body (clusters, correlations, questions, ``[[links]]``)."""
    raise NotImplementedError("track B: deskmate.insight is not implemented yet")


def build_insight(
    settings: DeskmateSettings,
    llm: BatchLLM,
    profile: str,
    period: Period,
    *,
    now: datetime | None = None,
) -> InsightNote:
    """Summarize + cluster + write the note for one profile and period. Implemented in track B."""
    raise NotImplementedError("track B: deskmate.insight is not implemented yet")
