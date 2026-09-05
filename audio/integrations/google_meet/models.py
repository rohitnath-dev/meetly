from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class GoogleMeetSpace:
    name: str
    meeting_uri: str | None = None
    meeting_code: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GoogleMeetSpace":
        return cls(
            name=data["name"],
            meeting_uri=data.get("meetingUri"),
            meeting_code=data.get("meetingCode"),
        )


@dataclass(slots=True)
class GoogleMeetConference:
    name: str
    space: str | None = None
    start_time: str | None = None
    end_time: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GoogleMeetConference":
        return cls(
            name=data["name"],
            space=data.get("space"),
            start_time=data.get("startTime"),
            end_time=data.get("endTime"),
        )


@dataclass(slots=True)
class GoogleMeetParticipant:
    name: str
    display_name: str | None = None
    signedin_user: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GoogleMeetParticipant":
        signedin_user = data.get("signedinUser")

        if isinstance(signedin_user, dict):
            signedin_user = signedin_user.get("user")

        return cls(
            name=data["name"],
            display_name=data.get("displayName"),
            signedin_user=signedin_user,
        )


@dataclass(slots=True)
class GoogleMeetTranscriptResource:
    name: str
    state: str | None = None
    start_time: str | None = None
    end_time: str | None = None

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> "GoogleMeetTranscriptResource":
        return cls(
            name=data["name"],
            state=data.get("state"),
            start_time=data.get("startTime"),
            end_time=data.get("endTime"),
        )