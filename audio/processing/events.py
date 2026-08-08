"""
Events used throughout the audio pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .models import AudioChunk, TranscriptChunk, SpeakerSegment


@dataclass(slots=True)
class AudioReceived:
    """
    Fired when a new audio chunk is received.
    """

    chunk: AudioChunk
    timestamp: datetime


@dataclass(slots=True)
class TranscriptReceived:
    """
    Fired when a transcript is generated.
    """

    transcript: TranscriptChunk
    timestamp: datetime


@dataclass(slots=True)
class SpeakerDetected:
    """
    Fired when a speaker is identified.
    """

    speaker: SpeakerSegment
    timestamp: datetime