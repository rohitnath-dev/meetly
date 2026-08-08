"""
Microphone audio source for Meetly.

Captures live audio from a local input device using PortAudio (via
the ``sounddevice`` bindings) and exposes it as a stream of
``AudioChunk`` objects conforming to the ``AudioSource`` interface.
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator, Optional

import sounddevice as sd

from .models import AudioChunk, AudioFormat
from .source import AudioSource

logger = logging.getLogger(__name__)

_DTYPE_BY_FORMAT: dict[AudioFormat, str] = {
    AudioFormat.PCM16: "int16",
    AudioFormat.PCM32: "int32",
    AudioFormat.FLOAT32: "float32",
}


class MicrophoneError(RuntimeError):
    """Raised for microphone configuration or capture failures."""


class MicrophoneSource(AudioSource):
    """
    ``AudioSource`` implementation that captures live microphone audio.

    Audio is captured on a dedicated PortAudio callback thread and
    handed off to the asyncio event loop through a thread-safe queue,
    so :meth:`stream` can be safely consumed by asyncio code without
    blocking the event loop.
    """

    def __init__(
        self,
        *,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_size: int = 1024,
        audio_format: AudioFormat = AudioFormat.PCM16,
        device: Optional[int | str] = None,
        name: str = "Microphone",
    ) -> None:
        """
        Configure a microphone audio source.

        Args:
            sample_rate: Capture sample rate in Hz (e.g. 16000, 44100, 48000).
            channels: Number of input channels to capture.
            chunk_size: Number of frames per emitted ``AudioChunk``.
            audio_format: Sample encoding used for captured audio.
            device: PortAudio device index or name substring. ``None``
                selects the system default input device.
            name: Human-readable name reported via :attr:`name`.

        Raises:
            ValueError:
                If ``sample_rate``, ``channels``, or ``chunk_size`` are
                not positive, or if ``audio_format`` is unsupported.
        """
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive.")
        if channels <= 0:
            raise ValueError("channels must be positive.")
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive.")
        if audio_format not in _DTYPE_BY_FORMAT:
            raise ValueError(f"Unsupported audio format: {audio_format!r}")

        self._sample_rate = sample_rate
        self._channels = channels
        self._chunk_size = chunk_size
        self._audio_format = audio_format
        self._dtype = _DTYPE_BY_FORMAT[audio_format]
        self._device = device
        self._name = name

        self._stream: Optional[sd.RawInputStream] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._queue: "asyncio.Queue[Optional[AudioChunk]]" = asyncio.Queue()
        self._running = False

    @property
    def name(self) -> str:
        """Human-readable source name."""
        return self._name

    @property
    def sample_rate(self) -> int:
        """Configured capture sample rate, in Hz."""
        return self._sample_rate

    @property
    def channels(self) -> int:
        """Configured number of input channels."""
        return self._channels

    @property
    def chunk_size(self) -> int:
        """Configured number of frames per emitted chunk."""
        return self._chunk_size

    async def start(self) -> None:
        """
        Open and start the underlying input stream.

        Raises:
            MicrophoneError:
                If the source is already running or the input device
                cannot be opened.
        """
        if self._running:
            raise MicrophoneError(
                f"Microphone source '{self._name}' is already running."
            )

        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue()

        try:
            self._stream = sd.RawInputStream(
                samplerate=self._sample_rate,
                channels=self._channels,
                dtype=self._dtype,
                blocksize=self._chunk_size,
                device=self._device,
                callback=self._on_audio,
            )
            self._stream.start()
        except sd.PortAudioError as exc:
            self._stream = None
            raise MicrophoneError(
                f"Failed to open microphone input stream: {exc}"
            ) from exc
        except Exception as exc:
            self._stream = None
            raise MicrophoneError(
                f"Unexpected error starting microphone: {exc}"
            ) from exc

        self._running = True
        logger.info(
            "Microphone '%s' started (sample_rate=%d, channels=%d, "
            "chunk_size=%d, format=%s)",
            self._name,
            self._sample_rate,
            self._channels,
            self._chunk_size,
            self._audio_format,
        )

    async def stop(self) -> None:
        """
        Stop and close the underlying input stream.

        Safe to call multiple times; calls after the source has
        already stopped are a no-op.
        """
        if not self._running:
            return

        self._running = False

        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except sd.PortAudioError:
                logger.exception(
                    "Error while closing microphone stream for '%s'.", self._name
                )
            finally:
                self._stream = None

        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, None)

        logger.info("Microphone '%s' stopped.", self._name)

    def _on_audio(
        self,
        indata: bytes,
        frames: int,
        time_info: object,
        status: sd.CallbackFlags,
    ) -> None:
        """
        PortAudio callback invoked on the native audio thread.

        Copies the incoming buffer (which PortAudio reuses internally)
        into an immutable ``bytes`` object and hands it to the asyncio
        queue via ``call_soon_threadsafe``.
        """
        if status:
            logger.warning("Microphone '%s' input status: %s", self._name, status)

        if not self._running or self._loop is None:
            return

        chunk = AudioChunk(
            data=bytes(indata),
            sample_rate=self._sample_rate,
            channels=self._channels,
            format=self._audio_format,
            source=self._name,
        )
        try:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, chunk)
        except RuntimeError:
            logger.debug(
                "Dropped audio chunk for '%s': event loop closed.", self._name
            )

    async def stream(self) -> AsyncIterator[AudioChunk]:
        """
        Yield captured :class:`AudioChunk` objects until stopped.

        Raises:
            MicrophoneError: If called before :meth:`start`.
        """
        if not self._running and self._stream is None:
            raise MicrophoneError(
                f"Microphone source '{self._name}' must be started before streaming."
            )

        while True:
            chunk = await self._queue.get()
            if chunk is None:
                break
            yield chunk

    async def __aenter__(self) -> "MicrophoneSource":
        """Start the microphone as an async context manager."""
        await self.start()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        """Stop the microphone when exiting an async context manager."""
        await self.stop()