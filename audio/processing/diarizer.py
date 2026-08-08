"""Speaker diarization interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Diarizer(ABC):
    """Base interface for speaker identification."""

    @abstractmethod
    async def start(self) -> None:
        """Initialize the diarizer."""

    @abstractmethod
    async def stop(self) -> None:
        """Release diarizer resources."""

    @abstractmethod
    async def identify(
        self,
        audio_chunk: bytes,
    ) -> str:
        """Return the speaker for an audio chunk."""