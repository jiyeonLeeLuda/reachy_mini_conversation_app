"""Insight note body template (§2.5 step 4).

The body is rendered from the JSON-schema fields only; LLM text appears in
exactly four places per cluster (topic, summary, 관계, 질문) and is flattened
to one line so it can never open a new markdown section.
"""

from __future__ import annotations
from pathlib import Path

from deskmate.store import nfc
from deskmate.models import Bookmark, InsightNote


NOTE_TITLE_PREFIX = "# 위클리 인사이트"
UNAVAILABLE_HEADING = "## 본문 미확보"
CORRELATION_LABEL = "**관계**"
QUESTION_LABEL = "**질문**"


def _one_line(text: str) -> str:
    return " ".join(text.split())


def link_targets(bookmarks: list[Bookmark]) -> dict[str, str]:
    """Map guid → Obsidian link stem (file name without ``.md``) for bookmarks loaded from disk."""
    targets: dict[str, str] = {}
    for bookmark in bookmarks:
        if bookmark.path is None:
            continue
        targets[bookmark.guid] = nfc(Path(bookmark.path).stem)
    return targets


def _link_line(bookmark_id: str, targets: dict[str, str]) -> str:
    stem = targets.get(bookmark_id)
    return f"- [[{stem}]]" if stem else f"- ({bookmark_id})"


def render_note_body(note: InsightNote, bookmarks: list[Bookmark]) -> str:
    """Render the human-readable Obsidian body (clusters, correlations, questions, ``[[links]]``)."""
    targets = link_targets(bookmarks)
    lines: list[str] = [f"{NOTE_TITLE_PREFIX} ({note.since.isoformat()} ~ {note.until.isoformat()})"]
    for cluster in note.clusters:
        lines.append("")
        lines.append(f"## {_one_line(cluster.topic) or '(주제 없음)'}")
        lines.append(_one_line(cluster.summary))
        lines.append("")
        lines.extend(_link_line(bookmark_id, targets) for bookmark_id in cluster.bookmark_ids)
        lines.append("")
        lines.append(f"{CORRELATION_LABEL}: {_one_line(cluster.correlation)}")
        lines.append("")
        lines.append(f"{QUESTION_LABEL}: {_one_line(cluster.question)}")
    if note.unavailable:
        lines.append("")
        lines.append(UNAVAILABLE_HEADING)
        lines.extend(_link_line(bookmark_id, targets) for bookmark_id in note.unavailable)
    return "\n".join(lines) + "\n"
