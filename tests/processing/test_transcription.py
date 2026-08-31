"""
Tests for Meetly live transcription.

These tests use fake engines and mocked Whisper inference.
No real microphone or Whisper model is required.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from meetly.audio.recorder.models import (
    AudioChunk,
    AudioFormat,
    TranscriptChunk,
)
from meetly.audio.processing.live_transcription.transcriber import (
    Transcriber,
    TranscriberStateError,
    TranscriptionEngine,
    TranscriptionError,
)
from meetly.audio.processing.live_transcription.whisper import (
    InvalidAudioFormatError,
    WhisperEngine,
)


def make_chunk(
    source: str = "mic",
    data: bytes = b"\x00\x00",
) -> AudioChunk:
    return AudioChunk(
        data=data,
        sample_rate=16000,
        channels=1,
        format=AudioFormat.PCM16,
        timestamp=datetime.utcnow(),
        source=source,
    )


class FakeTranscriptionEngine(TranscriptionEngine):
    """Small deterministic engine for testing Transcriber."""

    def __init__(
        self,
        emit_every: int = 1,
        fail_on: int | None = None,
    ) -> None:
        self.calls = 0
        self.emit_every = emit_every
        self.fail_on = fail_on

    async def transcribe(
        self,
        audio: AudioChunk,
    ) -> TranscriptChunk | None:
        self.calls += 1

        if (
            self.fail_on is not None
            and self.calls == self.fail_on
        ):
            raise RuntimeError(
                "synthetic engine failure"
            )

        if self.calls % self.emit_every != 0:
            return None

        return TranscriptChunk(
            text=f"text-{self.calls}",
            start_time=0.0,
            end_time=1.0,
            is_final=True,
        )


# ------------------------------------------------------------------
# TranscriptionEngine
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_engine_can_return_none_or_transcript():
    engine = FakeTranscriptionEngine(
        emit_every=2
    )

    assert await engine.transcribe(
        make_chunk()
    ) is None

    result = await engine.transcribe(
        make_chunk()
    )

    assert isinstance(
        result,
        TranscriptChunk,
    )

    assert result.text == "text-2"


# ------------------------------------------------------------------
# Transcriber state
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_before_start_raises():
    transcriber = Transcriber(
        engine=FakeTranscriptionEngine()
    )

    with pytest.raises(TranscriberStateError):
        await transcriber.submit(
            make_chunk()
        )


@pytest.mark.asyncio
async def test_start_stop_is_idempotent():
    transcriber = Transcriber(
        engine=FakeTranscriptionEngine()
    )

    await transcriber.start()
    await transcriber.start()

    assert transcriber.running

    await transcriber.stop()
    await transcriber.stop()

    assert not transcriber.running


# ------------------------------------------------------------------
# Streaming
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_returns_transcription_results():
    transcriber = Transcriber(
        engine=FakeTranscriptionEngine()
    )

    await transcriber.start()

    received: list[str] = []

    async def consume() -> None:
        async for result in transcriber.stream():
            received.append(result.text)

    consumer = asyncio.create_task(
        consume()
    )

    await transcriber.submit(
        make_chunk()
    )

    await transcriber.submit(
        make_chunk()
    )

    await asyncio.sleep(0.05)

    await transcriber.stop()
    await consumer

    assert received == [
        "text-1",
        "text-2",
    ]


# ------------------------------------------------------------------
# Callbacks
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_callback_receives_result():
    transcriber = Transcriber(
        engine=FakeTranscriptionEngine()
    )

    received: list[TranscriptChunk] = []

    transcriber.add_callback(
        received.append
    )

    await transcriber.start()

    await transcriber.submit(
        make_chunk()
    )

    await asyncio.sleep(0.05)

    await transcriber.stop()

    assert len(received) == 1
    assert received[0].text == "text-1"


# ------------------------------------------------------------------
# Worker error handling
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worker_continues_after_engine_error():
    engine = FakeTranscriptionEngine(
        fail_on=1
    )

    transcriber = Transcriber(
        engine=engine
    )

    received: list[TranscriptChunk] = []

    transcriber.add_callback(
        received.append
    )

    await transcriber.start()

    await transcriber.submit(
        make_chunk()
    )

    await transcriber.submit(
        make_chunk()
    )

    await asyncio.sleep(0.05)

    await transcriber.stop()

    assert len(received) == 1
    assert received[0].text == "text-2"


@pytest.mark.asyncio
async def test_direct_transcribe_wraps_engine_error():
    class BrokenEngine(
        TranscriptionEngine
    ):
        async def transcribe(
            self,
            audio: AudioChunk,
        ) -> TranscriptChunk:
            raise ValueError("boom")

    transcriber = Transcriber(
        engine=BrokenEngine()
    )

    with pytest.raises(TranscriptionError):
        await transcriber.transcribe(
            make_chunk()
        )


# ------------------------------------------------------------------
# WhisperEngine
# ------------------------------------------------------------------


class FakeWhisperSegment:
    def __init__(
        self,
        text: str,
        avg_logprob: float = -0.3,
    ) -> None:
        self.text = text
        self.avg_logprob = avg_logprob


@pytest.mark.asyncio
async def test_whisper_engine_buffers_before_inference():
    engine = WhisperEngine(
        sample_rate=16000,
        channels=1,
        inference_window_seconds=0.5,
        minimum_audio_seconds=0.2,
        context_seconds=1.0,
        inference_interval_seconds=0.1,
        stability_passes=1,
    )

    engine._model = MagicMock()

    engine._model.transcribe.return_value = (
        [FakeWhisperSegment("hello")],
        None,
    )

    chunk = make_chunk(
        data=b"\x00\x00" * 1600
    )

    result = None

    for _ in range(4):
        result = await engine.transcribe(
            chunk
        )

    assert result is None

    result = await engine.transcribe(
        chunk
    )

    assert isinstance(
        result,
        TranscriptChunk,
    )

    assert result.text == "hello"


@pytest.mark.asyncio
async def test_whisper_engine_rejects_wrong_sample_rate():
    engine = WhisperEngine(
        sample_rate=16000,
        channels=1,
        inference_window_seconds=0.5,
        minimum_audio_seconds=0.2,
        context_seconds=1.0,
        inference_interval_seconds=0.1,
        stability_passes=1,
    )

    bad_chunk = AudioChunk(
        data=b"\x00\x00",
        sample_rate=44100,
        channels=1,
        format=AudioFormat.PCM16,
        timestamp=datetime.utcnow(),
        source="mic",
    )

    with pytest.raises(
        InvalidAudioFormatError
    ):
        await engine.transcribe(
            bad_chunk
        )