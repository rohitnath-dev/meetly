from __future__ import annotations

from typing import Any

from .client import GoogleMeetClient


class GoogleMeetMeetings:
    def __init__(self, client: GoogleMeetClient) -> None:
        self.client = client

    async def create(
        self,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self.client.create_space(config)

    async def get(
        self,
        space_name: str,
    ) -> dict[str, Any]:
        return await self.client.get_space(space_name)

    async def end(
        self,
        space_name: str,
    ) -> dict[str, Any]:
        return await self.client.end_active_conference(space_name)

    async def get_conference(
        self,
        conference_record_name: str,
    ) -> dict[str, Any]:
        return await self.client.get_conference_record(
            conference_record_name
        )

    async def list_conferences(
        self,
        *,
        page_size: int = 100,
        page_token: str | None = None,
        filter_expression: str | None = None,
    ) -> dict[str, Any]:
        return await self.client.list_conference_records(
            page_size=page_size,
            page_token=page_token,
            filter_expression=filter_expression,
        )

    async def list_participants(
        self,
        conference_record_name: str,
        *,
        page_size: int = 100,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        return await self.client.list_participants(
            conference_record_name,
            page_size=page_size,
            page_token=page_token,
        )