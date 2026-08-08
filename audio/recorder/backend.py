"""
Core recorder backend for Meetly's audio pipeline.

This module owns the lifecycle of audio recording: registering one or
more ``AudioSource`` instances, starting/stopping them, consuming the
``AudioChunk`` objects they produce, and exposing those chunks to the
rest of the system through async iteration and/or callbacks.

This module intentionally contains no transcription, diarization, or
other AI logic -- it is a pure audio plumbing layer.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import threading
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, Union

from .models import AudioChunk, RecordingState
from .source import AudioSource

logger = logging.getLogger(__name__)

ChunkCallback = Callable[[AudioChunk], Union[None, Awaitable[None]]]


class RecorderError(RuntimeError):
    """Raised for invalid recorder operations or lifecycle violations."""


class SourceAlreadyRegisteredError(RecorderError):
    """Raised when attempting to register a source that is already registered."""


class SourceNotRegisteredError(RecorderError):
    """Raised when attempting to unregister/reference an unknown source."""


@dataclass
class _SourceHandle:
    """Internal bookkeeping for a registered audio source and its consumer task."""

    source: AudioSource
    task: Optional[asyncio.Task[None]] = None


class RecorderBackend:
    """
    Orchestrates one or more :class:`AudioSource` instances.

    The backend is responsible for the full recording lifecycle: it
    starts and stops registered sources, drains their audio streams
    concurrently into a single ordered queue, fans chunks out to
    registered callbacks, and exposes the resulting stream through
    async iteration (``async for chunk in backend``).

    The backend performs no audio decoding, transcription, or speaker
    analysis -- it only moves ``AudioChunk`` objects from sources to
    consumers.

    Thread safety:
        Public state (``state``, registered sources, and callbacks) is
        protected by an internal ``threading.Lock`` because
        ``AudioSource`` implementations may deliver chunks from
        non-asyncio threads (e.g. a native audio callback thread).
        Coroutine methods are intended to be driven from a single
        asyncio event loop.
    """

    def __init__(self, *, queue_maxsize: int = 0) -> None:
        """
        Initialize the backend.

        Args:
            queue_maxsize:
                Maximum number of buffered chunks before producers
                block. ``0`` means unbounded.
        """
        self._lock = threading.Lock()
        self._state: RecordingState = RecordingState.STOPPED
        self._sources: dict[str, _SourceHandle] = {}
        self._callbacks: list[ChunkCallback] = []
        self._queue: "asyncio.Queue[Optional[AudioChunk]]" = asyncio.Queue(
            maxsize=queue_maxsize
        )
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stopping = False

    @property
    def state(self) -> RecordingState:
        """Current lifecycle state of the recorder."""
        with self._lock:
            return self._state

    def _set_state(self, new_state: RecordingState) -> None:
        """Update recorder state under lock and log the transition."""
        with self._lock:
            old_state = self._state
            self._state = new_state
        logger.debug("Recorder state transition: %s -> %s", old_state, new_state)

    @property
    def sources(self) -> tuple[AudioSource, ...]:
        """Tuple of currently registered audio sources."""
        with self._lock:
            return tuple(handle.source for handle in self._sources.values())

    def register_source(self, source: AudioSource) -> None:
        """
        Register an audio source with the recorder.

        Args:
            source: The :class:`AudioSource` instance to register.

        Raises:
            SourceAlreadyRegisteredError:
                If a source with the same name is already registered.
            RecorderError:
                If called while the recorder is running.
        """
        with self._lock:
            if self._state == RecordingState.RUNNING:
                raise RecorderError(
                    "Cannot register a source while the recorder is running."
                )
            if source.name in self._sources:
                raise SourceAlreadyRegisteredError(
                    f"Source '{source.name}' is already registered."
                )
            self._sources[source.name] = _SourceHandle(source=source)
        logger.info("Registered audio source: %s", source.name)

    def unregister_source(self, name: str) -> None:
        """
        Unregister a previously registered audio source.

        Args:
            name: The ``name`` of the source to remove.

        Raises:
            SourceNotRegisteredError: If no source with that name is registered.
            RecorderError: If called while the recorder is running.
        """
        with self._lock:
            if self._state == RecordingState.RUNNING:
                raise RecorderError(
                    "Cannot unregister a source while the recorder is running."
                )
            if name not in self._sources:
                raise SourceNotRegisteredError(f"Source '{name}' is not registered.")
            del self._sources[name]
        logger.info("Unregistered audio source: %s", name)

    def add_callback(self, callback: ChunkCallback) -> None:
        """
        Register a callback invoked for every received :class:`AudioChunk`.

        Callbacks may be synchronous or coroutine functions. Coroutine
        callbacks are scheduled as fire-and-forget tasks and are not
        awaited inline, so a slow callback will not stall the audio
        pipeline.

        Args:
            callback: A callable accepting a single ``AudioChunk``.
        """
        with self._lock:
            self._callbacks.append(callback)
        logger.debug("Added chunk callback: %r", callback)

    def remove_callback(self, callback: ChunkCallback) -> None:
        """
        Remove a previously registered callback.

        Args:
            callback: The callback instance to remove.

        Raises:
            RecorderError: If the callback was never registered.
        """
        with self._lock:
            try:
                self._callbacks.remove(callback)
            except ValueError as exc:
                raise RecorderError("Callback is not registered.") from exc

    async def start(self) -> None:
        """
        Start recording from all registered sources.

        Starts every registered :class:`AudioSource`, then spawns a
        background consumer task per source that drains its
        ``stream()`` into the backend's internal queue.

        Raises:
            RecorderError:
                If the recorder is not in the ``STOPPED`` state, or if
                no sources are registered.
        """
        with self._lock:
            if self._state != RecordingState.STOPPED:
                raise RecorderError(
                    f"Cannot start recorder from state '{self._state}'."
                )
            if not self._sources:
                raise RecorderError(
                    "Cannot start recording with no registered sources."
                )

        self._set_state(RecordingState.STARTING)
        self._loop = asyncio.get_running_loop()
        self._stopping = False

        started: list[_SourceHandle] = []
        try:
            for handle in list(self._sources.values()):
                logger.info("Starting audio source: %s", handle.source.name)
                await handle.source.start()
                started.append(handle)
        except Exception:
            logger.exception("Failed to start audio source; rolling back.")
            for handle in started:
                await self._safe_stop_source(handle.source)
            self._set_state(RecordingState.ERROR)
            raise

        for handle in self._sources.values():
            handle.task = asyncio.create_task(
                self._consume_source(handle.source),
                name=f"recorder-consume-{handle.source.name}",
            )

        self._set_state(RecordingState.RUNNING)
        logger.info("Recorder started with %d source(s).", len(self._sources))

    async def stop(self) -> None:
        """
        Stop recording and release all source resources.

        Idempotent: calling ``stop`` when already stopped, or while a
        stop is already in progress, is a no-op.
        """
        with self._lock:
            current = self._state

        if current == RecordingState.STOPPED:
            logger.debug("Recorder already stopped; ignoring stop() call.")
            return
        if current == RecordingState.STOPPING:
            logger.debug("Recorder already stopping; ignoring duplicate stop() call.")
            return

        self._set_state(RecordingState.STOPPING)
        self._stopping = True

        for handle in list(self._sources.values()):
            await self._safe_stop_source(handle.source)

        for handle in list(self._sources.values()):
            if handle.task is not None:
                try:
                    await handle.task
                except Exception:
                    logger.exception(
                        "Consumer task for source '%s' raised during shutdown.",
                        handle.source.name,
                    )
                finally:
                    handle.task = None

        await self._queue.put(None)
        self._set_state(RecordingState.STOPPED)
        logger.info("Recorder stopped.")

    async def _safe_stop_source(self, source: AudioSource) -> None:
        """Stop a single source, logging but not raising on failure."""
        try:
            logger.info("Stopping audio source: %s", source.name)
            await source.stop()
        except Exception:
            logger.exception("Error while stopping audio source '%s'.", source.name)

    async def _consume_source(self, source: AudioSource) -> None:
        """
        Drain a single source's ``stream()`` into the shared queue.

        Any exception raised by the source's stream is logged and
        transitions the recorder into the ``ERROR`` state; it does not
        propagate to the caller of ``start()``.
        """
        try:
            async for chunk in source.stream():
                if self._stopping:
                    break
                await self._queue.put(chunk)
                self._dispatch_callbacks(chunk)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Audio source '%s' failed while streaming.", source.name)
            self._set_state(RecordingState.ERROR)

    def _dispatch_callbacks(self, chunk: AudioChunk) -> None:
        """Invoke all registered callbacks for a received chunk."""
        with self._lock:
            callbacks = list(self._callbacks)

        for callback in callbacks:
            try:
                result = callback(chunk)
                if inspect.isawaitable(result):
                    asyncio.ensure_future(result)
            except Exception:
                logger.exception("Chunk callback %r raised an exception.", callback)

    def __aiter__(self) -> "RecorderBackend":
        """Return self as an async iterator over received audio chunks."""
        return self

    async def __anext__(self) -> AudioChunk:
        """
        Return the next available :class:`AudioChunk`.

        Raises:
            StopAsyncIteration:
                Once the recorder has fully stopped and no further
                chunks will be produced.
        """
        chunk = await self._queue.get()
        if chunk is None:
            raise StopAsyncIteration
        return chunk

    async def __aenter__(self) -> "RecorderBackend":
        """Start the recorder as an async context manager."""
        await self.start()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        """Stop the recorder when exiting an async context manager."""
        await self.stop()