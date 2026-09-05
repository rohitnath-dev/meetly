"""Tests for audio models."""

from datetime import datetime
import pytest
from audio.recorder.models import AudioChunk, AudioFormat, TranscriptChunk, SpeakerSegment


def test_audio_chunk_creation():
    """Test creating an AudioChunk."""
    data = b"\x00\x01\x00\x02"
    chunk = AudioChunk(
        data=data,
        sample_rate=16000,
        channels=1,
        format=AudioFormat.PCM16,
        timestamp=datetime.utcnow(),
        source="microphone",
    )
    assert chunk.data == data
    assert chunk.sample_rate == 16000
    assert chunk.channels == 1
    assert chunk.format == AudioFormat.PCM16
    assert chunk.source == "microphone"


def test_transcript_chunk_creation():
    """Test creating a TranscriptChunk."""
    chunk = TranscriptChunk(
        text="Hello world",
        start_time=0.0,
        end_time=1.0,
        confidence=0.95,
        is_final=True,
    )
    assert chunk.text == "Hello world"
    assert chunk.start_time == 0.0
    assert chunk.end_time == 1.0
    assert chunk.confidence == 0.95
    assert chunk.is_final is True


def test_transcript_chunk_partial():
    """Test partial transcript chunk."""
    chunk = TranscriptChunk(
        text="Hello",
        start_time=0.0,
        end_time=0.5,
        is_final=False,
    )
    assert chunk.is_final is False
    assert chunk.confidence is None


def test_speaker_segment_creation():
    """Test creating a SpeakerSegment."""
    segment = SpeakerSegment(
        speaker_id="SPEAKER_00",
        start_time=0.0,
        end_time=2.5,
        confidence=0.88,
    )
    assert segment.speaker_id == "SPEAKER_00"
    assert segment.start_time == 0.0
    assert segment.end_time == 2.5
    assert segment.confidence == 0.88
