"""Pytest configuration and fixtures."""

import os
import pytest


@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    """Set up test environment variables."""
    monkeypatch.setenv("DEBUG", "False")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test_key")
