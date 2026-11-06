"""Return one bookmark's front matter and summary by guid (design doc §2.2)."""

from __future__ import annotations
import time
import logging
from typing import Any

from deskmate.store import find_bookmark
from deskmate.models import SUMMARY_HEADING
from deskmate.settings import load_settings
from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies
from reachy_mini_conversation_app.tools._deskmate_common import today_iso, elapsed_ms, not_configured_error


logger = logging.getLogger(__name__)

BOOKMARK_NEXT_ACTION = "요약을 바탕으로 짧게 답하라. 본문 미확보면 그렇다고 밝혀라"


def extract_summary(body: str) -> str:
    """Return the text under ``## 요약`` (up to the next ``##`` heading), stripped."""
    lines = body.split("\n")
    start = next((i + 1 for i, line in enumerate(lines) if line.strip() == SUMMARY_HEADING), None)
    if start is None:
        return body.strip()
    collected: list[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        collected.append(line)
    return "\n".join(collected).strip()


class GetBookmark(Tool):
    """Fetch one bookmark (title, url, tags, date, summary) for follow-up questions."""

    name = "get_bookmark"
    description = (
        "Get one bookmark's details and its stored summary by id (the id from get_insight clusters or "
        "list_bookmarks). Use it to answer follow-up questions such as 'what was that article about?'. "
        "No profile argument: ids are global."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "id": {"type": "string", "description": "Bookmark id (guid) from get_insight or list_bookmarks."},
        },
        "required": ["id"],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Look the bookmark up across all profiles and return its summary."""
        started = time.perf_counter()
        bookmark_id = str(kwargs.get("id") or "").strip()
        logger.info("get_bookmark start: id=%s", bookmark_id)
        try:
            result = self._run(bookmark_id)
        except Exception as exc:
            logger.exception("get_bookmark failed")
            result = {"error": f"{type(exc).__name__}: {exc}"}
        logger.info("get_bookmark done in %.0f ms: %s", elapsed_ms(started), "error" if "error" in result else "ok")
        return result

    def _run(self, bookmark_id: str) -> dict[str, Any]:
        settings = load_settings()
        if not settings.configured:
            return not_configured_error()
        if not bookmark_id:
            return {"error": "id is required"}
        bookmark = find_bookmark(settings, bookmark_id)
        if bookmark is None:
            return {"error": f"bookmark not found: {bookmark_id}"}
        return {
            "id": bookmark.guid,
            "profile": bookmark.profile,
            "title": bookmark.title,
            "url": bookmark.url,
            "tags": list(bookmark.tags),
            "date": bookmark.date.isoformat(),
            "summary_status": bookmark.summary_status,
            "summary": extract_summary(bookmark.body),
            "today": today_iso(),
            "next_action": BOOKMARK_NEXT_ACTION,
        }
