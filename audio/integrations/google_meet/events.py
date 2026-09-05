from __future__ import annotations

from typing import Any, Callable, Awaitable


EventHandler = Callable[[dict[str, Any]], Awaitable[None]]


class GoogleMeetEventHandler:
    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = {}

    def register(
        self,
        event_type: str,
        handler: EventHandler,
    ) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    async def handle(
        self,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        handlers = self._handlers.get(event_type, [])

        for handler in handlers:
            await handler(payload)

    def registered_events(self) -> list[str]:
        return list(self._handlers.keys())