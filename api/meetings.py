from fastapi import APIRouter, HTTPException

from api.meeting_factory import create_meeting
from api.meeting_manager import (
    MeetingManager,
    MeetingNotFoundError,
)
from api.schemas.meeting import (
    AskRequest,
    AskResponse,
    CreateMeetingRequest,
    CreateMeetingResponse,
    MeetingProvider,
    MeetingResponse,
    MeetingStateResponse,
    SummaryResponse,
    TranscriptResponse,
)


router = APIRouter(
    prefix="/meetings",
    tags=["meetings"],
)

manager = MeetingManager()


@router.post(
    "",
    response_model=CreateMeetingResponse,
)
async def create_new_meeting(
    request: CreateMeetingRequest | None = None,
) -> CreateMeetingResponse:
    """Create and register a new Meetly meeting."""

    try:
        request = request or CreateMeetingRequest()
        meeting = create_meeting(
            provider=request.provider.value,
            meeting_url=request.meeting_url,
        )
        meeting_id = manager.create(meeting)

        return CreateMeetingResponse(
            meeting_id=meeting_id,
            state=MeetingStateResponse.IDLE,
            provider=MeetingProvider(meeting.provider),
        )

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Failed to create meeting.",
        ) from exc


@router.get(
    "/{meeting_id}",
    response_model=MeetingResponse,
)
async def get_meeting(
    meeting_id: str,
) -> MeetingResponse:
    """Return the current state of a meeting."""

    try:
        meeting = manager.get(meeting_id)

    except MeetingNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    return MeetingResponse(
        meeting_id=meeting_id,
        state=MeetingStateResponse(
            meeting.state.value
        ),
        running=meeting.running,
        provider=MeetingProvider(meeting.provider),
    )


@router.post(
    "/{meeting_id}/start",
    response_model=MeetingResponse,
)
async def start_meeting(
    meeting_id: str,
) -> MeetingResponse:
    """Start a registered meeting."""

    try:
        meeting = manager.get(meeting_id)

    except MeetingNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    try:
        await meeting.start()

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return MeetingResponse(
        meeting_id=meeting_id,
        state=MeetingStateResponse(
            meeting.state.value
        ),
        running=meeting.running,
        provider=MeetingProvider(meeting.provider),
    )


@router.post(
    "/{meeting_id}/stop",
    response_model=MeetingResponse,
)
async def stop_meeting(
    meeting_id: str,
) -> MeetingResponse:
    """Stop a registered meeting."""

    try:
        meeting = manager.get(meeting_id)

    except MeetingNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    try:
        await meeting.stop()

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return MeetingResponse(
        meeting_id=meeting_id,
        state=MeetingStateResponse(
            meeting.state.value
        ),
        running=meeting.running,
        provider=MeetingProvider(meeting.provider),
    )


@router.get(
    "/{meeting_id}/transcript",
    response_model=TranscriptResponse,
)
async def get_transcript(
    meeting_id: str,
) -> TranscriptResponse:
    """Return the finalized transcript of a meeting."""

    try:
        meeting = manager.get(meeting_id)

    except MeetingNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    return TranscriptResponse(
        meeting_id=meeting_id,
        transcript=meeting.transcript,
    )


@router.get(
    "/{meeting_id}/summary",
    response_model=SummaryResponse,
)
async def get_summary(
    meeting_id: str,
) -> SummaryResponse:
    """Generate and return a meeting summary."""

    try:
        meeting = manager.get(meeting_id)

    except MeetingNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    try:
        summary = await meeting.summary()

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return SummaryResponse(
        meeting_id=meeting_id,
        summary=summary,
    )


@router.post(
    "/{meeting_id}/ask",
    response_model=AskResponse,
)
async def ask_meeting(
    meeting_id: str,
    request: AskRequest,
) -> AskResponse:
    """Ask a question about the finalized meeting."""

    try:
        meeting = manager.get(meeting_id)

    except MeetingNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    try:
        answer = await meeting.ask(
            request.question
        )

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return AskResponse(
        meeting_id=meeting_id,
        question=request.question,
        answer=answer,
    )