"""
Audio processing package for Meetly.

Exposes the live transcription pipeline: submit AudioChunk objects and
receive TranscriptChunk results via async iteration or callbacks.
"""

from .transcriber import Transcriber, TranscriptionEngine, TranscriptionError
from .whisper import WhisperEngine

__all__ = [
    "Transcriber",
    "TranscriptionEngine",
    "TranscriptionError",
    "WhisperEngine",
]
