"""Run the full insight pipeline (sync → summarize → cluster → note) in the background.

Long-running: the backends run every tool through ``BackgroundToolManager``,
so the model only sees the result when this coroutine returns, exactly like a
pomodoro phase ending. ``get_insight`` hands off to this tool when the note is
missing or stale.
"""

from __future__ import annotations
import time
import asyncio
import logging
from typing import Any

import deskmate.sync as sync_mod
import deskmate.insight as insight_mod
from deskmate.llm import build_llm
from deskmate.periods import Period
from deskmate.settings import DeskmateSettings
from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies
from reachy_mini_conversation_app.tools.get_insight import PERIOD_PROPERTIES
from reachy_mini_conversation_app.tools._deskmate_common import (
    ToolContext,
    elapsed_ms,
    empty_result,
    profile_hint,
    ready_result,
    prepare_context,
)


logger = logging.getLogger(__name__)

BUILT_NEXT_ACTION = (
    "인사이트 생성이 끝났다. 묶음 하나와 질문 하나로 시작하라: 첫 묶음의 summary와 correlation을 짧게 줄인 "
    "제목으로 근거를 짚어 한두 문장으로 말하고, 발화는 반드시 그 묶음의 question으로 끝내라. 나머지 묶음은 "
    "사용자가 반응한 뒤 하나씩 꺼내라. unavailable에 있는 북마크는 '제목만 보고 하는 얘긴데'라고만 밝히고, "
    "읽었는지·개수·묵힌 기간으로 평가하지 마라. 노트에 없는 내용은 말하지 마라."
)


class BuildInsight(Tool):
    """Generate (or regenerate) the insight note for a period; returns when the note is written."""

    # Long-running tool: awaits the whole batch pipeline in a worker thread.
    # task_status / task_cancel work on it through the BackgroundToolManager.
    name = "build_insight"
    description = (
        "Build the weekly insight note for a period (sync bookmarks, summarize, cluster). Call it only "
        "when get_insight returned status 'generating', with the same since/until/profile. It takes a "
        "while; the result arrives when the note is ready and tells you how to start talking. "
    )
    parameters_schema = {
        "type": "object",
        "properties": dict(PERIOD_PROPERTIES),
        "required": [],
    }

    def __init__(self) -> None:
        """Append the configured profile names to the description."""
        self.description = self.description + profile_hint()

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Run the pipeline off the event loop and return ready / empty / error."""
        started = time.perf_counter()
        logger.info("build_insight start: %s", {k: v for k, v in kwargs.items() if k != "tool_manager"})
        ctx = prepare_context(kwargs)
        if not isinstance(ctx, ToolContext):
            return ctx
        try:
            # CancelledError (task_cancel) is not an Exception subclass: it propagates.
            result = await asyncio.to_thread(_run_pipeline, ctx)
        except Exception as exc:
            logger.exception("build_insight failed")
            result = {"error": f"{type(exc).__name__}: {exc}", "profile": ctx.profile}
        logger.info("build_insight done in %.0f ms: status=%s", elapsed_ms(started), result.get("status", "error"))
        return result


def _sync(settings: DeskmateSettings, profile: str) -> str | None:
    """Mirror Chrome bookmarks; return a warning string instead of failing the pipeline."""
    try:
        report = sync_mod.sync_profiles(settings, profiles=[profile])
    except NotImplementedError as exc:
        logger.warning("build_insight: sync unavailable, continuing with the repository as is: %s", exc)
        return f"sync skipped: {exc}"
    except Exception as exc:
        logger.warning("build_insight: sync failed, continuing with the repository as is: %s", exc)
        return f"sync failed: {type(exc).__name__}: {exc}"
    warnings = getattr(report, "warnings", None) or []
    return "; ".join(str(item) for item in warnings) or None


def _build(settings: DeskmateSettings, profile: str, period: Period) -> Any:
    llm = build_llm(settings.gemini_api_key, settings.batch_model)
    return insight_mod.build_insight(settings, llm, profile, period)


def _run_pipeline(ctx: ToolContext) -> dict[str, Any]:
    """Blocking pipeline body (worker thread)."""
    warning = _sync(ctx.settings, ctx.profile)
    note = _build(ctx.settings, ctx.profile, ctx.period)
    if note is None or getattr(note, "path", None) is None:
        result = empty_result(ctx)
    else:
        result = ready_result(note, ctx.profile, BUILT_NEXT_ACTION)
    if warning:
        result["sync_warning"] = warning
    return result
