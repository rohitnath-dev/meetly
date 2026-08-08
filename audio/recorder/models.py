"""
Shared data models for the audio pipeline.

These models are exchanged between AudioSource, Recorder,
Transcriber, Diarizer, and the Meeting Engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class AudioFormat(str, Enum):
    """Supported raw audio formats."""

    PCM16 = "pcm16"
    PCM32 = "pcm32"
    FLOAT32 = "float32"


class RecordingState(str, Enum):
    """Current state of the recorder."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass(slots=True)
class AudioChunk:
    """
    A small piece of raw audio.

    Attributes:
        data:
            Raw audio bytes.
        sample_rate:
            Audio sample rate in Hz.
        channels:
            Number of audio channels.
        format:
            Encoding format.
        timestamp:
            UTC time when the chunk was created.
        source:
            Name of the audio source.
    """

    data: bytes
    sample_rate: int
    channels: int
    format: AudioFormat

    timestamp: datetime = field(default_factory=datetime.utcnow)
    source: str = "unknown"


@dataclass(slots=True)
class TranscriptChunk:
    """
    A partial or complete transcript.
    """

    text: str

    start_time: float
    end_time: float

    confidence: Optional[float] = None
    is_final: bool = False


@dataclass(slots=True)
class SpeakerSegment:
    """
    Speaker identification for part of a transcript.
    """

    speaker_id: str

    start_time: float
    end_time: float

    confidence: Optional[float] = None