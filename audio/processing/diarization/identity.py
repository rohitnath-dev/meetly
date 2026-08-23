"""
Speaker identity resolution for Meetly.

Diarization and identity resolution are intentionally separate.

Diarization answers:

    "Which parts of the audio belong to the same speaker?"

Identity resolution answers:

    "Which known participant does this speaker correspond to?"

The resolver supports several identity sources:

    1. Explicit participant/source mappings.
    2. Participant metadata supplied by the host application.
    3. Optional pre-enrolled voice identity providers.

If no reliable identity is available, the original anonymous speaker ID
is preserved.

This makes the module usable both inside Meetly and as a standalone
component imported by third-party applications.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional


class IdentityResolutionError(RuntimeError):
    """Base exception for speaker identity resolution failures."""


@dataclass(frozen=True, slots=True)
class Participant:
    """
    A known meeting participant.

    Attributes:
        participant_id:
            Stable identifier supplied by the host application.

        name:
            Human-readable participant name.

        source:
            Optional audio/source identifier associated with the
            participant.
    """

    participant_id: str
    name: str
    source: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.participant_id:
            raise ValueError(
                "participant_id cannot be empty."
            )

        if not self.name:
            raise ValueError(
                "name cannot be empty."
            )


class SpeakerIdentityResolver(ABC):
    """
    Abstract interface for resolving anonymous speaker IDs.

    Implementations can use participant metadata, explicit mappings,
    voice identity systems, or another identity provider.

    The resolver must return None when identity cannot be established
    reliably. It must not invent a participant name.
    """

    @abstractmethod
    async def resolve(
        self,
        speaker_id: str,
    ) -> Optional[Participant]:
        """
        Resolve an anonymous speaker ID.

        Args:
            speaker_id:
                Identifier produced by the diarization layer.

        Returns:
            A known Participant when identity is available,
            otherwise None.
        """

        raise NotImplementedError


class ParticipantRegistry(SpeakerIdentityResolver):
    """
    In-memory participant registry.

    This is the default identity resolver.

    It is intentionally simple and dependency-free so external
    applications can populate it from their own meeting/user system.

    Example:

        registry = ParticipantRegistry()

        registry.register(
            Participant(
                participant_id="user_123",
                name="Rohit",
            )
        )

        registry.bind_speaker(
            "SPEAKER_00",
            "user_123",
        )

    After binding:

        SPEAKER_00 → Rohit
    """

    def __init__(
        self,
        participants: Optional[
            Iterable[Participant]
        ] = None,
    ) -> None:
        self._participants: Dict[
            str,
            Participant,
        ] = {}

        self._speaker_bindings: Dict[
            str,
            str,
        ] = {}

        self._source_bindings: Dict[
            str,
            str,
        ] = {}

        if participants is not None:
            for participant in participants:
                self.register(participant)

    # ------------------------------------------------------------------
    # Participant management
    # ------------------------------------------------------------------

    def register(
        self,
        participant: Participant,
    ) -> None:
        """
        Register or replace a participant.
        """

        self._participants[
            participant.participant_id
        ] = participant

        if participant.source:
            self.bind_source(
                participant.source,
                participant.participant_id,
            )

    def unregister(
        self,
        participant_id: str,
    ) -> None:
        """
        Remove a participant and its associated bindings.
        """

        self._participants.pop(
            participant_id,
            None,
        )

        self._speaker_bindings = {
            speaker_id: bound_id
            for speaker_id, bound_id
            in self._speaker_bindings.items()
            if bound_id != participant_id
        }

        self._source_bindings = {
            source: bound_id
            for source, bound_id
            in self._source_bindings.items()
            if bound_id != participant_id
        }

    def get(
        self,
        participant_id: str,
    ) -> Optional[Participant]:
        """Return a participant by ID."""

        return self._participants.get(
            participant_id
        )

    def participants(self) -> List[Participant]:
        """Return all registered participants."""

        return list(
            self._participants.values()
        )

    # ------------------------------------------------------------------
    # Speaker bindings
    # ------------------------------------------------------------------

    def bind_speaker(
        self,
        speaker_id: str,
        participant_id: str,
    ) -> None:
        """
        Explicitly associate a diarization speaker with a participant.

        This is the most deterministic form of identity resolution.
        """

        if not speaker_id:
            raise ValueError(
                "speaker_id cannot be empty."
            )

        if participant_id not in self._participants:
            raise IdentityResolutionError(
                f"Unknown participant: {participant_id}"
            )

        self._speaker_bindings[
            speaker_id
        ] = participant_id

    def unbind_speaker(
        self,
        speaker_id: str,
    ) -> None:
        """Remove an explicit speaker binding."""

        self._speaker_bindings.pop(
            speaker_id,
            None,
        )

    # ------------------------------------------------------------------
    # Source bindings
    # ------------------------------------------------------------------

    def bind_source(
        self,
        source: str,
        participant_id: str,
    ) -> None:
        """
        Associate an audio source with a known participant.

        This is useful when the host application knows which source
        belongs to which participant.
        """

        if not source:
            raise ValueError(
                "source cannot be empty."
            )

        if participant_id not in self._participants:
            raise IdentityResolutionError(
                f"Unknown participant: {participant_id}"
            )

        self._source_bindings[
            source
        ] = participant_id

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    async def resolve(
        self,
        speaker_id: str,
    ) -> Optional[Participant]:
        """
        Resolve a speaker using an explicit speaker binding.

        Returns None when the speaker is currently anonymous.
        """

        participant_id = self._speaker_bindings.get(
            speaker_id
        )

        if participant_id is None:
            return None

        return self._participants.get(
            participant_id
        )

    async def resolve_source(
        self,
        source: str,
    ) -> Optional[Participant]:
        """
        Resolve a participant from an audio source.
        """

        participant_id = self._source_bindings.get(
            source
        )

        if participant_id is None:
            return None

        return self._participants.get(
            participant_id
        )


@dataclass(frozen=True, slots=True)
class ResolvedSpeaker:
    """
    Result of speaker identity resolution.

    `name` is None when the speaker could not be reliably identified.
    In that case consumers should continue displaying `speaker_id`.
    """

    speaker_id: str
    name: Optional[str]
    participant_id: Optional[str] = None

    @property
    def display_name(self) -> str:
        """
        Return the best available display name.

        Known speaker:
            "Rohit"

        Unknown speaker:
            "SPEAKER_00"
        """

        return self.name or self.speaker_id


class SpeakerAttributor:
    """
    Converts anonymous SpeakerSegment objects into resolved speaker
    identities.

    This class does not perform diarization itself.
    """

    def __init__(
        self,
        resolver: SpeakerIdentityResolver,
    ) -> None:
        self._resolver = resolver

    async def resolve_speaker(
        self,
        speaker_id: str,
    ) -> ResolvedSpeaker:
        """
        Resolve one speaker ID into a displayable identity.
        """

        participant = await self._resolver.resolve(
            speaker_id
        )

        if participant is None:
            return ResolvedSpeaker(
                speaker_id=speaker_id,
                name=None,
            )

        return ResolvedSpeaker(
            speaker_id=speaker_id,
            name=participant.name,
            participant_id=participant.participant_id,
        )


__all__ = [
    "IdentityResolutionError",
    "Participant",
    "ResolvedSpeaker",
    "SpeakerIdentityResolver",
    "ParticipantRegistry",
    "SpeakerAttributor",
]