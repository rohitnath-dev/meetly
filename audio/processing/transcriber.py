"""
Live audio transcription pipeline for Meetly.

This module receives AudioChunk objects from the recorder layer and
converts them into TranscriptChunk objects.

The transcription engine itself is intentionally separated from the
pipeline so that different speech-to-text providers can be plugged in
later without changing the recorder or meeting logic.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import AsyncIterator, Callable, List, Optional, Union

from ..recorder.models import AudioChunk, TranscriptChunk

logger = logging.getLogger(__name__)

ResultCallback = Callable[[TranscriptChunk], None]


class TranscriptionError(RuntimeError):
    """Base exception for transcription failures."""


class TranscriberStateError(TranscriptionError):
    """Raised for invalid Transcriber lifecycle usage (e.g. submit after stop)."""


class TranscriptionEngine(ABC):
    """
    Abstract interface for a speech-to-text engine.

    Implementations may use:
        - Whisper
        - faster-whisper
        - cloud speech APIs
        - another local STT model
    """

    @abstractmethod
    async def transcribe(
        self,
        audio: AudioChunk,
    ) -> Optional[TranscriptChunk]:
        """
        Transcribe (or buffer) one audio chunk.

        Args:
            audio:
                AudioChunk containing raw audio data.

        Returns:
            A TranscriptChunk once enough audio has been processed to
            produce a result, otherwise None (e.g. still buffering).
        """
        raise NotImplementedError


class Transcriber:
    """
    Coordinates live audio transcription.

    Audio flow:

        AudioChunk
            -> input queue
            -> TranscriptionEngine
            -> TranscriptChunk
            -> result queue -> stream()
                             -> callbacks

    Usage:

        transcriber = Transcriber(engine=whisper)
        await transcriber.start()
        await transcriber.submit(audio_chunk)
        async for transcript in transcriber.stream():
            print(transcript.text)
        await transcriber.stop()
    """

    def __init__(
        self,
        engine: TranscriptionEngine,
        *,
        queue_maxsize: int = 100,
        result_queue_maxsize: int = 100,
    ) -> None:
        """
        Initialize the transcriber.

        Args:
            engine:
                Speech-to-text engine used for transcription.
            queue_maxsize:
                Maximum number of audio chunks waiting for transcription.
                ``0`` means unbounded.
            result_queue_maxsize:
                Maximum number of unread TranscriptChunk results buffered
                for stream() consumers. ``0`` means unbounded.
        """
        if queue_maxsize < 0:
            raise ValueError("queue_maxsize cannot be negative.")
        if result_queue_maxsize < 0:
            raise ValueError("result_queue_maxsize cannot be negative.")

        self._engine = engine

        self._queue: "asyncio.Queue[Optional[AudioChunk]]" = asyncio.Queue(
            maxsize=queue_maxsize
        )
        self._results: "asyncio.Queue[Optional[TranscriptChunk]]" = asyncio.Queue(
            maxsize=result_queue_maxsize
        )

        self._task: Optional[asyncio.Task[None]] = None
        self._running = False
        self._callbacks: List[ResultCallback] = []

    @property
    def running(self) -> bool:
        """Return whether the transcriber is currently running."""
        return self._running

    async def start(self) -> None:
        """Start the live transcription worker. Safe to call once; a repeat
        call while already running is a no-op."""
        if self._running:
            logger.debug("Transcriber.start() called while already running.")
            return

        self._running = True
        self._task = asyncio.create_task(
            self._process_audio(),
            name="meetly-transcription-worker",
        )
        logger.info("Transcriber started.")

    async def stop(self) -> None:
        """
        Stop the transcription worker gracefully.

        Shutdown policy: no new audio is accepted once stop() begins,
        but any audio already queued via submit() is processed to
        completion before the worker exits. Once the worker has
        drained, stream() consumers are signalled to end via a
        sentinel value.

        Idempotent: calling stop() when already stopped is a no-op.
        """
        if not self._running:
            return

        self._running = False
        await self._queue.put(None)

        if self._task is not None:
            try:
                await self._task
            except asyncio.CancelledError:
                raise
            finally:
                self._task = None

        await self._results.put(None)
        logger.info("Transcriber stopped.")

    async def submit(self, audio: AudioChunk) -> None:
        """
        Submit an AudioChunk for transcription.

        This method does not perform transcription itself; it places
        the audio into the processing queue for the background worker.

        Raises:
            TranscriberStateError: If the transcriber is not running.
        """
        if not self._running:
            raise TranscriberStateError(
                "Cannot submit audio while transcriber is stopped."
            )
        await self._queue.put(audio)

    async def transcribe(self, audio: AudioChunk) -> Optional[TranscriptChunk]:
        """
        Transcribe one audio chunk immediately, bypassing the input queue.

        The result (if any) is still dispatched to callbacks and pushed
        onto the result queue so that concurrent stream() consumers see
        it, keeping this path consistent with submit()/stream().

        Raises:
            TranscriptionError: If transcription fails.
        """
        try:
            result = await self._engine.transcribe(audio)
        except Exception as exc:
            logger.exception("Immediate audio transcription failed.")
            raise TranscriptionError("Failed to transcribe audio.") from exc

        if result is not None:
            await self._dispatch_result(result)
        return result

    async def _process_audio(self) -> None:
        """Continuously consume audio chunks and transcribe them. This is
        the main live transcription loop."""
        while True:
            audio = await self._queue.get()
            if audio is None:
                break

            try:
                result = await self._engine.transcribe(audio)
                if result is not None:
                    await self._dispatch_result(result)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Failed to transcribe audio chunk.")

    def add_callback(self, callback: ResultCallback) -> None:
        """
        Register a callback for completed transcript chunks.

        The callback receives a single TranscriptChunk argument and
        must be a synchronous, non-blocking callable.
        """
        if not callable(callback):
            raise TypeError("callback must be callable.")
        self._callbacks.append(callback)

    def remove_callback(self, callback: ResultCallback) -> None:
        """
        Remove a previously registered callback.

        Raises:
            TranscriptionError: If the callback was never registered.
        """
        try:
            self._callbacks.remove(callback)
        except ValueError as exc:
            raise TranscriptionError("Callback is not registered.") from exc

    async def _dispatch_result(self, result: TranscriptChunk) -> None:
        """Dispatch a transcript result to registered callbacks and push it
        onto the result queue for stream() consumers."""
        for callback in list(self._callbacks):
            try:
                callback(result)
            except Exception:
                logger.exception("Transcription callback failed.")

        await self._results.put(result)

    async def stream(self) -> AsyncIterator[TranscriptChunk]:
        """
        Yield transcript results as they become available.

        Ends once stop() has fully drained the worker and signalled
        the result queue's sentinel.
        """
        while True:
            result = await self._results.get()
            if result is None:
                break
            yield result

    async def __aenter__(self) -> "Transcriber":
        """Start the transcriber as an async context manager."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        """Stop the transcriber when leaving the context."""
        await self.stop()
