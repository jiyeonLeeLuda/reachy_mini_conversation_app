"""Run the full insight pipeline (sync → summarize → cluster → note) in the background.

Long-running: the backends run every tool through ``BackgroundToolManager``,
so the model only sees the result when this coroutine returns, exactly like a
pomodoro phase ending. ``get_insight`` hands off to this tool when the note is
missing or stale.

M7: one call summarizes at most ``batch_max_summaries`` pending bookmarks (and
never past the daily cap) and writes the note from everything summarized so
far. Pending bookmarks left → ``status: partial`` with the counts; calling
again continues from them. While the pipeline runs the profile/period is
registered so ``get_insight`` answers ``backfilling``.
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
from reachy_mini_conversation_app.deskmate_progress import working_signal
from reachy_mini_conversation_app.tools.get_insight import PERIOD_PROPERTIES
from reachy_mini_conversation_app.tools._deskmate_common import (
    ToolContext,
    building,
    elapsed_ms,
    empty_result,
    profile_hint,
    ready_result,
    partial_result,
    prepare_context,
)


logger = logging.getLogger(__name__)

BUILT_NEXT_ACTION = (
    "인사이트 생성이 끝났다. 묶음 하나와 질문 하나로 시작하라: 첫 묶음의 summary와 correlation을 짧게 줄인 "
    "제목으로 근거를 짚어 짧은 문장 최대 두 개로 말하고, 발화는 반드시 그 묶음의 question으로 끝내라. 나머지 "
    "묶음은 사용자가 반응한 뒤 하나씩 꺼내라. unavailable에 있는 북마크는 '제목만 보고 하는 얘긴데'라고만 "
    "밝히고, 읽었는지·개수·묵힌 기간으로 평가하지 마라. 노트에 없는 내용은 말하지 마라. 한국어로만 말한다."
)
DEGRADED_NEXT_ACTION = (
    "요약 서비스가 바빠서 새 인사이트를 못 만들었다. 대신 이전에 만든 인사이트(이 결과의 clusters)로 이야기한다. "
    "먼저 '요약 서비스가 바빠서 지난번 정리로 얘기할게'라고 한 문장으로 알리고, pending_titles에 있는 북마크 "
    "{count}건은 아직 못 봤다고 짧게 줄인 제목으로 말한 뒤, 첫 묶음의 요약 한 문장과 question으로 끝내라. "
    "한국어로만 말한다."
)
BUSY_NEXT_ACTION = (
    "요약 서비스가 바빠서 지금은 북마크를 못 봤다고 한 문장으로 짧게 사과하고, 조금 뒤에 다시 하자고 말하라. "
    "다른 설명은 덧붙이지 마라."
)


class BuildInsight(Tool):
    """Generate (or regenerate) the insight note for a period; returns when the note is written."""

    # Long-running tool: awaits the whole batch pipeline in a worker thread.
    # task_status / task_cancel work on it through the BackgroundToolManager.
    name = "build_insight"
    description = (
        "Build the weekly insight note for a period (sync bookmarks, summarize, cluster). Call it only "
        "when get_insight returned status 'generating', or 'partial' and the user asks to continue, with "
        "the same since/until/profile. It takes a while; the result arrives when the note is ready (or "
        "'partial' when more bookmarks than one batch allows are still pending) and tells you how to start talking. "
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
            with building(ctx.profile, ctx.period):
                async with working_signal(deps):
                    result = await asyncio.to_thread(_run_pipeline, ctx)
        except Exception as exc:
            logger.exception("build_insight failed")
            result = {"error": f"{type(exc).__name__}: {exc}", "profile": ctx.profile}
            if _looks_like_model_outage(exc):
                result["next_action"] = BUSY_NEXT_ACTION
        logger.info("build_insight done in %.0f ms: status=%s", elapsed_ms(started), result.get("status", "error"))
        return result


def _looks_like_model_outage(exc: BaseException) -> bool:
    """Whether the failure is the batch model being busy/unreachable (vs. a bug) → friendlier wording."""
    if isinstance(exc, insight_mod.ClusterUnavailableError):
        return True
    text = str(exc).lower()
    return any(
        marker in text for marker in ("503", "unavailable", "timeout", "timed out", "429", "resource_exhausted")
    )


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
    elif getattr(note, "degraded", False):
        pending = list(getattr(note, "pending_titles", []) or [])
        result = ready_result(note, ctx.profile, DEGRADED_NEXT_ACTION.format(count=len(pending)))
        result["degraded"] = True
        result["pending_titles"] = pending
    elif not getattr(note, "complete", True):
        result = partial_result(note, ctx, BUILT_NEXT_ACTION)
    else:
        result = ready_result(note, ctx.profile, BUILT_NEXT_ACTION)
    if warning:
        result["sync_warning"] = warning
    return result
