from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class MeetingStateResponse(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class MeetingProvider(str, Enum):
    LOCAL = "local"
    GOOGLE_MEET = "google_meet"


class CreateMeetingRequest(BaseModel):
    provider: MeetingProvider = MeetingProvider.LOCAL
    meeting_url: str | None = Field(
        default=None,
        description="Google Meet URL when provider is google_meet.",
    )


class CreateMeetingResponse(BaseModel):
    meeting_id: str = Field(
        ...,
        description="Unique identifier of the meeting.",
    )
    state: MeetingStateResponse
    provider: MeetingProvider = MeetingProvider.LOCAL


class MeetingResponse(BaseModel):
    meeting_id: str
    state: MeetingStateResponse
    running: bool
    provider: MeetingProvider = MeetingProvider.LOCAL


class TranscriptResponse(BaseModel):
    meeting_id: str
    transcript: str


class SummaryResponse(BaseModel):
    meeting_id: str
    summary: str


class AskRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=1,
        description="Question to ask about the finalized meeting.",
    )


class AskResponse(BaseModel):
    meeting_id: str
    question: str
    answer: str


__all__ = [
    "MeetingStateResponse",
    "MeetingProvider",
    "CreateMeetingRequest",
    "CreateMeetingResponse",
    "MeetingResponse",
    "TranscriptResponse",
    "SummaryResponse",
    "AskRequest",
    "AskResponse",
]