"""
Transcript assembly for Meetly.

This module combines live transcription results with speaker
diarization results and maintains a clean, AI-ready transcript.

Responsibilities
----------------
This module:

    - receives TranscriptChunk objects
    - receives SpeakerSegment objects
    - aligns transcript chunks with speaker segments
    - handles partial/live hypotheses
    - commits only final transcript text
    - resolves speaker IDs to participant names when available
    - exposes a clean plain-text transcript

This module does NOT:

    - perform speech-to-text
    - perform diarization
    - identify voices
    - call an AI model
    - generate summaries

Those responsibilities belong to other layers.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import AsyncIterator, Callable, List, Optional, Sequence

from ..diarization.diarizer import align_speaker_segments
from ..diarization.identity import (
    ResolvedSpeaker,
    SpeakerIdentityResolver,
)
from ...recorder.models import SpeakerSegment, TranscriptChunk

logger = logging.getLogger(__name__)


TranscriptCallback = Callable[
    ["AssembledTranscript"],
    None,
]


@dataclass(frozen=True, slots=True)
class AssembledTranscript:
    """
    A finalized transcript entry.

    Attributes:
        text:
            Final spoken text.

        start_time:
            Start time in seconds.

        end_time:
            End time in seconds.

        speaker_id:
            Anonymous diarization ID, if available.

        speaker_name:
            Resolved participant name, if available.
    """

    text: str
    start_time: float
    end_time: float

    speaker_id: Optional[str] = None
    speaker_name: Optional[str] = None

    @property
    def display_speaker(self) -> Optional[str]:
        """
        Return the best available speaker label.
        """

        return (
            self.speaker_name
            or self.speaker_id
        )


class TranscriptAssembler:
    """
    Maintains the final AI-ready meeting transcript.

    Live flow:

        TranscriptChunk(is_final=False)
                    ↓
              current partial
                    ↓
              UI/live consumer

        TranscriptChunk(is_final=True)
                    +
              SpeakerSegment
                    ↓
              AssembledTranscript
                    ↓
              final transcript

    Partial results are replaceable hypotheses and are never appended
    permanently to the final transcript.
    """

    def __init__(
        self,
        *,
        identity_resolver: Optional[
            SpeakerIdentityResolver
        ] = None,
        max_speaker_gap_seconds: float = 1.0,
        result_queue_maxsize: int = 100,
    ) -> None:
        """
        Initialize the transcript assembler.

        Args:
            identity_resolver:
                Optional resolver for converting anonymous speaker IDs
                into participant names.

            max_speaker_gap_seconds:
                Maximum temporal gap allowed when associating a
                transcript chunk with a speaker segment.

            result_queue_maxsize:
                Maximum number of finalized transcript entries waiting
                to be consumed.
        """

        if max_speaker_gap_seconds < 0:
            raise ValueError(
                "max_speaker_gap_seconds cannot be negative."
            )

        if result_queue_maxsize < 0:
            raise ValueError(
                "result_queue_maxsize cannot be negative."
            )

        self._identity_resolver = identity_resolver

        self._max_speaker_gap_seconds = (
            max_speaker_gap_seconds
        )

        self._results: asyncio.Queue[
            Optional[AssembledTranscript]
        ] = asyncio.Queue(
            maxsize=result_queue_maxsize
        )

        self._callbacks: List[
            TranscriptCallback
        ] = []

        self._speaker_segments: List[
            SpeakerSegment
        ] = []

        self._entries: List[
            AssembledTranscript
        ] = []

        self._partial: Optional[
            TranscriptChunk
        ] = None

        self._running = False

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def running(self) -> bool:
        """Return whether the assembler is active."""

        return self._running

    @property
    def partial_text(self) -> str:
        """
        Return the latest live partial transcript.

        This text is NOT part of the finalized transcript.
        """

        if self._partial is None:
            return ""

        return self._partial.text

    @property
    def entries(
        self,
    ) -> Sequence[AssembledTranscript]:
        """
        Return finalized transcript entries.

        A tuple is returned so callers cannot accidentally mutate
        internal state.
        """

        return tuple(self._entries)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the transcript assembler."""

        self._running = True

    async def stop(self) -> None:
        """
        Stop the assembler.

        Any currently stored partial hypothesis is discarded because
        it was never finalized by the STT engine.
        """

        self._running = False
        self._partial = None

        await self._results.put(None)

    # ------------------------------------------------------------------
    # Speaker input
    # ------------------------------------------------------------------

    def add_speaker_segment(
        self,
        segment: SpeakerSegment,
    ) -> None:
        """
        Add a diarization result to the speaker timeline.

        Speaker segments are kept sorted by start time.
        """

        self._speaker_segments.append(
            segment
        )

        self._speaker_segments.sort(
            key=lambda item: (
                item.start_time,
                item.end_time,
            )
        )

        # Keep only a bounded history.
        #
        # Old speaker segments are no longer needed once they are far
        # behind the latest transcript timeline.
        if len(self._speaker_segments) > 1000:
            self._speaker_segments = (
                self._speaker_segments[-1000:]
            )

    # ------------------------------------------------------------------
    # Transcript input
    # ------------------------------------------------------------------

    async def add_transcript(
        self,
        transcript: TranscriptChunk,
    ) -> Optional[AssembledTranscript]:
        """
        Add a transcription result.

        Partial results replace the current partial hypothesis.

        Final results are committed to the permanent transcript.
        """

        if not self._running:
            raise RuntimeError(
                "TranscriptAssembler is not running."
            )

        if not transcript.text.strip():
            return None

        if not transcript.is_final:
            self._partial = transcript

            return None

        # Final result.
        self._partial = None

        return await self._commit_final_transcript(
            transcript
        )

    async def _commit_final_transcript(
        self,
        transcript: TranscriptChunk,
    ) -> Optional[AssembledTranscript]:
        """
        Convert one final TranscriptChunk into a permanent
        AssembledTranscript entry.
        """

        speaker = align_speaker_segments(
            transcript,
            self._speaker_segments,
            max_gap_seconds=(
                self._max_speaker_gap_seconds
            ),
        )

        speaker_id: Optional[str] = None
        speaker_name: Optional[str] = None

        if speaker is not None:

            speaker_id = speaker.speaker_id

            if self._identity_resolver is not None:

                try:
                    resolved = (
                        await self._identity_resolver.resolve(
                            speaker_id
                        )
                    )

                except Exception:
                    logger.exception(
                        "Speaker identity resolution failed "
                        "for '%s'.",
                        speaker_id,
                    )

                else:

                    if resolved is not None:
                        speaker_name = (
                            resolved.name
                        )

        entry = AssembledTranscript(
            text=transcript.text.strip(),
            start_time=transcript.start_time,
            end_time=transcript.end_time,
            speaker_id=speaker_id,
            speaker_name=speaker_name,
        )

        self._entries.append(
            entry
        )

        await self._dispatch_result(
            entry
        )

        return entry

    # ------------------------------------------------------------------
    # Final transcript
    # ------------------------------------------------------------------

    def get_text(
        self,
        *,
        include_speakers: bool = True,
    ) -> str:
        """
        Return the finalized transcript as plain text.

        Example:

            Rohit: We should launch this by Friday.
            Rahul: I think the backend needs testing.

        If no speaker identity is available:

            SPEAKER_00: We should launch this.
        """

        lines: List[str] = []

        for entry in self._entries:

            if (
                include_speakers
                and entry.display_speaker
            ):
                lines.append(
                    f"{entry.display_speaker}: "
                    f"{entry.text}"
                )

            else:
                lines.append(
                    entry.text
                )

        return "\n".join(lines)

    def clear(self) -> None:
        """
        Clear the current meeting transcript and speaker timeline.
        """

        self._speaker_segments.clear()
        self._entries.clear()

        self._partial = None

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------

    def add_callback(
        self,
        callback: TranscriptCallback,
    ) -> None:
        """
        Register a callback for finalized transcript entries.

        Partial hypotheses are intentionally not sent through this
        callback because they are not permanent transcript entries.
        """

        if not callable(callback):
            raise TypeError(
                "callback must be callable."
            )

        if callback not in self._callbacks:
            self._callbacks.append(
                callback
            )

    def remove_callback(
        self,
        callback: TranscriptCallback,
    ) -> None:
        """Remove a registered callback."""

        try:
            self._callbacks.remove(
                callback
            )

        except ValueError as exc:
            raise ValueError(
                "Callback is not registered."
            ) from exc

    async def _dispatch_result(
        self,
        result: AssembledTranscript,
    ) -> None:
        """
        Dispatch one finalized transcript entry.
        """

        for callback in list(
            self._callbacks
        ):

            try:
                callback(result)

            except Exception:
                logger.exception(
                    "Transcript callback failed."
                )

        await self._results.put(
            result
        )

    async def stream(
        self,
    ) -> AsyncIterator[
        AssembledTranscript
    ]:
        """
        Yield finalized transcript entries as they become available.
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
    ) -> "TranscriptAssembler":
        """Start the assembler."""

        await self.start()

        return self

    async def __aexit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        """Stop the assembler."""

        await self.stop()


__all__ = [
    "AssembledTranscript",
    "TranscriptAssembler",
]