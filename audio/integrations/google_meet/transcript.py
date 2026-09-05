from __future__ import annotations

from typing import Any

from .client import GoogleMeetClient


class GoogleMeetTranscript:
    def __init__(self, client: GoogleMeetClient) -> None:
        self.client = client

    async def get(
        self,
        transcript_name: str,
    ) -> dict[str, Any]:
        return await self.client.get_transcript(
            transcript_name
        )

    async def list(
        self,
        conference_record_name: str,
        *,
        page_size: int = 100,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        return await self.client.list_transcripts(
            conference_record_name,
            page_size=page_size,
            page_token=page_token,
        )