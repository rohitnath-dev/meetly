"""
Speaker identity resolution for Meetly.

This module handles converting anonymous speaker IDs (SPEAKER_00, etc.)
into actual participant names when that information is available.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, slots=True)
class ResolvedSpeaker:
    """A speaker that has been resolved to a name."""

    speaker_id: str
    name: str


class SpeakerIdentityResolver(ABC):
    """
    Abstract interface for resolving anonymous speaker IDs to names.

    Implementations may integrate with meeting platforms, participant
    lists, or other sources of speaker identity.
    """

    @abstractmethod
    async def resolve(
        self,
        speaker_id: str,
    ) -> Optional[ResolvedSpeaker]:
        """
        Resolve an anonymous speaker ID to a name.

        Args:
            speaker_id:
                Anonymous identifier like "SPEAKER_00".

        Returns:
            A ResolvedSpeaker if identity could be determined, or None.
        """
        raise NotImplementedError


class NoOpSpeakerIdentityResolver(SpeakerIdentityResolver):
    """
    Resolver that never resolves any identities.

    Useful as a default when no identity resolution is available.
    """

    async def resolve(
        self,
        speaker_id: str,
    ) -> Optional[ResolvedSpeaker]:
        """Always returns None."""
        return None


__all__ = [
    "ResolvedSpeaker",
    "SpeakerIdentityResolver",
    "NoOpSpeakerIdentityResolver",
]
