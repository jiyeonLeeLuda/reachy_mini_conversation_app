"""Insight batch for one profile and period (§2.5 steps 3–4 and the note lifecycle).

``build_insight`` summarizes what still needs it, sends the summaries to
``llm.cluster``, validates the returned bookmark ids against the period,
renders the note and writes it atomically, keeping any ``## 대화 기록``
sections of a previous note at the same path.
"""

from __future__ import annotations
import logging
from datetime import datetime

import httpx

from deskmate.llm import BatchLLM, SummaryInput
from deskmate.store import note_path, read_note, repo_lock, write_note, bookmarks_in_period
from deskmate.models import Bookmark, InsightNote, InsightCluster
from deskmate.periods import Period
from deskmate.settings import DeskmateSettings
from deskmate.summarize import summarize_bookmarks
from deskmate.insight.render import render_note_body
from deskmate.summarize.usage import log_usage
from deskmate.summarize.runner import iso_utc, resolve_now
from deskmate.summarize.sections import summary_text


logger = logging.getLogger(__name__)


def load_insight(settings: DeskmateSettings, profile: str, period: Period) -> tuple[InsightNote, str] | None:
    """Return the stored note (and its rendered body) for ``profile``/``period`` if it exists."""
    path = note_path(settings, profile, period)
    if not path.is_file():
        return None
    try:
        return read_note(path)
    except (OSError, ValueError) as exc:
        logger.warning("Ignoring unreadable insight note %s: %s", path, exc)
        return None


def cluster_inputs(bookmarks: list[Bookmark]) -> list[SummaryInput]:
    """Turn bookmarks into what the clustering step may see (summary only when ``ok``)."""
    items: list[SummaryInput] = []
    for bookmark in bookmarks:
        summary = summary_text(bookmark.body) if bookmark.summary_status == "ok" else None
        items.append(
            SummaryInput(
                id=bookmark.guid,
                title=bookmark.title,
                url=bookmark.url,
                tags=tuple(bookmark.tags),
                date=bookmark.date.isoformat(),
                summary=summary,
            )
        )
    return items


def sanitize_clusters(clusters: list[InsightCluster], valid_ids: set[str]) -> list[InsightCluster]:
    """Drop bookmark ids the model invented and clusters left empty (logged, never written)."""
    kept: list[InsightCluster] = []
    for cluster in clusters:
        ids: list[str] = []
        for bookmark_id in cluster.bookmark_ids:
            if bookmark_id in valid_ids and bookmark_id not in ids:
                ids.append(bookmark_id)
            elif bookmark_id not in valid_ids:
                logger.warning("Dropping unknown bookmark id %r from cluster %r", bookmark_id, cluster.topic)
        if not ids:
            logger.warning("Dropping cluster %r: no bookmark of the period left", cluster.topic)
            continue
        kept.append(
            InsightCluster(
                topic=cluster.topic,
                bookmark_ids=ids,
                summary=cluster.summary,
                correlation=cluster.correlation,
                question=cluster.question,
            )
        )
    return kept


def _chronological(bookmarks: list[Bookmark]) -> list[Bookmark]:
    return sorted(bookmarks, key=lambda item: (item.date, item.title))


def build_insight(
    settings: DeskmateSettings,
    llm: BatchLLM,
    profile: str,
    period: Period,
    *,
    now: datetime | None = None,
    client: httpx.Client | None = None,
) -> InsightNote:
    """Summarize + cluster + write the note for one profile and period.

    An empty period returns a note with no clusters and ``path=None`` and
    writes nothing. ``client`` and ``now`` are forwarded to the summarizer.
    """
    moment = resolve_now(now)
    bookmarks = bookmarks_in_period(settings, profile, period)
    if not bookmarks:
        return InsightNote(profile=profile, since=period.since, until=period.until, generated_at=iso_utc(moment))

    report = summarize_bookmarks(settings, llm, bookmarks, now=moment, client=client)
    for warning in report.warnings:
        logger.warning("summarize: %s", warning)

    with repo_lock(settings):
        bookmarks = _chronological(bookmarks_in_period(settings, profile, period))
        result = llm.cluster(cluster_inputs(bookmarks))
        log_usage(settings, profile=profile, op="cluster", usage=result.usage)
        valid_ids = {bookmark.guid for bookmark in bookmarks}
        existing = load_insight(settings, profile, period)
        note = InsightNote(
            profile=profile,
            since=period.since,
            until=period.until,
            generated_at=iso_utc(moment if now is not None else resolve_now(None)),
            clusters=sanitize_clusters(result.clusters, valid_ids),
            unavailable=[bookmark.guid for bookmark in bookmarks if bookmark.summary_status != "ok"],
            bookmark_ids=[bookmark.guid for bookmark in bookmarks],
            complete=True,
            conversations=list(existing[0].conversations) if existing is not None else [],
        )
        write_note(note, render_note_body(note, bookmarks), note_path(settings, profile, period))
    return note
