from __future__ import annotations

from datetime import datetime
from typing import AsyncIterator

import numpy as np
from av import AudioFrame

from meetly.audio.recorder.models import AudioChunk, AudioFormat
from meetly.audio.recorder.source import AudioSource

from .session import MediaSession


class GoogleMeetAudioSource(AudioSource):
    def __init__(self, session: MediaSession) -> None:
        self.session = session
        self._running = False

    @property
    def name(self) -> str:
        return "google_meet"

    async def start(self) -> None:
        if self._running:
            return

        if not self.session.is_connected:
            await self.session.connect()

        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def stream(self) -> AsyncIterator[AudioChunk]:
        if not self._running:
            raise RuntimeError("Google Meet audio source is not running.")

        async for frame in self.session.audio_stream():
            if not self._running:
                break

            yield self._frame_to_chunk(frame)

    def _frame_to_chunk(self, frame: AudioFrame) -> AudioChunk:
        array = frame.to_ndarray()

        if array.ndim == 2:
            array = np.asarray(array)
            data = array.T.astype(np.int16).tobytes()
            channels = array.shape[0]
        else:
            data = np.asarray(array).astype(np.int16).tobytes()
            channels = 1

        return AudioChunk(
            data=data,
            sample_rate=frame.sample_rate,
            channels=channels,
            format=AudioFormat.PCM16,
            timestamp=datetime.utcnow(),
            source=self.name,
        )