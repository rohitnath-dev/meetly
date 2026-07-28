"""OpenRouter client."""

from __future__ import annotations

import httpx

from config import settings


class LLMError(Exception):
    """Raised when an LLM request fails."""


class LLMClient:
    """Client for interacting with OpenRouter."""

    CHAT_COMPLETIONS_PATH = "/chat/completions"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.OPENROUTER_BASE_URL.rstrip("/"),
            timeout=settings.OPENROUTER_TIMEOUT,
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        """Return request headers."""
        return {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": settings.HTTP_REFERER,
            "X-Title": settings.APP_TITLE,
        }

    async def _request(self, payload: dict) -> dict:
        """Send a request to OpenRouter."""

        try:
            response = await self._client.post(
                self.CHAT_COMPLETIONS_PATH,
                headers=self._headers(),
                json=payload,
            )

            response.raise_for_status()

            return response.json()

        except httpx.HTTPError as exc:
            raise LLMError(str(exc)) from exc

    async def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Generate a completion."""

        payload = {
            "model": settings.OPENROUTER_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            "temperature": (
                temperature
                if temperature is not None
                else settings.OPENROUTER_TEMPERATURE
            ),
            "max_tokens": (
                max_tokens
                if max_tokens is not None
                else settings.OPENROUTER_MAX_TOKENS
            ),
        }

        data = await self._request(payload)

        try:
            return data["choices"][0]["message"]["content"]

        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("Invalid response received from OpenRouter.") from exc