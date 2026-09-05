"""Tests for configuration."""

import os
import pytest
from config import Settings


def test_default_settings():
    """Test default settings."""
    settings = Settings(_env_file=None)
    assert settings.PROJECT_NAME == "Meetly"
    assert settings.VERSION == "1.0.0"
    assert settings.HOST == "0.0.0.0"
    assert settings.PORT == 8000
    assert settings.DEBUG is False


def test_has_google_credentials():
    """Test Google credentials check."""
    settings = Settings(_env_file=None)
    assert settings.has_google_credentials() is False

    settings2 = Settings(
        _env_file=None,
        GOOGLE_CLIENT_ID="test_id",
        GOOGLE_CLIENT_SECRET="test_secret",
        GOOGLE_REFRESH_TOKEN="test_token",
    )
    assert settings2.has_google_credentials() is True


def test_has_openrouter_credentials():
    """Test OpenRouter credentials check."""
    settings = Settings(_env_file=None)
    assert settings.has_openrouter_credentials() is False

    settings2 = Settings(_env_file=None, OPENROUTER_API_KEY="test_key")
    assert settings2.has_openrouter_credentials() is True
