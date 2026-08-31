from unittest.mock import MagicMock

import pytest

from api.meeting_manager import (
    MeetingManager,
    MeetingNotFoundError,
)


def test_create_and_get_meeting():
    manager = MeetingManager()

    meeting = MagicMock()

    # Bypass the production Meeting type check for this
    # isolated registry test.
    manager._meetings["mtg_test"] = meeting

    assert manager.exists("mtg_test")
    assert manager.get("mtg_test") is meeting
    assert manager.count() == 1


def test_remove_meeting():
    manager = MeetingManager()

    meeting = MagicMock()
    manager._meetings["mtg_test"] = meeting

    manager.remove("mtg_test")

    assert not manager.exists("mtg_test")
    assert manager.count() == 0


def test_get_missing_meeting():
    manager = MeetingManager()

    with pytest.raises(MeetingNotFoundError):
        manager.get("does_not_exist")


def test_remove_missing_meeting():
    manager = MeetingManager()

    with pytest.raises(MeetingNotFoundError):
        manager.remove("does_not_exist")