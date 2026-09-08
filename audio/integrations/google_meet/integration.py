from __future__ import annotations

from urllib.parse import urlparse

from meetly.audio.recorder.source import AudioSource

from .auth import GoogleMeetAuth
from .media.client import GoogleMeetMediaClient, GoogleMeetMediaConfig
from .media.session import MediaSession, MediaTransport
from .media.audio_source import GoogleMeetAudioSource


class GoogleMeetMediaIntegration:
    def __init__(
        self,
        client: GoogleMeetMediaClient,
        transport: MediaTransport | None = None,
    ) -> None:
        self.client = client
        self.session = MediaSession(client, transport=transport)
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


class GoogleMeetProvider(AudioSource):
    """Lazy Google Meet provider backed by Meet Media API audio."""

    def __init__(
        self,
        *,
        meeting_url: str,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        media_transport: MediaTransport | None = None,
    ) -> None:
        self.meeting_url = meeting_url
        self._google_credentials = (
            client_id,
            client_secret,
            refresh_token,
        )
        self._auth: GoogleMeetAuth | None = None
        self._media_transport = media_transport
        self._integration: GoogleMeetMediaIntegration | None = None
        self._source: GoogleMeetAudioSource | None = None

    @property
    def name(self) -> str:
        return "google_meet"

    @property
    def is_running(self) -> bool:
        return bool(self._source and self._source._running)

    async def start(self) -> None:
        if self.is_running:
            return

        self._auth = GoogleMeetAuth(*self._google_credentials)
        access_token = await self._auth.get_access_token()
        config = GoogleMeetMediaConfig(
            access_token=access_token,
            space_name=space_name_from_url(self.meeting_url),
        )
        media_client = GoogleMeetMediaClient(config)
        self._integration = GoogleMeetMediaIntegration(
            media_client,
            transport=self._media_transport,
        )
        self._source = await self._integration.start()

    async def stop(self) -> None:
        if self._integration is not None:
            await self._integration.stop()
        self._source = None
        self._integration = None

    async def stream(self):
        if self._source is None:
            raise RuntimeError("Google Meet provider is not running.")
        async for chunk in self._source.stream():
            yield chunk


def space_name_from_url(meeting_url: str) -> str:
    """Convert a Meet URL or resource name into a Media API space name."""
    value = meeting_url.strip()
    if value.startswith("spaces/"):
        return value

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.netloc != "meet.google.com":
        raise ValueError(
            "meeting_url must be a Google Meet URL or a spaces/{name} resource."
        )

    code = parsed.path.strip("/").split("/", 1)[0]
    if not code:
        raise ValueError("meeting_url must contain a Google Meet code.")
    return f"spaces/{code}"