"""
Shared data models for the Meetly audio pipeline.

These models are used by the recorder, live transcription,
diarization, and transcript-processing layers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class AudioFormat(str, Enum):
    """Supported audio formats."""

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


@dataclass
class AudioChunk:
    """
    A chunk of raw audio produced by an audio source.

    Attributes:
        data:
            Raw audio bytes.

        sample_rate:
            Audio sample rate in Hz.

        channels:
            Number of audio channels.

        format:
            Audio encoding format.

        timestamp:
            Time at which the chunk was created.

        source:
            Name of the audio source.
    """

    data: bytes
    sample_rate: int
    channels: int
    format: AudioFormat

    timestamp: datetime

    source: str = "unknown"


@dataclass
class TranscriptChunk:
    """
    A piece of transcribed speech.

    The same structure supports both partial and final
    transcription results.

    Attributes:
        text:
            Transcribed text.

        start_time:
            Start time in seconds relative to the meeting/session.

        end_time:
            End time in seconds relative to the meeting/session.

        confidence:
            Optional confidence score between 0 and 1.

        is_final:
            False for a partial/live hypothesis.
            True when the text is finalized.
    """

    text: str
    start_time: float
    end_time: float

    confidence: Optional[float] = None

    is_final: bool = False


@dataclass
class SpeakerSegment:
    """
    A segment of audio attributed to a speaker.

    Attributes:
        speaker_id:
            Anonymous or resolved speaker identifier.

        start_time:
            Start time in seconds relative to the meeting/session.

        end_time:
            End time in seconds relative to the meeting/session.

        confidence:
            Optional confidence score between 0 and 1.
    """

    speaker_id: str
    start_time: float
    end_time: float

    confidence: Optional[float] = None


__all__ = [
    "AudioFormat",
    "RecordingState",
    "AudioChunk",
    "TranscriptChunk",
    "SpeakerSegment",
]