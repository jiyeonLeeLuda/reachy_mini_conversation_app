"""List non-archived bookmarks in a period, newest first (design doc §2.2)."""

from __future__ import annotations
import time
import logging
from typing import Any

from deskmate.store import bookmarks_in_period
from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies
from reachy_mini_conversation_app.tools.get_insight import PERIOD_PROPERTIES
from reachy_mini_conversation_app.tools._deskmate_common import (
    ToolContext,
    today_iso,
    elapsed_ms,
    profile_hint,
    prepare_context,
    sync_before_read,
)


logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 20
MAX_LIMIT = 200

LIST_NEXT_ACTION = (
    "목록은 보조 자료다. 사용자가 찾는 북마크를 짧게 줄인 제목으로 짚어 주고, 내용이 궁금하면 그 id로 "
    "get_bookmark를 호출하라. 개수나 읽었는지로 평가하지 마라."
)


class ListBookmarks(Tool):
    """Secondary lookup for bookmarks that the insight note does not mention."""

    name = "list_bookmarks"
    description = (
        "List the user's bookmarks saved in a period (newest first; archived ones excluded). Secondary "
        "tool: use it when something is not in the insight note. Use days (default 7) or since/until, "
        "never both. "
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            **PERIOD_PROPERTIES,
            "limit": {
                "type": "integer",
                "description": f"Maximum number of bookmarks to return. Default {DEFAULT_LIMIT}.",
            },
        },
        "required": [],
    }

    def __init__(self) -> None:
        """Append the configured profile names to the description."""
        self.description = self.description + profile_hint()

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Return the compact bookmark list for the period."""
        started = time.perf_counter()
        logger.info("list_bookmarks start: %s", {k: v for k, v in kwargs.items() if k != "tool_manager"})
        try:
            result = self._run(kwargs)
        except Exception as exc:
            logger.exception("list_bookmarks failed")
            result = {"error": f"{type(exc).__name__}: {exc}"}
        logger.info("list_bookmarks done in %.0f ms: count=%s", elapsed_ms(started), result.get("count", "error"))
        return result

    def _run(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        ctx = prepare_context(kwargs)
        if not isinstance(ctx, ToolContext):
            return ctx
        raw_limit = kwargs.get("limit")
        try:
            limit = DEFAULT_LIMIT if raw_limit is None else int(raw_limit)
        except (TypeError, ValueError):
            return {"error": f"limit must be an integer, got {raw_limit!r}"}
        limit = max(1, min(MAX_LIMIT, limit))

        sync_before_read(ctx.settings, ctx.profile)
        bookmarks = bookmarks_in_period(ctx.settings, ctx.profile, ctx.period)[:limit]
        return {
            "today": today_iso(),
            "profile": ctx.profile,
            "period": ctx.period.to_dict(),
            "count": len(bookmarks),
            "bookmarks": [bookmark.to_tool_summary() for bookmark in bookmarks],
            "next_action": LIST_NEXT_ACTION,
        }
