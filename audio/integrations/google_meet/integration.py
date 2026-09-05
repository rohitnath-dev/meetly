from __future__ import annotations

from .client import GoogleMeetMediaClient
from .session import MediaSession
from .audio_source import GoogleMeetAudioSource


class GoogleMeetMediaIntegration:
    def __init__(self, client: GoogleMeetMediaClient) -> None:
        self.client = client
        self.session = MediaSession(client)
        self.audio_source = GoogleMeetAudioSource(self.session)

    async def start(self) -> GoogleMeetAudioSource:
        await self.session.connect()
        await self.audio_source.start()
        return self.audio_source

    async def stop(self) -> None:
        await self.audio_source.stop()
        await self.session.close()

    @property
    def is_running(self) -> bool:
        return self.audio_source._running