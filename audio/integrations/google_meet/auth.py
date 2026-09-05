from __future__ import annotations

from typing import Any

import httpx

from .exceptions import GoogleMeetAuthenticationError


class GoogleMeetAuth:
    TOKEN_URL = "https://oauth2.googleapis.com/token"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
    ) -> None:
        if not client_id or not client_secret or not refresh_token:
            raise GoogleMeetAuthenticationError(
                "Google OAuth credentials are required."
            )

        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token

    async def refresh_access_token(self) -> dict[str, Any]:
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.TOKEN_URL,
                    data=data,
                )
        except httpx.HTTPError as exc:
            raise GoogleMeetAuthenticationError(
                f"Google OAuth request failed: {exc}"
            ) from exc

        if response.is_error:
            try:
                detail = response.json()
            except ValueError:
                detail = response.text

            raise GoogleMeetAuthenticationError(
                f"Google OAuth failed: {detail}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise GoogleMeetAuthenticationError(
                "Google OAuth returned an invalid response."
            ) from exc

    async def get_access_token(self) -> str:
        result = await self.refresh_access_token()

        access_token = result.get("access_token")

        if not access_token:
            raise GoogleMeetAuthenticationError(
                "Google OAuth response did not contain an access token."
            )

        return access_token