"""
Live speaker diarization for Meetly.

This module identifies distinct speakers in an incoming AudioChunk
stream and produces timestamped SpeakerSegment objects.

Architecture
------------
AudioChunk
    ↓
DiarizationEngine
    ↓
SpeakerSegment
    ↓
Diarizer
    ↓
callbacks / stream()

The concrete diarization algorithm is deliberately separated from
Diarizer so external applications can use the public API without
depending on a particular implementation.

Speaker identity
----------------
Diarization answers:

    "Which audio segments belong to the same speaker?"

It does NOT inherently answer:

    "Who is this person?"

The latter is handled by the identity layer.

Therefore speaker IDs such as:

    SPEAKER_00
    SPEAKER_01

remain valid even when no participant name can be resolved.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import (
    AsyncIterator,
    Callable,
    List,
    Optional,
    Sequence,
)

from ...recorder.models import (
    AudioChunk,
    AudioFormat,
    SpeakerSegment,
    TranscriptChunk,
)


logger = logging.getLogger(__name__)

SpeakerCallback = Callable[[SpeakerSegment], None]


class DiarizationError(RuntimeError):
    """Base exception for diarization failures."""


class DiarizerStateError(DiarizationError):
    """Raised when the diarizer is used in an invalid state."""


class UnsupportedAudioFormatError(DiarizationError):
    """Raised when the input audio format is unsupported."""


class DiarizationEngine(ABC):
    """
    Abstract interface for a speaker-diarization backend.

    Implementations receive AudioChunk objects and return zero or more
    SpeakerSegment objects.

    The implementation may buffer audio internally before producing
    a segment.

    External applications should depend on this interface rather than
    a concrete diarization implementation.
    """

    @abstractmethod
    async def diarize(
        self,
        audio: AudioChunk,
    ) -> List[SpeakerSegment]:
        """
        Process one audio chunk.

        Args:
            audio:
                Raw audio received from the recorder layer.

        Returns:
            Zero or more speaker segments generated from the
            currently available audio.
        """
        raise NotImplementedError

    async def flush(self) -> List[SpeakerSegment]:
        """
        Flush any internally buffered audio.

        Engines that do not maintain buffered audio may simply return
        an empty list.
        """

        return []


class Diarizer:
    """
    Coordinates live speaker diarization.

    The Diarizer is intentionally independent of the actual
    diarization algorithm.

    Pipeline:

        AudioChunk
            ↓
        input queue
            ↓
        DiarizationEngine
            ↓
        SpeakerSegment
            ↓
        result queue
            ↓
        stream() / callbacks

    This class is suitable for use by Meetly itself or by external
    applications importing the diarization package.
    """

    def __init__(
        self,
        engine: DiarizationEngine,
        *,
        queue_maxsize: int = 100,
        result_queue_maxsize: int = 100,
    ) -> None:
        """
        Initialize the diarization coordinator.

        Args:
            engine:
                Concrete diarization engine.

            queue_maxsize:
                Maximum number of pending audio chunks.
                0 means unlimited.

            result_queue_maxsize:
                Maximum number of unread speaker segments.
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
            Optional[SpeakerSegment]
        ] = asyncio.Queue(
            maxsize=result_queue_maxsize
        )

        self._task: Optional[
            asyncio.Task[None]
        ] = None

        self._running = False
        self._stopping = False

        self._callbacks: List[
            SpeakerCallback
        ] = []

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def running(self) -> bool:
        """Return whether the diarizer worker is running."""

        return self._running

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """
        Start the live diarization worker.

        Calling start() while already running is a no-op.
        """

        if self._running:
            return

        self._running = True
        self._stopping = False

        self._task = asyncio.create_task(
            self._process_audio(),
            name="meetly-diarization-worker",
        )

        logger.info("Diarizer started.")

    async def stop(self) -> None:
        """
        Stop the diarizer gracefully.

        Queued audio is processed before the worker exits.

        Buffered audio inside the engine is flushed before shutdown.
        """

        if not self._running:
            return

        self._stopping = True
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

        self._stopping = False

        logger.info("Diarizer stopped.")

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    async def submit(
        self,
        audio: AudioChunk,
    ) -> None:
        """
        Submit an AudioChunk for diarization.

        Raises:
            DiarizerStateError:
                If the diarizer is not running.
        """

        if not self._running or self._stopping:
            raise DiarizerStateError(
                "Cannot submit audio while "
                "diarizer is stopped."
            )

        await self._queue.put(audio)

    # ------------------------------------------------------------------
    # Direct processing
    # ------------------------------------------------------------------

    async def diarize(
        self,
        audio: AudioChunk,
    ) -> List[SpeakerSegment]:
        """
        Process one AudioChunk immediately.

        This bypasses the background queue but still publishes all
        generated SpeakerSegment objects.
        """

        try:
            segments = await self._engine.diarize(
                audio
            )

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            logger.exception(
                "Immediate diarization failed."
            )

            raise DiarizationError(
                "Failed to diarize audio."
            ) from exc

        for segment in segments:
            await self._dispatch_result(segment)

        return segments

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    async def _process_audio(self) -> None:
        """
        Sequentially process queued audio.

        Sequential processing is intentional: audio order must be
        preserved for correct speaker timelines.
        """

        while True:

            audio = await self._queue.get()

            if audio is None:
                break

            try:
                segments = await self._engine.diarize(
                    audio
                )

                for segment in segments:
                    await self._dispatch_result(
                        segment
                    )

            except asyncio.CancelledError:
                raise

            except Exception:
                logger.exception(
                    "Failed to diarize audio chunk."
                )

        # Flush any audio remaining inside the engine.
        try:
            segments = await self._engine.flush()

            for segment in segments:
                await self._dispatch_result(
                    segment
                )

        except asyncio.CancelledError:
            raise

        except Exception:
            logger.exception(
                "Failed to flush diarization engine."
            )

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------

    def add_callback(
        self,
        callback: SpeakerCallback,
    ) -> None:
        """
        Register a callback for speaker segments.

        The callback receives every generated SpeakerSegment.
        """

        if not callable(callback):
            raise TypeError(
                "callback must be callable."
            )

        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def remove_callback(
        self,
        callback: SpeakerCallback,
    ) -> None:
        """
        Remove a previously registered callback.
        """

        try:
            self._callbacks.remove(callback)

        except ValueError as exc:
            raise DiarizationError(
                "Callback is not registered."
            ) from exc

    async def _dispatch_result(
        self,
        segment: SpeakerSegment,
    ) -> None:
        """
        Publish one speaker segment.

        Results are delivered to callbacks and the asynchronous
        result stream.
        """

        for callback in list(self._callbacks):

            try:
                callback(segment)

            except Exception:
                logger.exception(
                    "Diarization callback failed."
                )

        await self._results.put(segment)

    async def stream(
        self,
    ) -> AsyncIterator[SpeakerSegment]:
        """
        Yield speaker segments as they become available.

        Example:

            async for segment in diarizer.stream():
                print(
                    segment.speaker_id,
                    segment.start_time,
                    segment.end_time,
                )
        """

        while True:

            segment = await self._results.get()

            if segment is None:
                break

            yield segment

    # ------------------------------------------------------------------
    # Async context manager
    # ------------------------------------------------------------------

    async def __aenter__(
        self,
    ) -> "Diarizer":
        """Start the diarizer when entering an async context."""

        await self.start()

        return self

    async def __aexit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        """Stop the diarizer when leaving the async context."""

        await self.stop()


def align_speaker_segments(
    transcript: TranscriptChunk,
    speaker_segments: Sequence[SpeakerSegment],
    max_gap_seconds: float = 1.0,
) -> Optional[SpeakerSegment]:
    """
    Find the speaker segment that best matches a transcript chunk.

    The segment with the greatest temporal overlap is preferred.
    If no segment overlaps, the closest segment is returned when its
    temporal gap is within max_gap_seconds.

    Returns:
        The best matching SpeakerSegment, or None if no suitable
        segment exists.
    """

    if not isinstance(transcript, TranscriptChunk):
        raise TypeError(
            "transcript must be a TranscriptChunk."
        )

    if max_gap_seconds < 0:
        raise ValueError(
            "max_gap_seconds must be non-negative."
        )

    if not speaker_segments:
        return None

    transcript_start = transcript.start_time
    transcript_end = transcript.end_time

    best_segment: Optional[SpeakerSegment] = None
    best_overlap = 0.0

    for segment in speaker_segments:
        overlap_start = max(
            transcript_start,
            segment.start_time,
        )
        overlap_end = min(
            transcript_end,
            segment.end_time,
        )

        overlap = max(
            0.0,
            overlap_end - overlap_start,
        )

        if overlap > best_overlap:
            best_overlap = overlap
            best_segment = segment

    if best_segment is not None:
        return best_segment

    closest_segment: Optional[SpeakerSegment] = None
    closest_gap = float("inf")

    for segment in speaker_segments:
        if segment.end_time < transcript_start:
            gap = transcript_start - segment.end_time

        elif segment.start_time > transcript_end:
            gap = segment.start_time - transcript_end

        else:
            gap = 0.0

        if gap < closest_gap:
            closest_gap = gap
            closest_segment = segment

    if (
        closest_segment is not None
        and closest_gap <= max_gap_seconds
    ):
        return closest_segment

    return None


__all__ = [
    "DiarizationEngine",
    "Diarizer",
    "DiarizationError",
    "DiarizerStateError",
    "UnsupportedAudioFormatError",
    "align_speaker_segments",
]