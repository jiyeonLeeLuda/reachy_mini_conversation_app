"""Close the open insight conversation and record its conclusion (design doc §2.2, §3.3)."""

from __future__ import annotations
import time
import logging
from typing import Any, ClassVar
from pathlib import Path

from deskmate.store import append_conversation_section
from deskmate.session import SESSION_MANAGER
from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies
from reachy_mini_conversation_app.tools._deskmate_common import elapsed_ms, now_local_label


logger = logging.getLogger(__name__)

ALLOWED_REASONS = ("explicit", "confirmed")
FINISH_NEXT_ACTION = "짧게 마무리 인사를 하라"
NO_SESSION_NEXT_ACTION = (
    "인사이트 세션이 이미 닫혀 있다(자동 종료됐거나 아직 시작하지 않았다). "
    "사용자에게 짧게 알리고, 이어서 하려면 get_insight를 다시 호출하라."
)


class FinishInsight(Tool):
    """End the insight conversation: append ``## 대화 기록`` to the note and close the session."""

    needs_response: ClassVar[bool] = True

    name = "finish_insight"
    description = (
        "Finish the current weekly insight conversation. Call it when the user explicitly asks to wrap up "
        "(reason='explicit') or confirms ending it after a topic change (reason='confirmed'). Pass your "
        "conclusion of the conversation in a few sentences; it is written into the insight note. "
        "No profile argument: the open session knows which note to write."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "conclusion": {
                "type": "string",
                "description": "Your summary of the conversation's conclusions (a few sentences, Korean).",
            },
            "reason": {
                "type": "string",
                "enum": list(ALLOWED_REASONS),
                "description": "'explicit' when the user asked to finish, 'confirmed' when they agreed to end it.",
            },
        },
        "required": ["conclusion"],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Validate the reason, close the session and append the conclusion to the note."""
        started = time.perf_counter()
        reason = str(kwargs.get("reason") or "explicit").strip()
        conclusion = str(kwargs.get("conclusion") or "").strip()
        logger.info("finish_insight start: reason=%s", reason)
        try:
            result = self._run(reason, conclusion)
        except Exception as exc:
            logger.exception("finish_insight failed")
            result = {"error": f"{type(exc).__name__}: {exc}"}
        logger.info("finish_insight done in %.0f ms: %s", elapsed_ms(started), "error" if "error" in result else "ok")
        return result

    def _run(self, reason: str, conclusion: str) -> dict[str, Any]:
        if reason == "auto":
            return {"error": "reason 'auto' is reserved for the app"}
        if reason not in ALLOWED_REASONS:
            return {"error": f"reason must be one of {', '.join(ALLOWED_REASONS)}, got {reason!r}"}
        if not conclusion:
            return {"error": "conclusion is required"}
        session = SESSION_MANAGER.close()
        reopened_last = False
        if session is None:
            # Safety net (§3.3): the session was already closed — by the app (idle / sleep /
            # shutdown) or by a premature explicit finish — but the model finishes again with the
            # real conclusion. It belongs to the last note, so record it there once (consumed).
            last = SESSION_MANAGER.take_last_closed()
            if last is None or not Path(last.note_path).is_file():
                return {"error": "no open insight session", "next_action": NO_SESSION_NEXT_ACTION}
            session, reopened_last = last, True
        append_conversation_section(session.note_path, now_local_label(), conclusion)
        logger.info(
            "finish_insight: recorded conclusion (%s%s) in %s",
            reason,
            ", last closed session" if reopened_last else "",
            session.note_path,
        )
        result: dict[str, Any] = {
            "ok": True,
            "note_path": str(session.note_path),
            "reason": reason,
            "next_action": FINISH_NEXT_ACTION,
        }
        if reopened_last:
            result["reopened_last"] = True
        return result
