from __future__ import annotations

from typing import Any

import httpx

from .exceptions import (
    GoogleMeetAPIError,
    GoogleMeetAuthenticationError,
)


class GoogleMeetClient:
    BASE_URL = "https://meet.googleapis.com/v2"

    def __init__(
        self,
        access_token: str,
        timeout: float = 30.0,
    ) -> None:
        if not access_token:
            raise GoogleMeetAuthenticationError(
                "Google Meet access token is required."
            )

        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "GoogleMeetClient":
        return self

    async def __aexit__(
        self,
        exc_type: Any,
        exc_value: Any,
        traceback: Any,
    ) -> None:
        await self.close()

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        try:
            response = await self._client.request(
                method,
                path,
                **kwargs,
            )
        except httpx.HTTPError as exc:
            raise GoogleMeetAPIError(
                f"Google Meet API request failed: {exc}"
            ) from exc

        if response.status_code in (401, 403):
            raise GoogleMeetAuthenticationError(
                f"Google Meet authentication failed: "
                f"{response.status_code}"
            )

        if response.is_error:
            try:
                detail = response.json()
            except ValueError:
                detail = response.text

            raise GoogleMeetAPIError(
                f"Google Meet API returned "
                f"{response.status_code}: {detail}"
            )

        if not response.content:
            return {}

        try:
            return response.json()
        except ValueError as exc:
            raise GoogleMeetAPIError(
                "Google Meet API returned an invalid JSON response."
            ) from exc

    async def get_space(
        self,
        space_name: str,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/{space_name}",
        )

    async def create_space(
        self,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}

        if config is not None:
            payload["config"] = config

        return await self._request(
            "POST",
            "/spaces",
            json=payload,
        )

    async def end_active_conference(
        self,
        space_name: str,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"/{space_name}:endActiveConference",
        )

    async def get_conference_record(
        self,
        conference_record_name: str,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/{conference_record_name}",
        )

    async def list_conference_records(
        self,
        *,
        page_size: int = 100,
        page_token: str | None = None,
        filter_expression: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "pageSize": page_size,
        }

        if page_token:
            params["pageToken"] = page_token

        if filter_expression:
            params["filter"] = filter_expression

        return await self._request(
            "GET",
            "/conferenceRecords",
            params=params,
        )

    async def get_participant(
        self,
        participant_name: str,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/{participant_name}",
        )

    async def list_participants(
        self,
        conference_record_name: str,
        *,
        page_size: int = 100,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "pageSize": page_size,
        }

        if page_token:
            params["pageToken"] = page_token

        return await self._request(
            "GET",
            f"/{conference_record_name}/participants",
            params=params,
        )

    async def get_transcript(
        self,
        transcript_name: str,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/{transcript_name}",
        )

    async def list_transcripts(
        self,
        conference_record_name: str,
        *,
        page_size: int = 100,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "pageSize": page_size,
        }

        if page_token:
            params["pageToken"] = page_token

        return await self._request(
            "GET",
            f"/{conference_record_name}/transcripts",
            params=params,
        )