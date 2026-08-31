from __future__ import annotations

from threading import Lock
from uuid import uuid4

from meetly.core.meeting import Meeting


class MeetingNotFoundError(KeyError):
    """Raised when a meeting ID does not exist."""


class MeetingManager:
    """
    In-memory registry for active and completed Meetly meetings.

    The manager does not construct Meeting dependencies itself.
    A Meeting instance is supplied by the caller.
    """

    def __init__(self) -> None:
        self._meetings: dict[str, Meeting] = {}
        self._lock = Lock()

    def create(self, meeting: Meeting) -> str:
        """
        Register a Meeting and return its unique ID.
        """

        if not isinstance(meeting, Meeting):
            raise TypeError(
                "meeting must be a Meeting instance."
            )

        meeting_id = f"mtg_{uuid4().hex}"

        with self._lock:
            self._meetings[meeting_id] = meeting

        return meeting_id

    def get(self, meeting_id: str) -> Meeting:
        """
        Return a registered Meeting by ID.
        """

        if not isinstance(meeting_id, str):
            raise TypeError(
                "meeting_id must be a string."
            )

        with self._lock:
            meeting = self._meetings.get(meeting_id)

        if meeting is None:
            raise MeetingNotFoundError(
                f"Meeting '{meeting_id}' was not found."
            )

        return meeting

    def exists(self, meeting_id: str) -> bool:
        """Return whether a meeting ID is registered."""

        if not isinstance(meeting_id, str):
            return False

        with self._lock:
            return meeting_id in self._meetings

    def remove(self, meeting_id: str) -> None:
        """
        Remove a meeting from the registry.
        """

        if not isinstance(meeting_id, str):
            raise TypeError(
                "meeting_id must be a string."
            )

        with self._lock:
            if meeting_id not in self._meetings:
                raise MeetingNotFoundError(
                    f"Meeting '{meeting_id}' was not found."
                )

            del self._meetings[meeting_id]

    def count(self) -> int:
        """Return the number of registered meetings."""

        with self._lock:
            return len(self._meetings)


__all__ = [
    "MeetingManager",
    "MeetingNotFoundError",
]