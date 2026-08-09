"""
faster-whisper backed TranscriptionEngine implementation for Meetly.

Provides near-real-time transcription of short, streamed AudioChunk
objects by buffering audio per source into rolling inference windows
before running Whisper, since a single microphone chunk (commonly
~64 ms) is far too short to transcribe usefully on its own.
"""

from __future__ import annotations

import asyncio
import difflib
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

from ..recorder.models import AudioChunk, AudioFormat, TranscriptChunk
from .transcriber import TranscriptionEngine, TranscriptionError

logger = logging.getLogger(__name__)

_BYTES_PER_SAMPLE = {
    AudioFormat.PCM16: 2,
}


class ModelInitializationError(TranscriptionError):
    """Raised when the Whisper model fails to load."""


class InvalidAudioFormatError(TranscriptionError):
    """Raised when an AudioChunk's format is not supported by this engine."""


class TranscriptionFailedError(TranscriptionError):
    """Raised when Whisper inference fails for a buffered audio window."""


@dataclass
class _SourceBuffer:
    """Rolling audio buffer and dedup state kept per ``audio.source``."""

    chunks: Deque[bytes] = field(default_factory=deque)
    buffered_bytes: int = 0
    window_start_time: Optional[float] = None
    last_tail_words: List[str] = field(default_factory=list)


class WhisperEngine(TranscriptionEngine):
    """
    ``TranscriptionEngine`` implementation backed by faster-whisper.

    Incoming ``AudioChunk`` objects are accumulated per ``audio.source``
    into a rolling window (``target_window_seconds``). Inference only
    runs once a window is full and at least ``min_duration_seconds`` of
    audio has been buffered; smaller amounts are held and ``None`` is
    returned. A configurable ``overlap_seconds`` of trailing audio is
    carried into the next window so words are not cut off at window
    boundaries, and a word-level dedup step strips text that overlaps
    with the previous window's tail so overlapping windows do not
    repeat text.

    The model is loaded once (lazily, on first use, or explicitly via
    :meth:`initialize`) and inference is serialized behind a lock,
    since the underlying faster-whisper model is not safe for
    concurrent use from multiple threads.
    """

    def __init__(
        self,
        *,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        sample_rate: int = 16000,
        channels: int = 1,
        target_window_seconds: float = 4.0,
        min_duration_seconds: float = 1.5,
        overlap_seconds: float = 0.5,
        language: Optional[str] = None,
    ) -> None:
        """
        Configure a Whisper transcription engine.

        Args:
            model_size: faster-whisper model name/size (e.g. "base", "small").
            device: Inference device, e.g. "cpu" or "cuda".
            compute_type: faster-whisper compute type (e.g. "int8", "float16").
            sample_rate: Expected sample rate, in Hz, of incoming audio.
            channels: Expected channel count of incoming audio.
            target_window_seconds: Audio duration accumulated per inference window.
            min_duration_seconds: Minimum buffered duration required before
                a completed window is actually sent to Whisper.
            overlap_seconds: Trailing audio carried from one window into the next.
            language: Optional forced language code; auto-detected if None.

        Raises:
            ValueError: If a rate/channel/duration argument is not positive,
                or if ``overlap_seconds`` is not smaller than ``target_window_seconds``.
        """
        if sample_rate <= 0 or channels <= 0:
            raise ValueError("sample_rate and channels must be positive.")
        if target_window_seconds <= 0 or min_duration_seconds <= 0:
            raise ValueError("Window durations must be positive.")
        if overlap_seconds < 0 or overlap_seconds >= target_window_seconds:
            raise ValueError(
                "overlap_seconds must be >= 0 and < target_window_seconds."
            )

        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._sample_rate = sample_rate
        self._channels = channels
        self._target_window_seconds = target_window_seconds
        self._min_duration_seconds = min_duration_seconds
        self._overlap_seconds = overlap_seconds
        self._language = language

        self._bytes_per_sample = _BYTES_PER_SAMPLE[AudioFormat.PCM16]
        self._bytes_per_second = (
            self._sample_rate * self._channels * self._bytes_per_sample
        )

        self._model = None
        self._init_lock = asyncio.Lock()
        self._inference_lock = asyncio.Lock()
        self._buffers: Dict[str, _SourceBuffer] = {}

    async def initialize(self) -> None:
        """
        Load the Whisper model, if it has not been loaded already.

        Safe to call concurrently or more than once; the model is
        loaded exactly once. Called automatically on first use of
        :meth:`transcribe` if not called explicitly beforehand.

        Raises:
            ModelInitializationError: If the model fails to load.
        """
        if self._model is not None:
            return

        async with self._init_lock:
            if self._model is not None:
                return
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise ModelInitializationError(
                    "faster-whisper is not installed. "
                    "Install it with `pip install faster-whisper`."
                ) from exc

            try:
                self._model = await asyncio.to_thread(
                    WhisperModel,
                    self._model_size,
                    device=self._device,
                    compute_type=self._compute_type,
                )
            except Exception as exc:
                raise ModelInitializationError(
                    f"Failed to load Whisper model '{self._model_size}': {exc}"
                ) from exc

            logger.info(
                "Whisper model '%s' loaded (device=%s, compute_type=%s).",
                self._model_size,
                self._device,
                self._compute_type,
            )

    async def transcribe(self, audio: AudioChunk) -> Optional[TranscriptChunk]:
        """
        Buffer ``audio`` and, once its source has accumulated a full
        window, run Whisper inference on that window.

        Args:
            audio: A short raw audio chunk.

        Returns:
            A TranscriptChunk if a window was completed and produced
            usable (non-empty, non-duplicate) text, otherwise None.

        Raises:
            InvalidAudioFormatError: If the chunk's format, sample rate,
                or channel count is unsupported.
            ModelInitializationError: If the model has not loaded and
                fails to load on demand.
            TranscriptionFailedError: If inference itself fails.
        """
        self._validate_format(audio)

        if self._model is None:
            await self.initialize()

        buf = self._buffers.setdefault(audio.source, _SourceBuffer())
        if buf.window_start_time is None:
            buf.window_start_time = audio.timestamp.timestamp()

        buf.chunks.append(audio.data)
        buf.buffered_bytes += len(audio.data)
        duration = buf.buffered_bytes / self._bytes_per_second

        if duration < self._target_window_seconds:
            return None

        window_bytes = b"".join(buf.chunks)
        window_start = buf.window_start_time
        window_duration = len(window_bytes) / self._bytes_per_second

        self._carry_overlap(buf, window_bytes, window_start, window_duration)

        if window_duration < self._min_duration_seconds:
            return None

        try:
            text, confidence = await self._run_inference(window_bytes)
        except Exception as exc:
            raise TranscriptionFailedError(
                f"Whisper inference failed for source '{audio.source}': {exc}"
            ) from exc

        text = self._dedupe_overlap(buf, text)
        if not text:
            return None

        return TranscriptChunk(
            text=text,
            start_time=window_start,
            end_time=window_start + window_duration,
            confidence=confidence,
            is_final=True,
        )

    def _carry_overlap(
        self,
        buf: _SourceBuffer,
        window_bytes: bytes,
        window_start: float,
        window_duration: float,
    ) -> None:
        """Reset ``buf`` to hold only the trailing overlap audio (if any)
        so it forms the start of the next window."""
        overlap_bytes = int(self._overlap_seconds * self._bytes_per_second)
        overlap_bytes -= overlap_bytes % self._bytes_per_sample

        if 0 < overlap_bytes < len(window_bytes):
            retained = window_bytes[-overlap_bytes:]
            buf.chunks = deque([retained])
            buf.buffered_bytes = len(retained)
            buf.window_start_time = window_start + (
                window_duration - (len(retained) / self._bytes_per_second)
            )
        else:
            buf.chunks = deque()
            buf.buffered_bytes = 0
            buf.window_start_time = None

    def _validate_format(self, audio: AudioChunk) -> None:
        """Validate that an incoming chunk matches the supported format."""
        if audio.format != AudioFormat.PCM16:
            raise InvalidAudioFormatError(
                f"Unsupported audio format '{audio.format}'; only PCM16 is supported."
            )
        if audio.sample_rate != self._sample_rate:
            raise InvalidAudioFormatError(
                f"Unsupported sample rate {audio.sample_rate}; "
                f"expected {self._sample_rate}."
            )
        if audio.channels != self._channels:
            raise InvalidAudioFormatError(
                f"Unsupported channel count {audio.channels}; "
                f"expected {self._channels}."
            )

    async def _run_inference(self, pcm_bytes: bytes) -> Tuple[str, Optional[float]]:
        """
        Convert PCM16 bytes to normalized float32 samples and run
        blocking Whisper inference in a worker thread, serialized
        behind a lock since the model is not thread-safe.
        """
        import numpy as np

        samples = (
            np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        )

        async with self._inference_lock:
            segments, _info = await asyncio.to_thread(
                self._model.transcribe,
                samples,
                language=self._language,
            )
            segments = list(segments)

        text = " ".join(segment.text.strip() for segment in segments).strip()
        confidences = [
            segment.avg_logprob
            for segment in segments
            if segment.avg_logprob is not None
        ]
        confidence = sum(confidences) / len(confidences) if confidences else None
        return text, confidence

    def _dedupe_overlap(self, buf: _SourceBuffer, text: str) -> str:
        """
        Strip words from the start of ``text`` that duplicate the tail
        of the previously emitted text for this source, compensating
        for re-transcribing the retained overlap audio.
        """
        words = text.split()
        if not words:
            return ""

        if buf.last_tail_words:
            matcher = difflib.SequenceMatcher(
                None, buf.last_tail_words, words, autojunk=False
            )
            match = matcher.find_longest_match(
                0, len(buf.last_tail_words), 0, len(words)
            )
            if match.b == 0 and match.size > 0:
                words = words[match.size :]

        buf.last_tail_words = text.split()[-10:]
        return " ".join(words)
