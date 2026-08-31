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


def create_meeting() -> Meeting:
    """
    Create a fully configured Meeting instance.

    The factory owns construction of the concrete processing
    components while Meeting remains responsible for orchestration.
    """

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

    return Meeting(
        transcriber=transcriber,
        diarizer=diarizer,
        assembler=assembler,
        llm=llm,
    )


__all__ = [
    "create_meeting",
]