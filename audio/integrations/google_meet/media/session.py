from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Protocol

import httpx

from .client import (
    GoogleMeetMediaClient,
    GoogleMeetMediaConfigurationError,
    GoogleMeetMediaError,
)

_AUDIO_VIRTUAL_SSRC_COUNT = 3
_END_OF_STREAM = object()


class MediaTransport(Protocol):
    """Adapter for Google's official Meet Media API reference client."""

    async def connect(
        self,
        client: GoogleMeetMediaClient,
    ) -> AsyncIterator[object]:
        ...

    async def close(self) -> None:
        ...


class GoogleMeetMediaTransport:
    """Receive live audio using Google's Meet Media API WebRTC contract.

    Google's official reference clients negotiate three receive-only audio
    transceivers, then exchange the SDP offer with
    ``connectActiveConference``.  ``aiortc`` supplies the Python WebRTC
    implementation while this class keeps the signaling and lifecycle
    behavior aligned with that reference client.

    ``aiortc`` is imported only when a connection is attempted so importing
    the Meetly API does not require native WebRTC libraries.  A missing
    dependency produces a configuration error at startup with an actionable
    message.
    """

    API_BASE_URL = "https://meet.googleapis.com/v2beta"

    def __init__(
        self,
        *,
        api_base_url: str = API_BASE_URL,
        request_timeout: float = 30.0,
    ) -> None:
        self.api_base_url = api_base_url.rstrip("/")
        self.request_timeout = request_timeout
        self._peer_connection: Any | None = None
        self._receive_tasks: set[asyncio.Task[Any]] = set()
        self._audio_queue: asyncio.Queue[object] = asyncio.Queue()
        self._connected = False

    async def connect(
        self,
        client: GoogleMeetMediaClient,
    ) -> AsyncIterator[object]:
        if self._connected or self._peer_connection is not None:
            raise GoogleMeetMediaError("Media transport is already connected.")

        try:
            from aiortc import RTCPeerConnection, RTCSessionDescription
        except ImportError as exc:
            raise GoogleMeetMediaConfigurationError(
                "The Google Meet live-audio transport requires aiortc. "
                "Install the project dependencies before starting a "
                "Google Meet recording."
            ) from exc

        self._audio_queue = asyncio.Queue()
        peer_connection = RTCPeerConnection()
        self._peer_connection = peer_connection

        if client.config.receive_audio:
            for _ in range(_AUDIO_VIRTUAL_SSRC_COUNT):
                peer_connection.addTransceiver("audio", direction="recvonly")

        if client.config.receive_video:
            peer_connection.addTransceiver("video", direction="recvonly")

        @peer_connection.on("track")
        def on_track(track: Any) -> None:
            if track.kind != "audio":
                return
            task = asyncio.create_task(self._receive_audio(track))
            self._receive_tasks.add(task)
            task.add_done_callback(self._receive_tasks.discard)

        try:
            offer = await peer_connection.createOffer()
            await peer_connection.setLocalDescription(offer)
            local_description = peer_connection.localDescription
            if local_description is None or not local_description.sdp:
                raise GoogleMeetMediaError(
                    "Google Meet media transport failed to create an SDP offer."
                )

            answer = await self._connect_active_conference(
                client,
                local_description.sdp,
            )
            await peer_connection.setRemoteDescription(
                RTCSessionDescription(sdp=answer, type="answer")
            )
            self._connected = True
            return self._audio_stream()
        except Exception:
            await self.close()
            raise

    async def _connect_active_conference(
        self,
        client: GoogleMeetMediaClient,
        offer: str,
    ) -> str:
        url = (
            f"{self.api_base_url}/{client.space_name}:"
            "connectActiveConference"
        )
        headers = {
            "Authorization": f"Bearer {client.access_token}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(
                timeout=self.request_timeout
            ) as http:
                response = await http.post(
                    url,
                    headers=headers,
                    json={"offer": offer},
                )
        except httpx.HTTPError as exc:
            raise GoogleMeetMediaError(
                f"Google Meet media signaling request failed: {exc}"
            ) from exc

        if response.is_error:
            try:
                detail: object = response.json()
            except ValueError:
                detail = response.text
            raise GoogleMeetMediaError(
                "Google Meet media signaling failed "
                f"({response.status_code}): {detail}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise GoogleMeetMediaError(
                "Google Meet media signaling returned invalid JSON."
            ) from exc

        answer = payload.get("answer") if isinstance(payload, dict) else None
        if not isinstance(answer, str) or not answer:
            raise GoogleMeetMediaError(
                "Google Meet media signaling response did not contain an "
                "SDP answer."
            )
        return answer

    async def _receive_audio(self, track: Any) -> None:
        try:
            while self._peer_connection is not None:
                frame = await track.recv()
                await self._audio_queue.put(frame)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if self._connected:
                await self._audio_queue.put(
                    GoogleMeetMediaError(f"Audio reception failed: {exc}")
                )

    async def _audio_stream(self) -> AsyncIterator[object]:
        while True:
            frame = await self._audio_queue.get()
            if frame is _END_OF_STREAM:
                return
            if isinstance(frame, GoogleMeetMediaError):
                raise frame
            yield frame

    async def close(self) -> None:
        self._connected = False
        peer_connection = self._peer_connection
        self._peer_connection = None

        for task in self._receive_tasks:
            task.cancel()
        if self._receive_tasks:
            await asyncio.gather(*self._receive_tasks, return_exceptions=True)
        self._receive_tasks.clear()

        if peer_connection is not None:
            await peer_connection.close()

        await self._audio_queue.put(_END_OF_STREAM)


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

        if not self.client.config.receive_audio:
            raise GoogleMeetMediaConfigurationError(
                "Google Meet media configuration must enable audio."
            )

        self._audio_queue = asyncio.Queue()
        await self.client.connect()
        try:
            self._frames = await self._transport.connect(self.client)
            self._connected = True
        except Exception:
            await self._transport.close()
            await self.client.close()
            raise

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
                await self._audio_queue.put(
                    GoogleMeetMediaError(f"Audio reception failed: {exc}")
                )

    async def audio_stream(self) -> AsyncIterator[object]:
        if self._frames is None:
            return
        task = asyncio.create_task(self._receive_audio(self._frames))
        try:
            while self._connected:
                frame = await self._audio_queue.get()
                if frame is _END_OF_STREAM:
                    return
                if isinstance(frame, GoogleMeetMediaError):
                    raise frame
                yield frame
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def close(self) -> None:
        self._connected = False
        self._frames = None
        if self._transport is not None:
            await self._transport.close()
        await self.client.close()
        await self._audio_queue.put(_END_OF_STREAM)

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