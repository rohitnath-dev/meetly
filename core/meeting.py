from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import TYPE_CHECKING, AsyncIterator, Optional

from meetly.audio.processing.diarization.diarizer import Diarizer
from meetly.audio.processing.transcript.assembler import (
    AssembledTranscript,
    TranscriptAssembler,
)
from meetly.audio.processing.live_transcription.transcriber import Transcriber
from meetly.audio.recorder.models import AudioChunk
from meetly.audio.recorder.backend import RecorderBackend
from meetly.audio.recorder.source import AudioSource
from meetly.audio.processing.ai.summarizer import MeetingSummarizer
from meetly.llm import LLMClient

if TYPE_CHECKING:
    from meetly.audio.processing.ai.qna import MeetingQnA

logger = logging.getLogger(__name__)


class MeetingState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class MeetingStateError(RuntimeError):
    """Raised when a meeting operation is invalid for the current state."""


class Meeting:
    """
    High-level orchestration layer for a Meetly meeting.

    The Meeting class connects recording input with transcription,
    diarization, transcript assembly, and AI features.

    Audio processing:

        AudioChunk
            ├──> Transcriber
            │       └──> TranscriptChunk
            │
            └──> Diarizer
                    └──> SpeakerSegment

        TranscriptChunk + SpeakerSegment
                    ↓
            TranscriptAssembler
                    ↓
            finalized transcript
                    ↓
             AI features
              ├── Summary
              └── RAG Q&A
    """

    def __init__(
        self,
        *,
        transcriber: Transcriber,
        diarizer: Diarizer,
        assembler: TranscriptAssembler,
        llm: LLMClient,
        audio_source: AudioSource | None = None,
        provider: str = "local",
        meeting_url: str | None = None,
    ) -> None:
        self._transcriber = transcriber
        self._diarizer = diarizer
        self._assembler = assembler

        self._summarizer = MeetingSummarizer(llm)
        self._qna_llm = llm
        self._audio_source = audio_source
        self._recorder: RecorderBackend | None = None
        if audio_source is not None:
            self._recorder = RecorderBackend()
            self._recorder.register_source(audio_source)
        self._provider = provider
        self._meeting_url = meeting_url

        self._state = MeetingState.IDLE

        self._transcript_task: Optional[asyncio.Task[None]] = None
        self._speaker_task: Optional[asyncio.Task[None]] = None
        self._audio_task: Optional[asyncio.Task[None]] = None

        self._stop_lock = asyncio.Lock()

    @property
    def state(self) -> MeetingState:
        """Return the current meeting state."""
        return self._state

    @property
    def running(self) -> bool:
        """Return whether the meeting is currently running."""
        return self._state is MeetingState.RUNNING

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def meeting_url(self) -> str | None:
        return self._meeting_url

    @property
    def transcript(self) -> str:
        """Return the finalized meeting transcript."""
        return self._assembler.get_text(
            include_speakers=True
        )

    @property
    def partial_transcript(self) -> str:
        """Return the latest live partial transcript."""
        return self._assembler.partial_text

    @property
    def entries(self) -> tuple[AssembledTranscript, ...]:
        """Return finalized transcript entries."""
        return tuple(self._assembler.entries)

    async def start(self) -> None:
        """
        Start all Meetly processing components.

        The recorder remains responsible for producing AudioChunk objects.
        Those chunks are submitted through submit_audio().
        """
        if self._state is MeetingState.RUNNING:
            return

        if self._state is MeetingState.STOPPING:
            raise MeetingStateError(
                "Cannot start a meeting while it is stopping."
            )

        if self._state is MeetingState.ERROR:
            raise MeetingStateError(
                "Cannot restart a meeting in ERROR state."
            )

        try:
            self._assembler.clear()

            await self._assembler.start()
            await self._transcriber.start()
            await self._diarizer.start()

            self._transcript_task = asyncio.create_task(
                self._consume_transcripts(),
                name="meetly-meeting-transcripts",
            )

            self._speaker_task = asyncio.create_task(
                self._consume_speakers(),
                name="meetly-meeting-speakers",
            )

            self._state = MeetingState.RUNNING

            if self._recorder is not None:
                await self._recorder.start()
                self._audio_task = asyncio.create_task(
                    self._consume_recorder(),
                    name="meetly-meeting-recorder",
                )

            logger.info("Meeting started.")

        except Exception:
            self._state = MeetingState.ERROR

            await self._safe_stop_components()

            raise

    async def submit_audio(
        self,
        audio: AudioChunk,
    ) -> None:
        """
        Submit one AudioChunk to the transcription and diarization pipelines.
        """
        if not self.running:
            raise MeetingStateError(
                "Cannot submit audio when the meeting is not running."
            )

        if not isinstance(audio, AudioChunk):
            raise TypeError(
                "audio must be an AudioChunk."
            )

        await asyncio.gather(
            self._transcriber.submit(audio),
            self._diarizer.submit(audio),
        )

    async def stream_transcript(
        self,
    ) -> AsyncIterator[AssembledTranscript]:
        """
        Stream finalized transcript entries as they are assembled.
        """
        async for entry in self._assembler.stream():
            yield entry

    async def stop(self) -> str:
        """
        Stop the meeting and return the finalized transcript.

        Processing already queued inside the transcription and diarization
        pipelines is allowed to drain before the meeting is finalized.
        """
        async with self._stop_lock:
            if self._state is MeetingState.STOPPED:
                return self.transcript

            if self._state is MeetingState.IDLE:
                raise MeetingStateError(
                    "Cannot stop a meeting that has not started."
                )

            self._state = MeetingState.STOPPING

            try:
                await self._stop_audio_source()
                await self._transcriber.stop()
                await self._diarizer.stop()

                await self._wait_for_processing_tasks()

                await self._assembler.stop()

                self._state = MeetingState.STOPPED

                logger.info("Meeting stopped.")

                return self.transcript

            except asyncio.CancelledError:
                self._state = MeetingState.ERROR
                raise

            except Exception:
                self._state = MeetingState.ERROR
                logger.exception("Failed to stop meeting.")
                raise

    async def summary(self) -> str:
        """
        Generate a summary from the finalized meeting transcript.
        """
        transcript = self.transcript

        if not transcript:
            raise ValueError(
                "Cannot generate a summary from an empty transcript."
            )

        return await self._summarizer.summarize(
            transcript
        )

    def qna(
        self,
        *,
        embedding_model: str = (
            "sentence-transformers/all-MiniLM-L6-v2"
        ),
        chunk_size: int = 800,
        chunk_overlap: int = 120,
        retrieval_k: int = 5,
    ) -> MeetingQnA:
        """
        Create a RAG-based Q&A interface for the finalized transcript.
        """
        transcript = self.transcript

        if not transcript:
            raise ValueError(
                "Cannot create Q&A for an empty transcript."
            )

        from meetly.audio.processing.ai.qna import MeetingQnA

        return MeetingQnA(
            transcript=transcript,
            llm=self._qna_llm,
            embedding_model=embedding_model,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            retrieval_k=retrieval_k,
        )

    async def ask(
        self,
        question: str,
        *,
        embedding_model: str = (
            "sentence-transformers/all-MiniLM-L6-v2"
        ),
        chunk_size: int = 800,
        chunk_overlap: int = 120,
        retrieval_k: int = 5,
    ) -> str:
        """
        Ask a question about the finalized meeting using RAG.
        """
        qna = self.qna(
            embedding_model=embedding_model,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            retrieval_k=retrieval_k,
        )

        return await qna.answer(question)

    async def _consume_transcripts(self) -> None:
        """
        Forward finalized transcription results to the assembler.
        """
        try:
            async for transcript in self._transcriber.stream():
                await self._assembler.add_transcript(
                    transcript
                )

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Meeting transcript consumer failed."
            )
            self._state = MeetingState.ERROR
            raise

    async def _consume_recorder(self) -> None:
        """Forward recorder output into the processing pipeline."""
        if self._recorder is None:
            return

        try:
            async for audio in self._recorder:
                if self._state is not MeetingState.RUNNING:
                    break
                await self.submit_audio(audio)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Meeting audio source failed.")
            self._state = MeetingState.ERROR
            raise

    async def _consume_speakers(self) -> None:
        """
        Forward diarization results to the assembler.
        """
        try:
            async for segment in self._diarizer.stream():
                self._assembler.add_speaker_segment(
                    segment
                )

        except asyncio.CancelledError:
            raise

        except Exception:
            logger.exception(
                "Meeting speaker consumer failed."
            )
            self._state = MeetingState.ERROR
            raise

    async def _wait_for_processing_tasks(self) -> None:
        tasks = [
            task
            for task in (
                self._transcript_task,
                self._speaker_task,
            )
            if task is not None
        ]

        if not tasks:
            return

        results = await asyncio.gather(
            *tasks,
            return_exceptions=True,
        )

        self._transcript_task = None
        self._speaker_task = None

        for result in results:
            if isinstance(result, BaseException):
                raise result

    async def _safe_stop_components(self) -> None:
        """
        Best-effort shutdown used when startup fails.
        """
        await self._stop_audio_source()

        for component in (
            self._transcriber,
            self._diarizer,
            self._assembler,
        ):
            try:
                await component.stop()
            except Exception:
                logger.exception(
                    "Failed to stop %s during cleanup.",
                    type(component).__name__,
                )

    async def _stop_audio_source(self) -> None:
        """Stop and await the provider stream before draining processors."""
        task = self._audio_task
        self._audio_task = None

        if task is not None:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        if self._recorder is not None:
            try:
                await self._recorder.stop()
            except Exception:
                logger.exception("Failed to stop the meeting recorder.")

    async def __aenter__(self) -> "Meeting":
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        if self._state is MeetingState.RUNNING:
            await self.stop()


__all__ = [
    "Meeting",
    "MeetingState",
    "MeetingStateError",
]