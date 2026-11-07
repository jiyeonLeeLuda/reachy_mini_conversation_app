"""App-side hooks for the DeskMate insight session (design doc §3.3, M6).

The LLM only ever closes an insight conversation explicitly (``finish_insight``).
Everything else is the app's job and lives here, next to the other lifecycle
glue: every conversation activity is a heartbeat, and the session is closed
with the ``자동 종료`` marker when the user stays silent, when Reachy goes to
sleep, or when the app shuts down. No LLM call is involved in any of these.
"""

from __future__ import annotations
import logging
import threading
from typing import Any, Protocol

from deskmate.session import TRIGGER_IDLE, TRIGGER_SLEEP, SESSION_MANAGER, TRIGGER_SHUTDOWN, InsightSessionManager
from deskmate.settings import load_settings


logger = logging.getLogger(__name__)

# --- tuning constants -----------------------------------------------------------
IDLE_POLL_INTERVAL_S = 2.0


def idle_timeout_label(timeout_s: float) -> str:
    """Human label for the note: whole minutes as ``10분``, anything shorter as ``30초``."""
    minutes = timeout_s / 60.0
    if minutes >= 1 and float(minutes).is_integer():
        return f"{int(minutes)}분"
    return f"{timeout_s:g}초"


class _ActivitySource(Protocol):
    def add_activity_observer(self, observer: Any) -> None: ...


class DeskmateSessionHooks:
    """Heartbeat + auto-close glue between the conversation app and the insight session."""

    def __init__(
        self,
        manager: InsightSessionManager = SESSION_MANAGER,
        *,
        idle_timeout_min: float,
        poll_interval_s: float = IDLE_POLL_INTERVAL_S,
    ) -> None:
        """Hold the manager and the idle timeout (minutes, from ``DESKMATE_INSIGHT_IDLE_TIMEOUT_MIN``)."""
        self._manager = manager
        self._idle_timeout_s = max(idle_timeout_min, 0.0) * 60.0
        self._poll_interval_s = poll_interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def idle_timeout_s(self) -> float:
        """Idle timeout in seconds (0 disables the watchdog)."""
        return self._idle_timeout_s

    # --- hooks --------------------------------------------------------------------------
    def on_activity(self, reason: str) -> None:
        """Activity observer: any user/assistant/tool activity keeps the session alive."""
        self._manager.heartbeat()

    def on_sleep(self) -> None:
        """Sleep hook: close the session before the robot goes to sleep (any sleep path)."""
        self._manager.auto_finish(TRIGGER_SLEEP)

    def on_shutdown(self) -> None:
        """Shutdown hook: stop the watchdog and close the session."""
        self.stop()
        self._manager.auto_finish(TRIGGER_SHUTDOWN)

    def check_idle(self) -> bool:
        """Close the session when idle for the timeout; return whether it was closed (used by the watchdog)."""
        if self._idle_timeout_s <= 0:
            return False
        trigger = f"{TRIGGER_IDLE} {idle_timeout_label(self._idle_timeout_s)}"
        return self._manager.auto_finish(trigger, idle_timeout_s=self._idle_timeout_s) is not None

    # --- watchdog ---------------------------------------------------------------------
    def start(self) -> None:
        """Start the idle watchdog thread (no-op when the timeout is 0 or already running)."""
        if self._idle_timeout_s <= 0 or self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._poll, name="deskmate-idle-watchdog", daemon=True)
        self._thread.start()
        logger.info("DeskMate insight idle watchdog started: %.1f min.", self._idle_timeout_s / 60.0)

    def stop(self) -> None:
        """Stop the watchdog thread."""
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=self._poll_interval_s * 2)
        self._thread = None

    def _poll(self) -> None:
        while not self._stop.wait(self._poll_interval_s):
            try:
                self.check_idle()
            except Exception:
                logger.exception("DeskMate idle watchdog failed (continuing)")


def install_deskmate_hooks(stream_manager: _ActivitySource, logger_: logging.Logger) -> DeskmateSessionHooks:
    """Create the hooks, attach the activity observer to the stream and start the watchdog."""
    try:
        timeout_min: float = load_settings().insight_idle_timeout_min
    except Exception as exc:  # settings must never break app startup
        logger_.warning("DeskMate settings unreadable (%s); idle auto-close disabled.", exc)
        timeout_min = 0.0
    hooks = DeskmateSessionHooks(idle_timeout_min=timeout_min)
    stream_manager.add_activity_observer(hooks.on_activity)
    hooks.start()
    return hooks
