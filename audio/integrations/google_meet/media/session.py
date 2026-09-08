from __future__ import annotations

import asyncio
from typing import AsyncIterator, Protocol

from .client import (
    GoogleMeetMediaClient,
    GoogleMeetMediaConfigurationError,
    GoogleMeetMediaError,
)


class MediaTransport(Protocol):
    """Adapter for Google's official Meet Media API reference client."""

    async def connect(
        self,
        client: GoogleMeetMediaClient,
    ) -> AsyncIterator[object]:
        ...

    async def close(self) -> None:
        ...


class MediaSession:
    def __init__(
        self,
        client: GoogleMeetMediaClient,
        transport: MediaTransport | None = None,
    ) -> None:
        self.client = client
        self._transport = transport
        self._frames: AsyncIterator[object] | None = None
        self._audio_queue: asyncio.Queue = asyncio.Queue()
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        if self._connected:
            raise GoogleMeetMediaError("Media session is already connected.")

        if self._transport is None:
            raise GoogleMeetMediaConfigurationError(
                "Google Meet Media API access is not available in this "
                "runtime. Enroll the Google Cloud project and OAuth "
                "principal in the Meet Media API Developer Preview, then "
                "provide a transport built from Google's official Media API "
                "reference client. The REST API cannot receive live audio, "
                "so Meetly will not use browser automation or undocumented "
                "signaling."
            )

        await self.client.connect()
        self._frames = await self._transport.connect(self.client)
        if not self.client.config.receive_audio:
            raise GoogleMeetMediaConfigurationError(
                "Google Meet media configuration must enable audio."
            )
        self._connected = True

    async def _receive_audio(self, frames: AsyncIterator[object]) -> None:
        try:
            async for frame in frames:
                if not self._connected:
                    break
                await self._audio_queue.put(frame)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if self._connected:
                raise GoogleMeetMediaError(
                    f"Audio reception failed: {exc}"
                ) from exc

    async def audio_stream(self) -> AsyncIterator[object]:
        if self._frames is None:
            return
        task = asyncio.create_task(self._receive_audio(self._frames))
        try:
            while self._connected:
                yield await self._audio_queue.get()
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def close(self) -> None:
        self._connected = False
        self._frames = None
        if self._transport is not None:
            await self._transport.close()
        await self.client.close()

        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def __aenter__(self) -> "MediaSession":
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        await self.close()