from __future__ import annotations

from meetly.llm import (
    ACTION_ITEMS_PROMPT,
    SYSTEM_PROMPT,
    LLMClient,
)


class ActionItemExtractor:

    def __init__(
        self,
        llm: LLMClient,
    ) -> None:
        self._llm = llm

    async def extract(
        self,
        transcript: str,
    ) -> str:
        if not isinstance(transcript, str):
            raise TypeError(
                "transcript must be a string."
            )

        transcript = transcript.strip()

        if not transcript:
            raise ValueError(
                "Cannot extract action items from an empty transcript."
            )

        user_prompt = ACTION_ITEMS_PROMPT.format(
            transcript=transcript
        )

        return await self._llm.complete(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )


__all__ = [
    "ActionItemExtractor",
]