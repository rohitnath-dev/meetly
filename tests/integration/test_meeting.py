import pytest

from meetly import Meeting
from meetly.audio.processing.transcript import TranscriptAssembler
from meetly.audio.processing.diarization import Diarizer
from meetly.audio.processing.transcription import Transcriber
from meetly.llm import LLMClient


@pytest.mark.asyncio
async def test_meeting_ai_flow():
    llm = LLMClient()

    transcriber = Transcriber(...)
    diarizer = Diarizer(...)
    assembler = TranscriptAssembler()

    meeting = Meeting(
        transcriber=transcriber,
        diarizer=diarizer,
        assembler=assembler,
        llm=llm,
    )

    transcript = """
    Rohit: We will launch the beta on September 30.
    Rahul: I will finish the backend integration before September 25.
    Rohit: The backend will use PostgreSQL.
    """

    # Temporary transcript injection for AI integration testing.
    assembler._entries = [
        transcript,
    ]

    summary = await meeting.summary()

    answer = await meeting.ask(
        "When will the beta launch?"
    )

    assert summary
    assert answer