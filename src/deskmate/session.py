"""Insight-conversation session state machine (§3.3). Implemented in M6.

The tools open a session in ``get_insight`` and close it in
``finish_insight``; the app feeds heartbeats from its activity observer and
closes the session itself on silence / sleep / shutdown (``reason="auto"``).
Only the signature is pinned here so track C can import it.
"""

from __future__ import annotations
import time
import threading
from typing import Literal
from pathlib import Path
from dataclasses import field, dataclass


FinishReason = Literal["explicit", "confirmed", "auto"]


@dataclass
class InsightSession:
    """One open insight conversation."""

    profile: str
    note_path: Path
    started_at: float = field(default_factory=time.monotonic)
    last_activity: float = field(default_factory=time.monotonic)
    asked_to_finish: bool = False  # "마칠까요?" asked once already


class InsightSessionManager:
    """Process-wide holder of the single open insight session (thread-safe)."""

    def __init__(self) -> None:
        """Start with no open session."""
        self._lock = threading.Lock()
        self._session: InsightSession | None = None

    def open(self, profile: str, note_path: Path) -> InsightSession:
        """Start a session, implicitly closing any previous one."""
        with self._lock:
            self._session = InsightSession(profile=profile, note_path=note_path)
            return self._session

    def current(self) -> InsightSession | None:
        """Return the open session, if any."""
        with self._lock:
            return self._session

    def heartbeat(self) -> None:
        """Record user/assistant activity (resets the idle timer)."""
        with self._lock:
            if self._session is not None:
                self._session.last_activity = time.monotonic()

    def close(self) -> InsightSession | None:
        """Close and return the session (caller writes the note section)."""
        with self._lock:
            session, self._session = self._session, None
            return session

    def idle_seconds(self) -> float | None:
        """Seconds since the last heartbeat, or ``None`` when no session is open."""
        with self._lock:
            if self._session is None:
                return None
            return time.monotonic() - self._session.last_activity


SESSION_MANAGER = InsightSessionManager()
