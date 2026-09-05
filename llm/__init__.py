"""LLM integration for Meetly."""

from .client import LLMClient, LLMError
from .prompts import (
    SUMMARIZATION_SYSTEM_PROMPT,
    SUMMARIZATION_USER_PROMPT_TEMPLATE,
    QNA_SYSTEM_PROMPT,
    QNA_USER_PROMPT_TEMPLATE,
)

__all__ = [
    "LLMClient",
    "LLMError",
    "SUMMARIZATION_SYSTEM_PROMPT",
    "SUMMARIZATION_USER_PROMPT_TEMPLATE",
    "QNA_SYSTEM_PROMPT",
    "QNA_USER_PROMPT_TEMPLATE",
]
