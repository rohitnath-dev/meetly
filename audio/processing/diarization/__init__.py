"""
Public API for Meetly speaker diarization.

This package provides:

    Diarizer
        Live diarization coordinator.

    DiarizationEngine
        Abstract diarization backend.

    AcousticDiarizationEngine
        Default CPU-friendly diarization implementation.

    SpeakerIdentityResolver
        Interface for resolving anonymous speakers to participants.

    ParticipantRegistry
        Simple participant/identity registry.
"""

from .diarizer import (
    DiarizationEngine,
    Diarizer,
    DiarizationError,
    DiarizerStateError,
    UnsupportedAudioFormatError,
)

from .engine import (
    AcousticDiarizationEngine,
)

from .identity import (
    IdentityResolutionError,
    Participant,
    ParticipantRegistry,
    ResolvedSpeaker,
    SpeakerAttributor,
    SpeakerIdentityResolver,
)

__all__ = [
    # Diarization
    "Diarizer",
    "DiarizationEngine",
    "AcousticDiarizationEngine",
    "DiarizationError",
    "DiarizerStateError",
    "UnsupportedAudioFormatError",

    # Identity
    "SpeakerIdentityResolver",
    "ParticipantRegistry",
    "Participant",
    "ResolvedSpeaker",
    "SpeakerAttributor",
    "IdentityResolutionError",
]