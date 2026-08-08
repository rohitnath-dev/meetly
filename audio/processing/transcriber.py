"""
Abstract speech-to-text interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from .models import AudioChunk, TranscriptChunk


class Transcriber(ABC):
    """
    Base interface for all speech-to-text engines.

    Examples:
        - Whisper
        - Deepgram
        - AssemblyAI
        - Azure Speech
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable engine name."""
        raise NotImplementedError

    @abstractmethod
    async def start(self) -> None:
        """Initialize the transcription engine."""
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        """Release resources."""
        raise NotImplementedError

    @abstractmethod
    async def transcribe(
        self,
        audio: AsyncIterator[AudioChunk],
    ) -> AsyncIterator[TranscriptChunk]:
        """
        Convert an audio stream into transcript chunks.
        """
        raise NotImplementedError