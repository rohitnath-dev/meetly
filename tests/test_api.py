"""Tests for API endpoints."""

import pytest
from fastapi.testclient import TestClient
from api.main import app


client = TestClient(app)


def test_health_endpoint():
    """Test health check endpoint."""
    response = client.get("/health/")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["project"] == "Meetly"


def test_root_endpoint():
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["success"] == "true"
    assert response.json()["project"] == "Meetly"


def test_create_meeting():
    """Test creating a meeting."""
    response = client.post("/meetings")
    assert response.status_code == 200
    data = response.json()
    assert "meeting_id" in data
    assert data["state"] == "idle"
    assert data["meeting_id"].startswith("mtg_")


def test_get_meeting():
    """Test getting meeting status."""
    # Create a meeting first
    create_response = client.post("/meetings")
    meeting_id = create_response.json()["meeting_id"]

    # Get the meeting
    response = client.get(f"/meetings/{meeting_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["meeting_id"] == meeting_id
    assert data["state"] == "idle"
    assert data["running"] is False


def test_get_nonexistent_meeting():
    """Test getting a nonexistent meeting."""
    response = client.get("/meetings/mtg_nonexistent")
    assert response.status_code == 404


def test_get_transcript():
    """Test getting transcript."""
    # Create a meeting first
    create_response = client.post("/meetings")
    meeting_id = create_response.json()["meeting_id"]

    # Get transcript (should be empty)
    response = client.get(f"/meetings/{meeting_id}/transcript")
    assert response.status_code == 200
    data = response.json()
    assert data["meeting_id"] == meeting_id
    assert data["transcript"] == ""
