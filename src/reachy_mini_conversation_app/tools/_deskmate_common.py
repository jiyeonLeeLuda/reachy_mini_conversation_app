"""Shared helpers for the DeskMate tools (design doc §2.2).

Not a tool itself: the leading underscore keeps ``list_tool_module_names`` from
discovering it. Everything that more than one DeskMate tool needs lives here:
settings loading, profile / period resolution, ``today`` and the shared result
shapes (``empty`` / ``ready``). Settings are loaded on every call (never at
import time) so the environment can change under the running app and tests
can monkeypatch it.
"""

from __future__ import annotations
import time
import logging
from typing import Any
from datetime import date
from dataclasses import dataclass

import deskmate.sync as sync_mod
from deskmate.store import list_profiles
from deskmate.models import InsightNote
from deskmate.periods import Period, PeriodError, resolve_period
from deskmate.session import SESSION_MANAGER, now_local_label
from deskmate.settings import ENV_BOOKMARK_REPO, DeskmateSettings, load_settings


logger = logging.getLogger(__name__)

__all__ = ["now_local_label"]  # re-exported from deskmate.session for the tools

# --- tuning constants ---------------------------------------------------------
FALLBACK_PROFILE = "Default"
DEFAULT_DAYS = 7
DEFAULT_PERIOD_LABEL = "지난 일주일"
SYNC_MIN_INTERVAL_S = 30.0  # read-tools re-sync Chrome at most this often per profile (0.1 s for 360 bookmarks)

# --- next_action texts (§3.1 / §3.2, tuned per profile prompt later) ----------
NOT_CONFIGURED_NEXT_ACTION = "사용자에게 북마크 저장소가 설정되지 않았다고 짧게 말하라"
UNKNOWN_PROFILE_NEXT_ACTION = "쓸 수 있는 프로필 이름을 말해 주라"
READY_NEXT_ACTION = (
    "노트가 준비됐다. 발화는 반드시 이 결과의 clusters를 근거로 하고, 기억이나 추측으로 북마크 내용을 "
    "말하지 마라. 한 번의 발화에 묶음 하나와 질문 하나만 꺼내고, 사용자가 반응한 뒤에 다음 묶음으로 "
    "넘어가라. 읽었는지·몇 개 모았는지·얼마나 묵혔는지 평가하지 말고, 왜 저장했는지도 묻지 마라. "
    "상관관계를 말할 때는 어느 북마크끼리인지 짧게 줄인 제목으로 짚고 긴 제목을 그대로 읽지 마라. "
    "unavailable에 있는 북마크는 '제목만 보고 하는 얘긴데'라고 밝혀라. 첫 발화는 짧은 문장 최대 두 개와 "
    "질문 하나로 끝낸다: 첫 묶음의 summary와 correlation을 한 문장씩 줄여 말하고, 반드시 그 묶음의 "
    "question으로 끝내라. 한국어로만 말한다."
)


def _today() -> date:
    """Return the local date (patched in tests)."""
    return date.today()


def today_iso() -> str:
    """ISO ``today`` included in every successful tool result (§2.2)."""
    return _today().isoformat()


def elapsed_ms(started: float) -> float:
    """Milliseconds since ``started`` (a ``time.perf_counter()`` value)."""
    return (time.perf_counter() - started) * 1000.0


# --- Chrome sync before reading (a bookmark saved a second ago must be visible) ----------

_LAST_SYNC_AT: dict[str, float] = {}  # profile → time.monotonic() of the last sync by a read tool


def reset_sync_throttle() -> None:
    """Forget the last sync times (tests)."""
    _LAST_SYNC_AT.clear()


def sync_before_read(settings: DeskmateSettings, profile: str) -> str | None:
    """Mirror Chrome into the repo for ``profile`` unless it was done within ``SYNC_MIN_INTERVAL_S``.

    Returns a short warning string (or ``None``); never raises, the tools still
    answer from whatever the repository holds.
    """
    now = time.monotonic()
    last = _LAST_SYNC_AT.get(profile)
    if last is not None and now - last < SYNC_MIN_INTERVAL_S:
        return None
    _LAST_SYNC_AT[profile] = now
    try:
        report = sync_mod.sync_profiles(settings, profiles=[profile])
    except Exception as exc:
        logger.warning("sync before read failed for %s (continuing with the repository): %s", profile, exc)
        return f"sync failed: {type(exc).__name__}: {exc}"
    warnings = [str(item) for item in (getattr(report, "warnings", None) or [])]
    if warnings:
        logger.warning("sync before read (%s): %s", profile, "; ".join(warnings))
    return "; ".join(warnings) or None


# --- settings / profile ------------------------------------------------------------


def not_configured_error() -> dict[str, Any]:
    """Error returned by every tool when the bookmark repository is not set."""
    return {
        "error": f"deskmate not configured: set {ENV_BOOKMARK_REPO}",
        "next_action": NOT_CONFIGURED_NEXT_ACTION,
    }


def allowed_profiles(settings: DeskmateSettings) -> list[str]:
    """Profiles a tool may target: allow list, else repo folders, else ``Default``."""
    if settings.chrome_profiles:
        return list(settings.chrome_profiles)
    if settings.configured:
        found = list_profiles(settings)
        if found:
            return found
    return [FALLBACK_PROFILE]


def default_profile(settings: DeskmateSettings, allowed: list[str]) -> str:
    """Profile used when the model omits the ``profile`` argument."""
    return settings.default_profile or allowed[0]


def profile_hint() -> str:
    """Short sentence appended to tool descriptions so the model never invents a profile name."""
    try:
        settings = load_settings()
    except Exception:  # defensive: a description must never break tool registration
        return "profile is optional (Chrome profile folder name)."
    allowed = allowed_profiles(settings)
    return f"profile is optional and must be one of: {', '.join(allowed)} (default: {default_profile(settings, allowed)})."


def resolve_profile(settings: DeskmateSettings, requested: Any) -> tuple[str | None, dict[str, Any] | None]:
    """Return ``(profile, None)`` or ``(None, error_dict)`` for an unknown profile."""
    allowed = allowed_profiles(settings)
    if requested is None or str(requested).strip() == "":
        return default_profile(settings, allowed), None
    name = str(requested).strip()
    if name not in allowed:
        return None, {"error": "unknown profile", "available": allowed, "next_action": UNKNOWN_PROFILE_NEXT_ACTION}
    return name, None


# --- period --------------------------------------------------------------------


def _optional_int(value: Any, label: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise PeriodError(f"{label} must be an integer, got {value!r}") from exc


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass(frozen=True)
class PeriodArgs:
    """Normalized ``days`` / ``since`` / ``until`` arguments plus the resolved range."""

    days: int | None
    since: str | None
    until: str | None
    period: Period

    @property
    def explicit(self) -> bool:
        """Whether the model gave since/until (changes the empty-period wording)."""
        return self.since is not None or self.until is not None

    def label(self) -> str:
        """Korean period wording for §3.2 ("지난 일주일" or the explicit range)."""
        if self.explicit:
            return f"{self.period.since.isoformat()}부터 {self.period.until.isoformat()}까지"
        if self.days is None or self.days == DEFAULT_DAYS:
            return DEFAULT_PERIOD_LABEL
        return f"지난 {self.days}일"

    def build_insight_call(self, profile: str) -> str:
        """Exact ``build_insight(...)`` call text the model should repeat."""
        return (
            f"build_insight(since='{self.period.since.isoformat()}', "
            f"until='{self.period.until.isoformat()}', profile='{profile}')"
        )


def resolve_period_args(days: Any = None, since: Any = None, until: Any = None) -> PeriodArgs:
    """Resolve raw tool kwargs into a ``PeriodArgs`` (raises ``PeriodError``)."""
    day_count = _optional_int(days, "days")
    since_text = _optional_str(since)
    until_text = _optional_str(until)
    period = resolve_period(days=day_count, since=since_text, until=until_text, today=_today())
    return PeriodArgs(days=day_count, since=since_text, until=until_text, period=period)


# --- combined context ----------------------------------------------------------------


@dataclass(frozen=True)
class ToolContext:
    """Settings, profile and period a period-based DeskMate tool works on."""

    settings: DeskmateSettings
    profile: str
    args: PeriodArgs

    @property
    def period(self) -> Period:
        """Resolved inclusive date range."""
        return self.args.period


def prepare_context(kwargs: dict[str, Any]) -> ToolContext | dict[str, Any]:
    """Validate settings, profile and period from tool kwargs; return an error dict on failure."""
    settings = load_settings()
    if not settings.configured:
        return not_configured_error()
    profile, error = resolve_profile(settings, kwargs.get("profile"))
    if error is not None or profile is None:
        return error or {"error": "unknown profile"}
    try:
        args = resolve_period_args(kwargs.get("days"), kwargs.get("since"), kwargs.get("until"))
    except PeriodError as exc:
        return {"error": str(exc)}
    return ToolContext(settings=settings, profile=profile, args=args)


# --- shared results ----------------------------------------------------------------


def empty_result(ctx: ToolContext) -> dict[str, Any]:
    """``status: empty`` with the §3.2 empty-period line (period wording adapted)."""
    label = ctx.args.label()
    return {
        "status": "empty",
        "today": today_iso(),
        "profile": ctx.profile,
        "period": ctx.period.to_dict(),
        "bookmark_count": 0,
        "next_action": (
            "이 기간에는 북마크가 없다. 재촉이나 평가 없이 이렇게 말하고 대화를 이어라: "
            f'"{label} 동안은 새로 저장한 게 없네. 요즘 관심 있는 건 뭐야?"'
        ),
    }


def ready_result(note: InsightNote, profile: str, next_action: str) -> dict[str, Any]:
    """``status: ready`` from a note; opens the insight session (§3.3)."""
    if note.path is not None:
        SESSION_MANAGER.open(profile, note.path)
    result: dict[str, Any] = {"status": "ready", "today": today_iso()}
    result.update(note.to_tool_result())
    result["profile"] = profile
    result["next_action"] = next_action
    return result
