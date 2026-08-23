"""
Low-latency Whisper transcription engine for Meetly.

This module receives short AudioChunk objects and continuously
produces partial transcript hypotheses from a rolling audio context.

The engine intentionally keeps the faster-whisper model behind the
TranscriptionEngine abstraction so the recorder and meeting layers
remain independent of the speech-to-text provider.

Timestamp convention
--------------------
Transcript timestamps are measured in seconds elapsed from the
beginning of each audio source/session.

They are NOT Unix timestamps.

This allows the transcription and diarization pipelines to share the
same timeline later.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple
from collections import deque

from ..recorder.models import AudioChunk, AudioFormat, TranscriptChunk
from .transcriber import TranscriptionEngine, TranscriptionError

logger = logging.getLogger(__name__)


_BYTES_PER_SAMPLE = {
    AudioFormat.PCM16: 2,
}


class ModelInitializationError(TranscriptionError):
    """Raised when the Whisper model cannot be initialized."""


class InvalidAudioFormatError(TranscriptionError):
    """Raised when incoming audio does not match the engine configuration."""


class TranscriptionFailedError(TranscriptionError):
    """Raised when Whisper inference fails."""


@dataclass
class _SourceBuffer:
    """
    Runtime state for one audio source.

    The buffer keeps enough recent audio to repeatedly generate
    transcription hypotheses while preserving a small amount of
    context between inference calls.
    """

    chunks: Deque[bytes] = field(default_factory=deque)
    buffered_bytes: int = 0

    timeline_start: Optional[float] = None
    total_audio_seconds: float = 0.0

    last_text: str = ""
    last_final_text: str = ""

    # Text which has remained stable across multiple inference passes.
    stable_text: str = ""

    # Number of consecutive inference passes in which the current
    # hypothesis remained unchanged.
    stable_passes: int = 0


class WhisperEngine(TranscriptionEngine):
    """
    faster-whisper based low-latency transcription engine.

    Unlike the previous implementation, this engine does not wait for
    a fixed 3-second window before producing a result.

    Instead:

        AudioChunk
            ↓
        rolling buffer
            ↓
        short inference window
            ↓
        partial TranscriptChunk
            ↓
        updated partial hypothesis
            ↓
        final/stable transcript chunks

    The engine still uses a small amount of context because Whisper
    cannot reliably recognize an individual ~64 ms microphone chunk.

    Partial results should be treated as replaceable hypotheses by the
    consumer. Final results can be committed permanently.
    """

    def __init__(
        self,
        *,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        sample_rate: int = 16000,
        channels: int = 1,
        inference_window_seconds: float = 1.0,
        minimum_audio_seconds: float = 0.4,
        context_seconds: float = 2.0,
        inference_interval_seconds: float = 0.25,
        language: Optional[str] = None,
        stability_passes: int = 2,
    ) -> None:
        """
        Configure the Whisper engine.

        Args:
            model_size:
                faster-whisper model name, for example "base".

            device:
                Inference device, normally "cpu" or "cuda".

            compute_type:
                faster-whisper compute type, for example "int8".

            sample_rate:
                Expected input sample rate.

            channels:
                Expected input channel count.

            inference_window_seconds:
                Minimum amount of recent audio used for an inference
                pass.

            minimum_audio_seconds:
                Minimum audio required before the first inference.

            context_seconds:
                Maximum recent audio retained as context.

            inference_interval_seconds:
                Minimum elapsed audio time between inference passes.

            language:
                Optional forced language code.

            stability_passes:
                Number of identical consecutive hypotheses required
                before text is considered stable enough to finalize.
        """

        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive.")

        if channels <= 0:
            raise ValueError("channels must be positive.")

        if inference_window_seconds <= 0:
            raise ValueError(
                "inference_window_seconds must be positive."
            )

        if minimum_audio_seconds <= 0:
            raise ValueError(
                "minimum_audio_seconds must be positive."
            )

        if context_seconds < inference_window_seconds:
            raise ValueError(
                "context_seconds must be >= inference_window_seconds."
            )

        if inference_interval_seconds <= 0:
            raise ValueError(
                "inference_interval_seconds must be positive."
            )

        if stability_passes <= 0:
            raise ValueError(
                "stability_passes must be positive."
            )

        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type

        self._sample_rate = sample_rate
        self._channels = channels

        self._inference_window_seconds = inference_window_seconds
        self._minimum_audio_seconds = minimum_audio_seconds
        self._context_seconds = context_seconds
        self._inference_interval_seconds = inference_interval_seconds

        self._language = language
        self._stability_passes = stability_passes

        self._bytes_per_sample = _BYTES_PER_SAMPLE[AudioFormat.PCM16]

        self._bytes_per_second = (
            self._sample_rate
            * self._channels
            * self._bytes_per_sample
        )

        self._model = None

        self._init_lock = asyncio.Lock()
        self._inference_lock = asyncio.Lock()

        self._buffers: Dict[str, _SourceBuffer] = {}

    # ------------------------------------------------------------------
    # Model lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """
        Load faster-whisper exactly once.

        Safe to call multiple times.
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
                    f"Failed to load Whisper model "
                    f"'{self._model_size}': {exc}"
                ) from exc

            logger.info(
                "Whisper model '%s' loaded "
                "(device=%s, compute_type=%s).",
                self._model_size,
                self._device,
                self._compute_type,
            )

    # ------------------------------------------------------------------
    # Public transcription API
    # ------------------------------------------------------------------

    async def transcribe(
        self,
        audio: AudioChunk,
    ) -> Optional[TranscriptChunk]:
        """
        Consume one AudioChunk and produce the latest transcript
        hypothesis when enough new audio is available.

        The returned TranscriptChunk is normally partial
        (is_final=False).

        Stable text may be marked final when the same hypothesis
        remains unchanged across multiple inference passes.
        """

        self._validate_audio(audio)

        if self._model is None:
            await self.initialize()

        buffer = self._buffers.setdefault(
            audio.source,
            _SourceBuffer(),
        )

        if buffer.timeline_start is None:
            buffer.timeline_start = 0.0

        buffer.chunks.append(audio.data)
        buffer.buffered_bytes += len(audio.data)

        chunk_duration = (
            len(audio.data) / self._bytes_per_second
        )

        buffer.total_audio_seconds += chunk_duration

        buffered_duration = (
            buffer.buffered_bytes / self._bytes_per_second
        )

        if buffered_duration < self._minimum_audio_seconds:
            return None

        # Do not run Whisper on every tiny microphone callback.
        # This prevents excessive CPU usage.
        if (
            buffer.last_text
            and (
                buffer.total_audio_seconds
                - self._last_inference_time(buffer)
                < self._inference_interval_seconds
            )
        ):
            return None

        window_bytes, window_start, window_duration = (
            self._build_inference_window(buffer)
        )

        try:
            text, confidence = await self._run_inference(
                window_bytes
            )

        except Exception as exc:
            logger.exception(
                "Whisper inference failed for source '%s'.",
                audio.source,
            )

            # IMPORTANT:
            # Do not destroy the buffered audio when inference fails.
            raise TranscriptionFailedError(
                f"Whisper inference failed for "
                f"source '{audio.source}': {exc}"
            ) from exc

        text = text.strip()

        if not text:
            return None

        previous_text = buffer.last_text

        buffer.last_text = text

        # Track stability.
        if text == previous_text:
            buffer.stable_passes += 1
        else:
            buffer.stable_passes = 0

        is_final = (
            buffer.stable_passes >= self._stability_passes
        )

        if is_final:
            final_text = self._extract_new_final_text(
                buffer,
                text,
            )

            if not final_text:
                return None

            buffer.last_final_text = text
            buffer.stable_text = text

            return TranscriptChunk(
                text=final_text,
                start_time=window_start,
                end_time=window_start + window_duration,
                confidence=confidence,
                is_final=True,
            )

        return TranscriptChunk(
            text=text,
            start_time=window_start,
            end_time=window_start + window_duration,
            confidence=confidence,
            is_final=False,
        )

    # ------------------------------------------------------------------
    # Buffer handling
    # ------------------------------------------------------------------

    def _build_inference_window(
        self,
        buffer: _SourceBuffer,
    ) -> Tuple[bytes, float, float]:
        """
        Build a bounded rolling inference window.

        The most recent context is preferred so that the latest speech
        is reflected in the partial hypothesis.
        """

        max_bytes = int(
            self._context_seconds
            * self._bytes_per_second
        )

        current = b"".join(buffer.chunks)

        if len(current) > max_bytes:
            current = current[-max_bytes:]

        duration = (
            len(current) / self._bytes_per_second
        )

        start = max(
            0.0,
            buffer.total_audio_seconds - duration,
        )

        return current, start, duration

    def _last_inference_time(
        self,
        buffer: _SourceBuffer,
    ) -> float:
        """
        Approximate the audio position represented by the previous
        inference.

        The current rolling hypothesis itself serves as the marker.
        """

        if not buffer.last_text:
            return 0.0

        return max(
            0.0,
            buffer.total_audio_seconds
            - self._context_seconds,
        )

    def _extract_new_final_text(
        self,
        buffer: _SourceBuffer,
        text: str,
    ) -> str:
        """
        Return only text that has not already been committed.

        This prevents stable hypotheses from being permanently
        duplicated in the final transcript.
        """

        if not buffer.last_final_text:
            return text

        old_words = buffer.last_final_text.split()
        new_words = text.split()

        common = 0

        max_overlap = min(
            len(old_words),
            len(new_words),
        )

        for size in range(max_overlap, 0, -1):

            if old_words[-size:] == new_words[:size]:
                common = size
                break

        if common:
            new_words = new_words[common:]

        return " ".join(new_words).strip()

    # ------------------------------------------------------------------
    # Audio validation
    # ------------------------------------------------------------------

    def _validate_audio(
        self,
        audio: AudioChunk,
    ) -> None:
        """Validate incoming audio against engine configuration."""

        if audio.format != AudioFormat.PCM16:
            raise InvalidAudioFormatError(
                f"Unsupported audio format '{audio.format}'. "
                "Only PCM16 is supported."
            )

        if audio.sample_rate != self._sample_rate:
            raise InvalidAudioFormatError(
                f"Unsupported sample rate "
                f"{audio.sample_rate}; "
                f"expected {self._sample_rate}."
            )

        if audio.channels != self._channels:
            raise InvalidAudioFormatError(
                f"Unsupported channel count "
                f"{audio.channels}; "
                f"expected {self._channels}."
            )

    # ------------------------------------------------------------------
    # Whisper inference
    # ------------------------------------------------------------------

    async def _run_inference(
        self,
        pcm_bytes: bytes,
    ) -> Tuple[str, Optional[float]]:
        """
        Convert PCM16 audio to float32 and run faster-whisper
        outside the asyncio event loop.
        """

        import numpy as np

        samples = (
            np.frombuffer(
                pcm_bytes,
                dtype=np.int16,
            )
            .astype(np.float32)
            / 32768.0
        )

        async with self._inference_lock:

            segments, _info = await asyncio.to_thread(
                self._model.transcribe,
                samples,
                language=self._language,
                vad_filter=True,
                condition_on_previous_text=True,
            )

            segments = list(segments)

        texts = []

        confidences = []

        for segment in segments:

            segment_text = segment.text.strip()

            if segment_text:
                texts.append(segment_text)

            if segment.avg_logprob is not None:
                # faster-whisper avg_logprob is not already a
                # [0, 1] confidence value. We deliberately don't
                # expose it as confidence.
                pass

        text = " ".join(texts).strip()

        # We cannot honestly convert avg_logprob into a calibrated
        # confidence score. Keep this None rather than exposing a
        # misleading number.
        confidence = None

        return text, confidence

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def reset_source(
        self,
        source: str,
    ) -> None:
        """
        Clear all transcription state for one audio source.

        Call this when a meeting/source ends so the next meeting
        starts from a clean timeline.
        """

        self._buffers.pop(source, None)

    def reset(self) -> None:
        """
        Clear all source buffers.

        This does not unload the Whisper model.
        """

        self._buffers.clear()


__all__ = [
    "WhisperEngine",
    "ModelInitializationError",
    "InvalidAudioFormatError",
    "TranscriptionFailedError",
]