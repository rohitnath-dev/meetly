"""
Events used throughout the Meetly audio pipeline.

These events provide lightweight notifications for important
audio-pipeline state changes. They do not perform processing
themselves.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .recorder.models import AudioChunk, TranscriptChunk, SpeakerSegment


@dataclass(slots=True)
class AudioReceived:
    """Emitted when a new audio chunk is received."""

    chunk: AudioChunk
    timestamp: datetime


@dataclass(slots=True)
class TranscriptReceived:
    """Emitted when a transcript result is generated."""

    transcript: TranscriptChunk
    timestamp: datetime


@dataclass(slots=True)
class SpeakerDetected:
    """Emitted when a speaker segment is detected."""

    speaker: SpeakerSegment
    timestamp: datetime


__all__ = [
    "AudioReceived",
    "TranscriptReceived",
    "SpeakerDetected",
]