"""Shared fixtures for unit tests under tests/unit/video."""

import pytest

from tests.audio_fixtures import setup_dummy_whisper


@pytest.fixture(autouse=True)
def _patch_whisper(monkeypatch):
    """
    Automatically install the dummy Whisper model for all video unit tests.

    The production implementation downloads large models and requires network
    access.  The dummy model allows the suite to exercise the alignment logic
    deterministically and without external dependencies.
    """

    setup_dummy_whisper(monkeypatch)

