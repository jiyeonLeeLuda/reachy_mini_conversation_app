"""M6: DeskMate app hooks — activity heartbeat fan-out and auto-close on idle / sleep / shutdown."""

import time
import shutil
import asyncio
import logging
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from deskmate.session import InsightSessionManager
from reachy_mini_conversation_app.console import LocalStream
from reachy_mini_conversation_app.deskmate_hooks import (
    DeskmateSessionHooks,
    idle_timeout_label,
    install_deskmate_hooks,
)


FIXTURE_NOTE = Path(__file__).parent / "deskmate" / "fixtures" / "repo_sample" / "insights"


@pytest.fixture
def note(tmp_path: Path) -> Path:
    """Writable copy of the fixture insight note."""
    source = next(FIXTURE_NOTE.rglob("*.md"))
    target = tmp_path / source.name
    shutil.copy(source, target)
    return target


def _stream() -> LocalStream:
    handler = MagicMock()
    handler.output_queue = asyncio.Queue()
    robot = SimpleNamespace(media=SimpleNamespace(audio=SimpleNamespace(clear_player=MagicMock())))
    return LocalStream(handler, robot)


def test_on_activity_is_a_heartbeat(note: Path) -> None:
    """Any activity reason resets the session idle timer."""
    manager = InsightSessionManager()
    session = manager.open("Default", note)
    session.last_activity -= 100
    DeskmateSessionHooks(manager, idle_timeout_min=10).on_activity("user_speech_started")
    assert (manager.idle_seconds() or 0) < 1


def test_on_sleep_and_on_shutdown_auto_close(note: Path) -> None:
    """Sleep and shutdown both close the session and mark the note with their trigger."""
    manager = InsightSessionManager()
    hooks = DeskmateSessionHooks(manager, idle_timeout_min=10)
    manager.open("Default", note)
    hooks.on_sleep()
    assert manager.current() is None and "자동 종료: 슬립 전환" in note.read_text(encoding="utf-8")
    manager.open("Default", note)
    hooks.on_shutdown()
    assert manager.current() is None and "자동 종료: 앱 종료" in note.read_text(encoding="utf-8")


def test_check_idle_disabled_with_zero_timeout(note: Path) -> None:
    """A 0-minute timeout disables the idle close and the watchdog thread."""
    manager = InsightSessionManager()
    hooks = DeskmateSessionHooks(manager, idle_timeout_min=0)
    session = manager.open("Default", note)
    session.last_activity -= 10_000
    assert hooks.check_idle() is False and manager.current() is session
    hooks.start()
    assert hooks._thread is None


def test_watchdog_closes_idle_session(note: Path) -> None:
    """The watchdog thread closes a session idle past the timeout without any LLM involvement."""
    manager = InsightSessionManager()
    hooks = DeskmateSessionHooks(manager, idle_timeout_min=1 / 60, poll_interval_s=0.01)
    session = manager.open("Default", note)
    session.last_activity -= 5
    hooks.start()
    try:
        deadline = time.monotonic() + 2.0
        while manager.current() is not None and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        hooks.stop()
    assert manager.current() is None and hooks._thread is None
    assert "자동 종료: 무응답 1초" in note.read_text(encoding="utf-8")


def test_local_stream_fans_activity_out_to_extra_observers() -> None:
    """Registered observers all receive the reason; one raising does not stop the others."""
    stream = _stream()
    seen: list[str] = []

    def bad(_reason: str) -> None:
        raise RuntimeError("boom")

    stream.add_activity_observer(bad)
    stream.add_activity_observer(seen.append)
    stream.add_activity_observer(lambda reason: seen.append(reason.upper()))
    stream._dispatch_activity("say")
    assert seen == ["say", "SAY"]


def test_install_registers_observer_without_thread_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Installing wires the observer into the stream; a 0 timeout starts no watchdog."""
    monkeypatch.setenv("DESKMATE_INSIGHT_IDLE_TIMEOUT_MIN", "0")
    stream = _stream()
    hooks = install_deskmate_hooks(stream, logging.getLogger("test"))
    assert hooks.idle_timeout_s == 0 and hooks._thread is None
    assert hooks.on_activity in stream._extra_activity_observers


@pytest.mark.parametrize(("seconds", "label"), [(600, "10분"), (60, "1분"), (90, "90초"), (1, "1초")])
def test_idle_timeout_label(seconds: float, label: str) -> None:
    """Whole minutes read as 분, anything else as 초."""
    assert idle_timeout_label(seconds) == label
