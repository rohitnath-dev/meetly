"""
Live transcription coordinator for Meetly.

This module receives AudioChunk objects from the recorder layer,
passes them to a TranscriptionEngine, and exposes TranscriptChunk
results through callbacks and an asynchronous result stream.

The coordinator is intentionally independent of the concrete STT
provider. Whisper, faster-whisper, or another provider can implement
TranscriptionEngine without changing this layer.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import AsyncIterator, Callable, List, Optional

from ..recorder.models import AudioChunk, TranscriptChunk

logger = logging.getLogger(__name__)


ResultCallback = Callable[[TranscriptChunk], None]


class TranscriptionError(RuntimeError):
    """Base exception for transcription failures."""


class TranscriberStateError(TranscriptionError):
    """Raised when the transcriber is used in an invalid state."""


class TranscriptionEngine(ABC):
    """
    Abstract interface for a speech-to-text engine.

    The engine receives audio chunks and returns the latest available
    transcription hypothesis.

    A returned TranscriptChunk may be:

        is_final=False
            Current partial/live hypothesis.

        is_final=True
            Finalized transcript text.
    """

    @abstractmethod
    async def transcribe(
        self,
        audio: AudioChunk,
    ) -> Optional[TranscriptChunk]:
        """
        Process one audio chunk.

        The implementation may buffer audio internally.

        Returns:
            The latest available transcript result, or None when
            there is not enough new audio to produce one.
        """
        raise NotImplementedError


class Transcriber:
    """
    Coordinates live audio transcription.

    Pipeline:

        AudioChunk
            ↓
        input queue
            ↓
        TranscriptionEngine
            ↓
        TranscriptChunk
            ↓
        result queue
            ↓
        stream() / callbacks

    Partial results are intentionally delivered to consumers.

    Consumers should replace their current partial hypothesis when
    receiving is_final=False instead of permanently appending it.
    Final results can be committed to the meeting transcript.
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
                Speech-to-text engine.

            queue_maxsize:
                Maximum number of pending audio chunks.
                0 means unlimited.

            result_queue_maxsize:
                Maximum number of unread transcript results.
                0 means unlimited.
        """

        if queue_maxsize < 0:
            raise ValueError(
                "queue_maxsize cannot be negative."
            )

        if result_queue_maxsize < 0:
            raise ValueError(
                "result_queue_maxsize cannot be negative."
            )

        self._engine = engine

        self._queue: asyncio.Queue[
            Optional[AudioChunk]
        ] = asyncio.Queue(
            maxsize=queue_maxsize
        )

        self._results: asyncio.Queue[
            Optional[TranscriptChunk]
        ] = asyncio.Queue(
            maxsize=result_queue_maxsize
        )

        self._task: Optional[
            asyncio.Task[None]
        ] = None

        self._running = False
        self._stopping = False

        self._callbacks: List[
            ResultCallback
        ] = []

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def running(self) -> bool:
        """Return whether the transcription worker is running."""

        return self._running

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """
        Start the background transcription worker.

        Calling start() while already running is a no-op.
        """

        if self._running:
            return

        self._running = True
        self._stopping = False

        self._task = asyncio.create_task(
            self._process_audio(),
            name="meetly-transcription-worker",
        )

        logger.info("Transcriber started.")

    async def stop(self) -> None:
        """
        Stop the transcription worker gracefully.

        Already queued audio is processed before the worker exits.

        Once the worker has completely stopped, the result stream
        receives a sentinel and terminates.
        """

        if not self._running:
            return

        self._stopping = True
        self._running = False

        # Sentinel is processed after everything already in the queue.
        await self._queue.put(None)

        if self._task is not None:
            try:
                await self._task
            except asyncio.CancelledError:
                raise
            finally:
                self._task = None

        await self._results.put(None)

        self._stopping = False

        logger.info("Transcriber stopped.")

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    async def submit(
        self,
        audio: AudioChunk,
    ) -> None:
        """
        Submit an audio chunk for live transcription.

        Raises:
            TranscriberStateError:
                If the transcriber is not running.
        """

        if not self._running or self._stopping:
            raise TranscriberStateError(
                "Cannot submit audio while "
                "transcriber is stopped."
            )

        await self._queue.put(audio)

    # ------------------------------------------------------------------
    # Direct transcription
    # ------------------------------------------------------------------

    async def transcribe(
        self,
        audio: AudioChunk,
    ) -> Optional[TranscriptChunk]:
        """
        Process one AudioChunk immediately.

        This bypasses the background input queue but still publishes
        any resulting TranscriptChunk through callbacks and stream().
        """

        try:
            result = await self._engine.transcribe(audio)

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            logger.exception(
                "Immediate transcription failed."
            )

            raise TranscriptionError(
                "Failed to transcribe audio."
            ) from exc

        if result is not None:
            await self._dispatch_result(result)

        return result

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    async def _process_audio(self) -> None:
        """
        Continuously process queued audio chunks.

        Processing is strictly sequential so that audio order is
        preserved.
        """

        while True:

            audio = await self._queue.get()

            if audio is None:
                break

            try:
                result = await self._engine.transcribe(
                    audio
                )

                if result is not None:
                    await self._dispatch_result(
                        result
                    )

            except asyncio.CancelledError:
                raise

            except Exception:
                # A failed chunk should not kill the entire live
                # transcription worker.
                logger.exception(
                    "Failed to transcribe audio chunk."
                )

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------

    def add_callback(
        self,
        callback: ResultCallback,
    ) -> None:
        """
        Register a callback for transcript results.

        The callback must be synchronous and non-blocking.

        Both partial and final TranscriptChunk objects are delivered.
        """

        if not callable(callback):
            raise TypeError(
                "callback must be callable."
            )

        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def remove_callback(
        self,
        callback: ResultCallback,
    ) -> None:
        """
        Remove a previously registered callback.
        """

        try:
            self._callbacks.remove(callback)

        except ValueError as exc:
            raise TranscriptionError(
                "Callback is not registered."
            ) from exc

    async def _dispatch_result(
        self,
        result: TranscriptChunk,
    ) -> None:
        """
        Publish one transcript result.

        The result is sent to callbacks and then placed into the
        asynchronous result queue.

        Partial results are NOT filtered or discarded.
        """

        for callback in list(self._callbacks):

            try:
                callback(result)

            except Exception:
                logger.exception(
                    "Transcription callback failed."
                )

        await self._results.put(result)

    async def stream(
        self,
    ) -> AsyncIterator[TranscriptChunk]:
        """
        Yield transcript results as they become available.

        Both partial and final results are yielded.

        Example:

            async for result in transcriber.stream():
                if result.is_final:
                    commit(result.text)
                else:
                    update_live_text(result.text)
        """

        while True:

            result = await self._results.get()

            if result is None:
                break

            yield result

    # ------------------------------------------------------------------
    # Async context manager
    # ------------------------------------------------------------------

    async def __aenter__(
        self,
    ) -> "Transcriber":
        """Start the transcriber when entering an async context."""

        await self.start()

        return self

    async def __aexit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        """Stop the transcriber when leaving an async context."""

        await self.stop()


__all__ = [
    "TranscriptionError",
    "TranscriberStateError",
    "TranscriptionEngine",
    "Transcriber",
]