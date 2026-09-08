from __future__ import annotations

from meetly.audio.processing.diarization.diarizer import Diarizer
from meetly.audio.processing.diarization.engine import (
    AcousticDiarizationEngine,
)
from meetly.audio.processing.live_transcription.transcriber import (
    Transcriber,
)
from meetly.audio.processing.live_transcription.whisper import (
    WhisperEngine,
)
from meetly.audio.processing.transcript.assembler import (
    TranscriptAssembler,
)
from meetly.llm import LLMClient
from meetly.core.meeting import Meeting
from meetly.audio.integrations.google_meet import GoogleMeetProvider
from meetly.audio.integrations.google_meet import MediaTransport
from config import settings


def create_meeting(
    *,
    provider: str = "local",
    meeting_url: str | None = None,
    media_transport: MediaTransport | None = None,
) -> Meeting:
    whisper_engine = WhisperEngine()

    transcriber = Transcriber(
        engine=whisper_engine,
    )

    diarization_engine = AcousticDiarizationEngine()

    diarizer = Diarizer(
        engine=diarization_engine,
    )

    assembler = TranscriptAssembler()
    llm = LLMClient()

    audio_source = None
    if provider == "google_meet":
        if not meeting_url:
            raise ValueError(
                "meeting_url is required for the google_meet provider."
            )
        audio_source = GoogleMeetProvider(
            meeting_url=meeting_url,
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            refresh_token=settings.GOOGLE_REFRESH_TOKEN,
            media_transport=media_transport,
        )
    elif provider != "local":
        raise ValueError(f"Unsupported meeting provider: {provider}.")

    return Meeting(
        transcriber=transcriber,
        diarizer=diarizer,
        assembler=assembler,
        llm=llm,
        audio_source=audio_source,
        provider=provider,
        meeting_url=meeting_url,
    )


__all__ = [
    "create_meeting",
]