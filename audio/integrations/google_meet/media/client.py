from __future__ import annotations

from dataclasses import dataclass


class GoogleMeetMediaError(RuntimeError):
    pass


class GoogleMeetMediaConfigurationError(GoogleMeetMediaError):
    pass


@dataclass(frozen=True, slots=True)
class GoogleMeetMediaConfig:
    access_token: str
    space_name: str
    receive_audio: bool = True
    receive_video: bool = False

    def __post_init__(self) -> None:
        if not self.access_token.strip():
            raise GoogleMeetMediaConfigurationError(
                "Google Meet media access token is required."
            )

        if not self.space_name.strip():
            raise GoogleMeetMediaConfigurationError(
                "Google Meet space name is required."
            )


class GoogleMeetMediaClient:
    def __init__(self, config: GoogleMeetMediaConfig) -> None:
        self._config = config
        self._connected = False

    @property
    def config(self) -> GoogleMeetMediaConfig:
        return self._config

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def access_token(self) -> str:
        return self._config.access_token

    @property
    def space_name(self) -> str:
        return self._config.space_name

    async def connect(self) -> None:
        if self._connected:
            raise GoogleMeetMediaError(
                "Google Meet media client is already connected."
            )

        self._connected = True

    async def close(self) -> None:
        self._connected = False

    async def __aenter__(self) -> "GoogleMeetMediaClient":
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        await self.close()