"""
Test strategy and examples for audio.processing.

Run with: pytest -q audio/processing/test_processing.py
(pytest-asyncio required, or convert to asyncio.run() calls manually)

No real microphone or Whisper model is required: Transcriber tests
use a FakeTranscriptionEngine, and WhisperEngine tests mock out the
underlying model so only the buffering/validation/dedup logic is
exercised.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from ..recorder.models import AudioChunk, AudioFormat, TranscriptChunk
from .transcriber import (
    Transcriber,
    TranscriberStateError,
    TranscriptionEngine,
    TranscriptionError,
)
from .whisper import InvalidAudioFormatError, WhisperEngine


def make_chunk(source: str = "mic", data: bytes = b"\x00\x00") -> AudioChunk:
    return AudioChunk(
        data=data,
        sample_rate=16000,
        channels=1,
        format=AudioFormat.PCM16,
        timestamp=datetime.utcnow(),
        source=source,
    )


class FakeTranscriptionEngine(TranscriptionEngine):
    """Minimal engine for exercising Transcriber without real STT."""

    def __init__(self, emit_every: int = 1, fail_on: int | None = None):
        self.calls = 0
        self.emit_every = emit_every
        self.fail_on = fail_on

    async def transcribe(self, audio: AudioChunk):
        self.calls += 1
        if self.fail_on is not None and self.calls == self.fail_on:
            raise RuntimeError("synthetic engine failure")
        if self.calls % self.emit_every != 0:
            return None
        return TranscriptChunk(
            text=f"text-{self.calls}", start_time=0.0, end_time=1.0, is_final=True
        )


# 1. TranscriptionEngine interface -------------------------------------------


@pytest.mark.asyncio
async def test_engine_interface_returns_optional_chunk():
    engine = FakeTranscriptionEngine(emit_every=2)
    assert await engine.transcribe(make_chunk()) is None
    result = await engine.transcribe(make_chunk())
    assert isinstance(result, TranscriptChunk)


# 2. Transcriber queue ---------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_before_start_raises():
    t = Transcriber(engine=FakeTranscriptionEngine())
    with pytest.raises(TranscriberStateError):
        await t.submit(make_chunk())


# 3. Transcriber start/stop -----------------------------------------------------


@pytest.mark.asyncio
async def test_start_stop_lifecycle_is_idempotent():
    t = Transcriber(engine=FakeTranscriptionEngine())
    await t.start()
    await t.start()  # no-op, must not raise
    assert t.running
    await t.stop()
    await t.stop()  # no-op, must not raise
    assert not t.running


# 4. Result streaming -----------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_yields_results_and_ends_after_stop():
    engine = FakeTranscriptionEngine(emit_every=1)
    t = Transcriber(engine=engine)
    await t.start()

    received = []

    async def consume():
        async for chunk in t.stream():
            received.append(chunk.text)

    consumer = asyncio.create_task(consume())
    await t.submit(make_chunk())
    await t.submit(make_chunk())
    await asyncio.sleep(0.05)
    await t.stop()
    await consumer

    assert received == ["text-1", "text-2"]


# 5. Callback delivery ------------------------------------------------------------


@pytest.mark.asyncio
async def test_callback_receives_result():
    engine = FakeTranscriptionEngine(emit_every=1)
    t = Transcriber(engine=engine)
    seen = []
    t.add_callback(seen.append)

    await t.start()
    await t.submit(make_chunk())
    await asyncio.sleep(0.05)
    await t.stop()

    assert len(seen) == 1
    assert seen[0].text == "text-1"


# 6. Fake/mock transcription engine (error propagation) ---------------------------


@pytest.mark.asyncio
async def test_worker_logs_and_continues_after_engine_error():
    engine = FakeTranscriptionEngine(emit_every=1, fail_on=1)
    t = Transcriber(engine=engine)
    seen = []
    t.add_callback(seen.append)

    await t.start()
    await t.submit(make_chunk())  # raises inside engine, worker should survive
    await t.submit(make_chunk())  # this one should succeed
    await asyncio.sleep(0.05)
    await t.stop()

    assert len(seen) == 1
    assert seen[0].text == "text-2"


# 7. WhisperEngine audio conversion / windowing ------------------------------------


class _FakeSegment:
    def __init__(self, text: str, avg_logprob: float = -0.3):
        self.text = text
        self.avg_logprob = avg_logprob


@pytest.mark.asyncio
async def test_whisper_engine_buffers_until_window_full():
    engine = WhisperEngine(
        sample_rate=16000,
        channels=1,
        target_window_seconds=0.5,
        min_duration_seconds=0.2,
        overlap_seconds=0.1,
    )
    engine._model = MagicMock()
    engine._model.transcribe.return_value = ([_FakeSegment("hello")], None)

    small_chunk = make_chunk(data=b"\x00\x00" * 1600)  # 0.1s of audio
    result = None
    for _ in range(4):  # 0.4s buffered, below 0.5s target
        result = await engine.transcribe(small_chunk)
    assert result is None  # still buffering

    result = await engine.transcribe(small_chunk)  # crosses target window
    assert isinstance(result, TranscriptChunk)
    assert result.text == "hello"
    assert result.confidence == pytest.approx(-0.3)


# 8. Error handling -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_whisper_engine_rejects_wrong_sample_rate():
    engine = WhisperEngine(sample_rate=16000, channels=1)
    bad_chunk = AudioChunk(
        data=b"\x00\x00",
        sample_rate=44100,
        channels=1,
        format=AudioFormat.PCM16,
        timestamp=datetime.utcnow(),
        source="mic",
    )
    with pytest.raises(InvalidAudioFormatError):
        await engine.transcribe(bad_chunk)


@pytest.mark.asyncio
async def test_immediate_transcribe_wraps_engine_errors():
    class BrokenEngine(TranscriptionEngine):
        async def transcribe(self, audio):
            raise ValueError("boom")

    t = Transcriber(engine=BrokenEngine())
    with pytest.raises(TranscriptionError):
        await t.transcribe(make_chunk())
