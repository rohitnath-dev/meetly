"""
Default CPU-friendly speaker diarization engine for Meetly.

This module implements the DiarizationEngine interface using lightweight
acoustic features and online speaker clustering.

It intentionally has no dependency on PyTorch, pyannote, or a remote
service. The goal is to provide a usable real-time baseline that can
run in constrained environments.

Architecture:

    AudioChunk
        ↓
    PCM16 → mono float32
        ↓
    speech/activity detection
        ↓
    acoustic feature extraction
        ↓
    speaker similarity
        ↓
    online clustering
        ↓
    SpeakerSegment

Important:
    This is diarization, not speaker-name recognition.

The engine produces stable anonymous IDs such as:

    SPEAKER_00
    SPEAKER_01

Identity resolution is handled separately by identity.py.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from ...recorder.models import AudioChunk, AudioFormat, SpeakerSegment
from .diarizer import (
    DiarizationEngine,
    UnsupportedAudioFormatError,
)

logger = logging.getLogger(__name__)


@dataclass
class _SpeakerCluster:
    """Internal state representing one anonymous speaker."""

    speaker_id: str
    centroid: np.ndarray
    sample_count: int = 1


class AcousticDiarizationEngine(DiarizationEngine):
    """
    Lightweight online speaker diarization engine.

    The engine maintains a rolling audio buffer and analyzes short
    windows. Each speech window is converted into a compact acoustic
    representation and compared against existing speaker clusters.

    If the representation is sufficiently similar to an existing
    cluster, the window is assigned to that speaker.

    Otherwise a new anonymous speaker cluster is created until
    max_speakers is reached.

    This implementation is intentionally a baseline rather than a
    neural diarization system. It is designed for portability and
    low dependency overhead.
    """

    def __init__(
        self,
        *,
        sample_rate: int = 16000,
        channels: int = 1,
        window_seconds: float = 1.0,
        min_speech_seconds: float = 0.5,
        overlap_seconds: float = 0.2,
        similarity_threshold: float = 0.86,
        max_speakers: int = 8,
        silence_rms_threshold: float = 0.01,
    ) -> None:
        """
        Configure the diarization engine.

        Args:
            sample_rate:
                Expected PCM sample rate.

            channels:
                Expected number of channels.

            window_seconds:
                Duration of each diarization analysis window.

            min_speech_seconds:
                Minimum audio required before a partial window can be
                processed during flush().

            overlap_seconds:
                Amount of audio retained between analysis windows.

            similarity_threshold:
                Minimum cosine similarity required to assign a new
                speech window to an existing speaker cluster.

            max_speakers:
                Maximum number of anonymous speaker clusters.

            silence_rms_threshold:
                RMS threshold below which a window is considered
                silence/non-speech.
        """

        if sample_rate <= 0:
            raise ValueError(
                "sample_rate must be positive."
            )

        if channels <= 0:
            raise ValueError(
                "channels must be positive."
            )

        if window_seconds <= 0:
            raise ValueError(
                "window_seconds must be positive."
            )

        if min_speech_seconds <= 0:
            raise ValueError(
                "min_speech_seconds must be positive."
            )

        if min_speech_seconds > window_seconds:
            raise ValueError(
                "min_speech_seconds cannot exceed window_seconds."
            )

        if overlap_seconds < 0:
            raise ValueError(
                "overlap_seconds cannot be negative."
            )

        if overlap_seconds >= window_seconds:
            raise ValueError(
                "overlap_seconds must be smaller than window_seconds."
            )

        if not 0.0 < similarity_threshold <= 1.0:
            raise ValueError(
                "similarity_threshold must be in (0, 1]."
            )

        if max_speakers <= 0:
            raise ValueError(
                "max_speakers must be positive."
            )

        if silence_rms_threshold < 0:
            raise ValueError(
                "silence_rms_threshold cannot be negative."
            )

        self._sample_rate = sample_rate
        self._channels = channels

        self._window_seconds = window_seconds
        self._min_speech_seconds = min_speech_seconds
        self._overlap_seconds = overlap_seconds

        self._similarity_threshold = similarity_threshold
        self._max_speakers = max_speakers
        self._silence_rms_threshold = silence_rms_threshold

        self._bytes_per_sample = 2
        self._bytes_per_frame = (
            self._bytes_per_sample * channels
        )

        self._window_samples = int(
            sample_rate * window_seconds
        )

        self._window_bytes = (
            self._window_samples
            * self._bytes_per_frame
        )

        self._overlap_samples = int(
            sample_rate * overlap_seconds
        )

        self._overlap_bytes = (
            self._overlap_samples
            * self._bytes_per_frame
        )

        self._minimum_flush_bytes = int(
            sample_rate
            * min_speech_seconds
            * self._bytes_per_frame
        )

        self._buffer = bytearray()

        self._timeline_seconds = 0.0

        self._clusters: List[
            _SpeakerCluster
        ] = []

        self._next_speaker_index = 0

        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def diarize(
        self,
        audio: AudioChunk,
    ) -> List[SpeakerSegment]:
        """
        Consume one AudioChunk.

        The engine buffers incoming audio until a complete analysis
        window is available.

        Returns:
            Zero or more SpeakerSegment objects.
        """

        self._validate_audio(audio)

        async with self._lock:

            self._buffer.extend(audio.data)

            results: List[SpeakerSegment] = []

            while len(self._buffer) >= self._window_bytes:

                window = bytes(
                    self._buffer[: self._window_bytes]
                )

                if self._overlap_bytes:
                    self._buffer = self._buffer[
                        self._window_bytes
                        - self._overlap_bytes :
                    ]
                else:
                    self._buffer = self._buffer[
                        self._window_bytes :
                    ]

                start_time = self._timeline_seconds

                end_time = (
                    start_time
                    + self._window_seconds
                )

                self._timeline_seconds = (
                    end_time
                    - self._overlap_seconds
                )

                segment = await asyncio.to_thread(
                    self._process_window,
                    window,
                    start_time,
                    end_time,
                )

                if segment is not None:
                    results.append(segment)

            return results

    async def flush(
        self,
    ) -> List[SpeakerSegment]:
        """
        Process the final partial window.

        Audio shorter than min_speech_seconds is discarded because
        there is not enough information for reliable acoustic
        clustering.
        """

        async with self._lock:

            if len(self._buffer) < self._minimum_flush_bytes:
                self._buffer.clear()
                return []

            window = bytes(self._buffer)

            duration = (
                len(window)
                / self._bytes_per_frame
                / self._sample_rate
            )

            start_time = self._timeline_seconds
            end_time = start_time + duration

            self._buffer.clear()

            segment = await asyncio.to_thread(
                self._process_window,
                window,
                start_time,
                end_time,
            )

            if segment is None:
                return []

            return [segment]

    # ------------------------------------------------------------------
    # Window processing
    # ------------------------------------------------------------------

    def _process_window(
        self,
        pcm_bytes: bytes,
        start_time: float,
        end_time: float,
    ) -> Optional[SpeakerSegment]:
        """
        Analyze one PCM16 window and assign it to a speaker cluster.
        """

        samples = self._pcm16_to_mono(
            pcm_bytes
        )

        if samples.size == 0:
            return None

        rms = float(
            np.sqrt(
                np.mean(
                    np.square(samples)
                )
            )
        )

        if rms < self._silence_rms_threshold:
            return None

        embedding = self._extract_embedding(
            samples
        )

        if embedding is None:
            return None

        cluster, similarity = (
            self._find_cluster(embedding)
        )

        if cluster is None:

            if len(self._clusters) >= self._max_speakers:

                cluster = self._nearest_cluster(
                    embedding
                )

                if cluster is None:
                    return None

                similarity = self._cosine_similarity(
                    embedding,
                    cluster.centroid,
                )

            else:

                cluster = self._create_cluster(
                    embedding
                )

                similarity = 1.0

        else:
            self._update_cluster(
                cluster,
                embedding,
            )

        confidence = self._similarity_to_confidence(
            similarity
        )

        return SpeakerSegment(
            speaker_id=cluster.speaker_id,
            start_time=start_time,
            end_time=end_time,
            confidence=confidence,
        )

    # ------------------------------------------------------------------
    # Audio conversion
    # ------------------------------------------------------------------

    def _pcm16_to_mono(
        self,
        pcm_bytes: bytes,
    ) -> np.ndarray:
        """
        Convert interleaved PCM16 audio to mono float32 samples.
        """

        samples = np.frombuffer(
            pcm_bytes,
            dtype=np.int16,
        )

        if samples.size == 0:
            return np.empty(
                0,
                dtype=np.float32,
            )

        samples = (
            samples.astype(np.float32)
            / 32768.0
        )

        if self._channels == 1:
            return samples

        frame_count = (
            samples.size // self._channels
        )

        if frame_count <= 0:
            return np.empty(
                0,
                dtype=np.float32,
            )

        samples = samples[
            : frame_count * self._channels
        ]

        samples = samples.reshape(
            frame_count,
            self._channels,
        )

        return samples.mean(axis=1)

    # ------------------------------------------------------------------
    # Feature extraction
    # ------------------------------------------------------------------

    def _extract_embedding(
        self,
        samples: np.ndarray,
    ) -> Optional[np.ndarray]:
        """
        Extract a compact acoustic embedding.

        The representation combines:

            - log spectral energy
            - spectral centroid
            - spectral spread
            - spectral rolloff
            - zero-crossing rate
            - coarse spectral-band energies

        It is deliberately lightweight and does not require a neural
        model.
        """

        if samples.size < 256:
            return None

        samples = samples.astype(
            np.float32,
            copy=False,
        )

        window = np.hanning(
            samples.size
        )

        windowed = samples * window

        spectrum = np.abs(
            np.fft.rfft(
                windowed
            )
        )

        power = np.square(spectrum)

        total_power = float(
            np.sum(power)
        )

        if total_power <= 1e-12:
            return None

        frequencies = np.fft.rfftfreq(
            samples.size,
            d=1.0 / self._sample_rate,
        )

        normalized_power = (
            power / total_power
        )

        spectral_centroid = float(
            np.sum(
                frequencies
                * normalized_power
            )
            / self._sample_rate
        )

        spectral_spread = float(
            np.sqrt(
                np.sum(
                    (
                        (
                            frequencies
                            / self._sample_rate
                        )
                        - spectral_centroid
                    )
                    ** 2
                    * normalized_power
                )
            )
        )

        cumulative = np.cumsum(
            normalized_power
        )

        rolloff_index = int(
            np.searchsorted(
                cumulative,
                0.85,
            )
        )

        rolloff_index = min(
            rolloff_index,
            len(frequencies) - 1,
        )

        spectral_rolloff = float(
            frequencies[rolloff_index]
            / self._sample_rate
        )

        zero_crossings = np.count_nonzero(
            np.diff(
                np.signbit(samples)
            )
        )

        zero_crossing_rate = (
            zero_crossings
            / max(samples.size - 1, 1)
        )

        band_energies = self._band_energies(
            power
        )

        log_energy = float(
            np.log10(
                total_power
                + 1e-12
            )
        )

        feature_vector = np.concatenate(
            [
                np.array(
                    [
                        log_energy,
                        spectral_centroid,
                        spectral_spread,
                        spectral_rolloff,
                        zero_crossing_rate,
                    ],
                    dtype=np.float32,
                ),
                band_energies,
            ]
        )

        norm = float(
            np.linalg.norm(
                feature_vector
            )
        )

        if norm <= 1e-8:
            return None

        return (
            feature_vector / norm
        ).astype(np.float32)

    def _band_energies(
        self,
        power: np.ndarray,
    ) -> np.ndarray:
        """
        Calculate normalized energy in coarse spectral bands.
        """

        if power.size < 8:
            return np.zeros(
                8,
                dtype=np.float32,
            )

        boundaries = np.linspace(
            0,
            power.size,
            9,
            dtype=int,
        )

        energies = []

        total = float(
            np.sum(power)
        ) + 1e-12

        for index in range(8):

            start = boundaries[index]
            end = boundaries[index + 1]

            energy = float(
                np.sum(
                    power[start:end]
                )
            )

            energies.append(
                energy / total
            )

        return np.asarray(
            energies,
            dtype=np.float32,
        )

    # ------------------------------------------------------------------
    # Speaker clustering
    # ------------------------------------------------------------------

    def _find_cluster(
        self,
        embedding: np.ndarray,
    ) -> tuple[
        Optional[_SpeakerCluster],
        float,
    ]:
        """
        Find the best existing speaker cluster.
        """

        if not self._clusters:
            return None, 0.0

        best_cluster: Optional[
            _SpeakerCluster
        ] = None

        best_similarity = -1.0

        for cluster in self._clusters:

            similarity = (
                self._cosine_similarity(
                    embedding,
                    cluster.centroid,
                )
            )

            if similarity > best_similarity:
                best_similarity = similarity
                best_cluster = cluster

        if (
            best_cluster is not None
            and best_similarity
            >= self._similarity_threshold
        ):
            return (
                best_cluster,
                best_similarity,
            )

        return None, best_similarity

    def _nearest_cluster(
        self,
        embedding: np.ndarray,
    ) -> Optional[_SpeakerCluster]:
        """
        Return the closest existing cluster.
        """

        if not self._clusters:
            return None

        return max(
            self._clusters,
            key=lambda cluster:
            self._cosine_similarity(
                embedding,
                cluster.centroid,
            ),
        )

    def _create_cluster(
        self,
        embedding: np.ndarray,
    ) -> _SpeakerCluster:
        """
        Create a new anonymous speaker cluster.
        """

        speaker_id = (
            f"SPEAKER_{self._next_speaker_index:02d}"
        )

        self._next_speaker_index += 1

        cluster = _SpeakerCluster(
            speaker_id=speaker_id,
            centroid=embedding.copy(),
            sample_count=1,
        )

        self._clusters.append(
            cluster
        )

        logger.info(
            "Created new speaker cluster: %s",
            speaker_id,
        )

        return cluster

    def _update_cluster(
        self,
        cluster: _SpeakerCluster,
        embedding: np.ndarray,
    ) -> None:
        """
        Update a speaker centroid using a running mean.
        """

        count = cluster.sample_count

        updated = (
            cluster.centroid * count
            + embedding
        ) / (count + 1)

        norm = float(
            np.linalg.norm(updated)
        )

        if norm > 1e-8:
            cluster.centroid = (
                updated / norm
            ).astype(np.float32)

        cluster.sample_count += 1

    @staticmethod
    def _cosine_similarity(
        first: np.ndarray,
        second: np.ndarray,
    ) -> float:
        """
        Calculate cosine similarity.
        """

        first_norm = float(
            np.linalg.norm(first)
        )

        second_norm = float(
            np.linalg.norm(second)
        )

        if (
            first_norm <= 1e-8
            or second_norm <= 1e-8
        ):
            return 0.0

        return float(
            np.dot(first, second)
            / (first_norm * second_norm)
        )

    @staticmethod
    def _similarity_to_confidence(
        similarity: float,
    ) -> float:
        """
        Convert cosine similarity into a bounded heuristic confidence.

        This is NOT a calibrated probability.
        """

        return float(
            np.clip(
                (similarity + 1.0) / 2.0,
                0.0,
                1.0,
            )
        )

    # -----