"""
Integration tests for the Meetly Meeting orchestration layer.

External services are mocked:
- no OpenRouter API call
- no Whisper model
- no real microphone
- no real diarization backend
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from meetly import Meeting
from meetly.audio.recorder.models import (
    AudioChunk,
    AudioFormat,
    SpeakerSegment,
    TranscriptChunk,
)
from meetly.audio.processing.diarization.diarizer import (
    DiarizationEngine,
    Diarizer,
)
from meetly.audio.processing.live_transcription.transcriber import (
    Transcriber,
    TranscriptionEngine,
)
from meetly.audio.processing.transcript import (
    TranscriptAssembler,
)
from meetly.core.meeting import (
    MeetingState,
)


def make_audio_chunk() -> AudioChunk:
    return AudioChunk(
        data=b"\x00\x00" * 1600,
        sample_rate=16000,
        channels=1,
        format=AudioFormat.PCM16,
        timestamp=datetime.utcnow(),
        source="test",
    )


class FakeTranscriptionEngine(
    TranscriptionEngine
):
    """Produces one deterministic transcript."""

    async def transcribe(
        self,
        audio: AudioChunk,
    ) -> TranscriptChunk:
        return TranscriptChunk(
            text=(
                "Rohit: We will launch "
                "the beta on September 30."
            ),
            start_time=0.0,
            end_time=2.0,
            is_final=True,
        )


class FakeDiarizationEngine(
    DiarizationEngine
):
    """Produces one deterministic speaker segment."""

    async def diarize(
        self,
        audio: AudioChunk,
    ) -> list[SpeakerSegment]:
        return [
            SpeakerSegment(
                speaker_id="SPEAKER_00",
                start_time=0.0,
                end_time=2.0,
                confidence=0.95,
            )
        ]


class FakeLLM:
    """
    Deterministic LLM replacement.

    It records prompts and returns predictable responses.
    """

    def __init__(self) -> None:
        self.calls: list[
            tuple[str, str]
        ] = []

    async def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        self.calls.append(
            (
                system_prompt,
                user_prompt,
            )
        )

        if "Summarize" in user_prompt:
            return (
                "- Beta launch: September 30."
            )

        return (
            "The beta will launch "
            "on September 30."
        )


@pytest.fixture
def meeting_components():
    transcriber = Transcriber(
        engine=FakeTranscriptionEngine()
    )

    diarizer = Diarizer(
        engine=FakeDiarizationEngine()
    )

    assembler = TranscriptAssembler()

    llm = FakeLLM()

    meeting = Meeting(
        transcriber=transcriber,
        diarizer=diarizer,
        assembler=assembler,
        llm=llm,
    )

    return (
        meeting,
        assembler,
        llm,
    )


@pytest.mark.asyncio
async def test_meeting_lifecycle(
    meeting_components,
):
    meeting, _, _ = meeting_components

    assert meeting.state is MeetingState.IDLE
    assert not meeting.running

    await meeting.start()

    assert meeting.state is MeetingState.RUNNING
    assert meeting.running

    await meeting.stop()

    assert meeting.state is MeetingState.STOPPED
    assert not meeting.running


@pytest.mark.asyncio
async def test_meeting_processes_audio_into_transcript(
    meeting_components,
):
    meeting, _, _ = meeting_components

    await meeting.start()

    await meeting.submit_audio(
        make_audio_chunk()
    )

    await asyncio.sleep(0.1)

    transcript = await meeting.stop()

    assert transcript

    assert (
        "September 30"
        in transcript
    )


@pytest.mark.asyncio
async def test_meeting_assigns_speaker_to_transcript(
    meeting_components,
):
    meeting, _, _ = meeting_components

    await meeting.start()

    await meeting.submit_audio(
        make_audio_chunk()
    )

    await asyncio.sleep(0.1)

    await meeting.stop()

    assert meeting.entries

    entry = meeting.entries[0]

    assert (
        entry.speaker_id
        == "SPEAKER_00"
    )

    assert (
        "September 30"
        in entry.text
    )


@pytest.mark.asyncio
async def test_meeting_rejects_audio_before_start(
    meeting_components,
):
    meeting, _, _ = meeting_components

    with pytest.raises(
        RuntimeError
    ):
        await meeting.submit_audio(
            make_audio_chunk()
        )


@pytest.mark.asyncio
async def test_meeting_summary_uses_llm(
    meeting_components,
):
    meeting, _, llm = meeting_components

    await meeting.start()

    await meeting.submit_audio(
        make_audio_chunk()
    )

    await asyncio.sleep(0.1)

    await meeting.stop()

    summary = await meeting.summary()

    assert summary

    assert (
        "September 30"
        in summary
    )

    assert len(llm.calls) >= 1