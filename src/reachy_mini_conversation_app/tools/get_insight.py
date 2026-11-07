"""Return the weekly-insight note for a period immediately (design doc §2.2).

Never does heavy work: a missing or stale note yields ``status: generating`` and
tells the model to call ``build_insight`` (the pomodoro focus→break hand-off
pattern), so the voice loop is never blocked by fetching or LLM calls.
"""

from __future__ import annotations
import time
import logging
from typing import Any

from deskmate.store import note_path, read_note, note_is_stale, bookmarks_in_period
from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies
from reachy_mini_conversation_app.tools._deskmate_common import (
    READY_NEXT_ACTION,
    ToolContext,
    today_iso,
    elapsed_ms,
    empty_result,
    profile_hint,
    ready_result,
    prepare_context,
    sync_before_read,
)


logger = logging.getLogger(__name__)

PERIOD_PROPERTIES: dict[str, Any] = {
    "days": {
        "type": "integer",
        "description": "Number of days back from until (inclusive). Default 7. Do not combine with since.",
    },
    "since": {"type": "string", "description": "Start date YYYY-MM-DD (inclusive). Do not combine with days."},
    "until": {"type": "string", "description": "End date YYYY-MM-DD (inclusive). Defaults to today."},
    "profile": {"type": "string", "description": "Chrome profile folder name. Omit for the default profile."},
}


class GetInsight(Tool):
    """Read the insight note for a period, or hand off generation to ``build_insight``."""

    name = "get_insight"
    description = (
        "Get the weekly insight (topic clusters, correlations, one question each) for the user's "
        "bookmarks in a period. Returns immediately. status 'ready' has the clusters; 'generating' "
        "means you must call build_insight next; 'empty' means no bookmarks in the period. "
        "Use days (default 7) or since/until, never both. "
    )
    parameters_schema = {
        "type": "object",
        "properties": dict(PERIOD_PROPERTIES),
        "required": [],
    }

    def __init__(self) -> None:
        """Append the configured profile names to the description (model must not invent them)."""
        self.description = self.description + profile_hint()

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Return ready / generating / empty for the requested period."""
        started = time.perf_counter()
        logger.info("get_insight start: %s", {k: v for k, v in kwargs.items() if k != "tool_manager"})
        try:
            result = self._run(kwargs)
        except Exception as exc:  # never raise into the loop
            logger.exception("get_insight failed")
            result = {"error": f"{type(exc).__name__}: {exc}"}
        logger.info("get_insight done in %.0f ms: status=%s", elapsed_ms(started), result.get("status", "error"))
        return result

    def _run(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        ctx = prepare_context(kwargs)
        if not isinstance(ctx, ToolContext):
            return ctx

        sync_warning = sync_before_read(ctx.settings, ctx.profile)
        result = self._read(ctx, bookmarks_in_period(ctx.settings, ctx.profile, ctx.period))
        if sync_warning:
            result["sync_warning"] = sync_warning
        return result

    def _read(self, ctx: ToolContext, bookmarks: list[Any]) -> dict[str, Any]:
        if not bookmarks:
            return empty_result(ctx)

        path = note_path(ctx.settings, ctx.profile, ctx.period)
        if path.is_file():
            try:
                note, _body = read_note(path)
            except ValueError as exc:
                logger.warning("Unreadable insight note %s: %s", path, exc)
            else:
                if not note_is_stale(note, bookmarks):
                    return ready_result(note, ctx.profile, READY_NEXT_ACTION)

        call = ctx.args.build_insight_call(ctx.profile)
        return {
            "status": "generating",
            "today": today_iso(),
            "profile": ctx.profile,
            "period": ctx.period.to_dict(),
            "bookmark_count": len(bookmarks),
            "next_action": (
                "이 기간의 인사이트 노트가 아직 없거나 낡았다. 먼저 반드시 사용자에게 '잠깐 훑어볼게' 한마디를 "
                f"소리 내어 말한 다음에 {call}를 호출하라. 도구가 도는 동안 사용자가 말을 걸면 한국어로 짧게 "
                "'아직 훑는 중이야'라고 답하라. 결과가 돌아오면 그때 묶음 하나와 질문 하나로 이야기를 시작한다."
            ),
        }
