from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest

from audio.integrations.google_meet.media.client import (
    GoogleMeetMediaClient,
    GoogleMeetMediaConfig,
)
from audio.integrations.google_meet.media.session import (
    GoogleMeetMediaTransport,
    MediaSession,
)


class FakePeerConnection:
    instances: list["FakePeerConnection"] = []

    def __init__(self) -> None:
        self.transceivers: list[tuple[str, str]] = []
        self.localDescription = None
        self.remote_description = None
        self.closed = False
        self.track_handler = None
        self.__class__.instances.append(self)

    def addTransceiver(self, kind: str, *, direction: str) -> None:
        self.transceivers.append((kind, direction))

    def on(self, event: str):
        assert event == "track"

        def decorator(callback):
            self.track_handler = callback
            return callback

        return decorator

    async def createOffer(self):
        return SimpleNamespace(sdp="fake-offer")

    async def setLocalDescription(self, description) -> None:
        self.localDescription = description

    async def setRemoteDescription(self, description) -> None:
        self.remote_description = description

    async def close(self) -> None:
        self.closed = True


class FakeAsyncClient:
    response = SimpleNamespace(
        is_error=False,
        status_code=200,
        json=lambda: {"answer": "fake-answer"},
    )
    requests: list[dict] = []

    def __init__(self, **kwargs) -> None:
        self.timeout = kwargs["timeout"]

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        return None

    async def post(self, url, *, headers, json):
        self.__class__.requests.append(
            {"url": url, "headers": headers, "json": json}
        )
        return self.response


@pytest.fixture
def fake_webrtc(monkeypatch):
    FakePeerConnection.instances.clear()
    fake_aiortc = ModuleType("aiortc")
    fake_aiortc.RTCPeerConnection = FakePeerConnection
    fake_aiortc.RTCSessionDescription = (
        lambda *, sdp, type: SimpleNamespace(sdp=sdp, type=type)
    )
    monkeypatch.setitem(sys.modules, "aiortc", fake_aiortc)
    monkeypatch.setattr(
        "audio.integrations.google_meet.media.session.httpx.AsyncClient",
        FakeAsyncClient,
    )
    FakeAsyncClient.requests.clear()


@pytest.mark.asyncio
async def test_transport_matches_reference_client_signaling(fake_webrtc):
    client = GoogleMeetMediaClient(
        GoogleMeetMediaConfig(
            access_token="access-token",
            space_name="spaces/abc-defg-hij",
        )
    )
    transport = GoogleMeetMediaTransport(api_base_url="https://meet.test/v2beta")

    await client.connect()
    frames = await transport.connect(client)

    peer_connection = FakePeerConnection.instances[0]
    assert peer_connection.transceivers == [
        ("audio", "recvonly"),
        ("audio", "recvonly"),
        ("audio", "recvonly"),
    ]
    assert peer_connection.remote_description.sdp == "fake-answer"
    assert FakeAsyncClient.requests == [
        {
            "url": (
                "https://meet.test/v2beta/spaces/abc-defg-hij:"
                "connectActiveConference"
            ),
            "headers": {
                "Authorization": "Bearer access-token",
                "Content-Type": "application/json",
            },
            "json": {"offer": "fake-offer"},
        }
    ]

    await transport.close()
    await client.close()
    with pytest.raises(StopAsyncIteration):
        await frames.__anext__()
    assert peer_connection.closed is True


@pytest.mark.asyncio
async def test_media_session_closes_client_when_transport_fails():
    class FailingTransport:
        async def connect(self, client):
            raise RuntimeError("enrollment required")

        async def close(self) -> None:
            return None

    client = GoogleMeetMediaClient(
        GoogleMeetMediaConfig(
            access_token="access-token",
            space_name="spaces/abc-defg-hij",
        )
    )
    session = MediaSession(client, transport=FailingTransport())

    with pytest.raises(RuntimeError, match="enrollment required"):
        await session.connect()

    assert client.is_connected is False
    assert session.is_connected is False