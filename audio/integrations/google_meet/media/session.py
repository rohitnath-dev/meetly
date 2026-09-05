from __future__ import annotations

import asyncio
from typing import AsyncIterator

import httpx
from aiortc import RTCPeerConnection, RTCSessionDescription

from .client import GoogleMeetMediaClient, GoogleMeetMediaError


class MediaSession:
    def __init__(self, client: GoogleMeetMediaClient) -> None:
        self.client = client
        self.pc: RTCPeerConnection | None = None
        self._audio_queue: asyncio.Queue = asyncio.Queue()
        self._tasks: set[asyncio.Task] = set()
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        if self._connected:
            raise GoogleMeetMediaError("Media session is already connected.")

        self.pc = RTCPeerConnection()

        if self.client.config.receive_audio:
            self.pc.addTransceiver("audio", direction="recvonly")

        if self.client.config.receive_video:
            self.pc.addTransceiver("video", direction="recvonly")

        @self.pc.on("track")
        def on_track(track) -> None:
            if track.kind == "audio":
                task = asyncio.create_task(self._receive_audio(track))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)

        offer = await self.pc.createOffer()
        await self.pc.setLocalDescription(offer)

        if self.pc.localDescription is None:
            raise GoogleMeetMediaError("Failed to create local SDP.")

        answer = await self._connect_active_conference(
            self.pc.localDescription.sdp
        )

        await self.pc.setRemoteDescription(
            RTCSessionDescription(
                sdp=answer,
                type="answer",
            )
        )

        self._connected = True

    async def _connect_active_conference(self, offer: str) -> str:
        url = (
            "https://meet.googleapis.com/v2beta/"
            f"{self.client.space_name}:connectActiveConference"
        )

        headers = {
            "Authorization": f"Bearer {self.client.access_token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30) as http:
            response = await http.post(
                url,
                headers=headers,
                json={"offer": offer},
            )

        if response.is_error:
            raise GoogleMeetMediaError(
                f"{response.status_code}: {response.text}"
            )

        data = response.json()

        if "answer" not in data:
            raise GoogleMeetMediaError(
                "Google Meet did not return an SDP answer."
            )

        return data["answer"]

    async def _receive_audio(self, track) -> None:
        while self._connected:
            try:
                frame = await track.recv()
                await self._audio_queue.put(frame)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                if self._connected:
                    raise GoogleMeetMediaError(
                        f"Audio reception failed: {exc}"
                    ) from exc
                break

    async def audio_stream(self) -> AsyncIterator:
        while self._connected:
            yield await self._audio_queue.get()

    async def close(self) -> None:
        self._connected = False

        for task in self._tasks:
            task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks.clear()

        if self.pc is not None:
            await self.pc.close()
            self.pc = None

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