import asyncio

import numpy as np
import pytest

from reachy_mini_conversation_app.streaming import (
    AdditionalOutputs,
    wait_for_item,
    audio_to_int16,
    audio_to_float32,
)


def test_additional_outputs_stores_messages() -> None:
    """Additional outputs should keep the emitted role/content payloads."""
    message = {"role": "assistant", "content": "hello"}

    outputs = AdditionalOutputs(message)

    assert outputs.args == (message,)


@pytest.mark.asyncio
async def test_wait_for_item_returns_none_on_timeout() -> None:
    """Queue waits should time out without raising."""
    queue: asyncio.Queue[int] = asyncio.Queue()

    assert await wait_for_item(queue, timeout=0.01) is None


def test_audio_to_int16_scales_float32() -> None:
    """Float audio should scale into the int16 sample range."""
    audio = np.array([-1.0, 0.0, 1.0], dtype=np.float32)

    np.testing.assert_array_equal(audio_to_int16(audio), np.array([-32767, 0, 32767], dtype=np.int16))


def test_audio_to_float32_scales_int16() -> None:
    """Int16 audio should scale into the float sample range."""
    audio = np.array([-32768, 0, 32767], dtype=np.int16)

    np.testing.assert_allclose(audio_to_float32(audio), np.array([-1.0, 0.0, 32767 / 32768], dtype=np.float32))


def test_audio_converters_reject_unsupported_dtype() -> None:
    """Unsupported audio dtypes should fail explicitly."""
    audio = np.array([1.0], dtype=np.float64)

    with pytest.raises(TypeError, match="Unsupported audio data type"):
        audio_to_int16(audio)


def test_audio_to_int16_clamps_overflow() -> None:
    """Out-of-range float audio should clamp safely instead of integer overflow."""
    audio = np.array([-2.5, 2.5], dtype=np.float32)

    np.testing.assert_array_equal(audio_to_int16(audio), np.array([-32767, 32767], dtype=np.int16))


def test_normalize_audio_frame_levels_loud_audio() -> None:
    """Loud audio exceeding target peak should be scaled down to target peak."""
    from reachy_mini_conversation_app.streaming import normalize_audio_frame

    loud = np.array([-1.4, 0.0, 1.4], dtype=np.float32)
    normalized = normalize_audio_frame(loud, target_peak=0.70)

    assert np.isclose(np.max(np.abs(normalized)), 0.70)
    assert np.all(normalized <= 1.0)
    assert np.all(normalized >= -1.0)


def test_normalize_audio_frame_preserves_quiet_audio() -> None:
    """Audio below target peak should be preserved without gain amplification."""
    from reachy_mini_conversation_app.streaming import normalize_audio_frame

    quiet = np.array([-0.3, 0.0, 0.4], dtype=np.float32)
    normalized = normalize_audio_frame(quiet, target_peak=0.70)

    np.testing.assert_array_equal(normalized, quiet)
