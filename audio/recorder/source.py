"""
Abstract audio source.

Every audio provider must inherit from AudioSource and implement
its lifecycle and streaming methods.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from .models import AudioChunk


class AudioSource(ABC):
    """
    Base interface for all audio sources.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Human-readable source name.

        Example:
            - Microphone
            - Zoom
            - Google Meet
        """
        raise NotImplementedError

    @abstractmethod
    async def start(self) -> None:
        """
        Start the audio source.
        """
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        """
        Stop the audio source.
        """
        raise NotImplementedError

    @abstractmethod
    async def stream(self) -> AsyncIterator[AudioChunk]:
        """
        Yield audio chunks continuously until stopped.
        """
        raise NotImplementedError