"""Unit tests for the GcuiSuno backend using mocked HTTP responses."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ganglia_studio.music.backends.gcui_suno import GcuiSunoBackend


class _FakeResponse:
    def __init__(self, *, status_code=200, json_data=None, content=b""):
        self.status_code = status_code
        self._json_data = json_data
        self._content = content

    @property
    def text(self) -> str:
        return json.dumps(self._json_data) if self._json_data is not None else ""

    def json(self):
        if self._json_data is None:
            raise ValueError("No JSON data configured")
        return self._json_data

    def iter_content(self, chunk_size):
        for idx in range(0, len(self._content), chunk_size):
            yield self._content[idx : idx + chunk_size]


@pytest.fixture
def mock_gcui_api(monkeypatch, tmp_path):
    """Patch requests so the backend can run entirely offline."""

    audio_bytes = b"\x11" * 2048
    audio_url = "https://fake-suno/audio.mp3"

    def fake_post(url, json=None, timeout=None):  # pylint: disable=unused-argument
        if url.endswith("/api/generate_lyrics"):
            return _FakeResponse(json_data={"text": json.get("prompt", "")})
        if url.endswith("/api/custom_generate"):
            return _FakeResponse(json_data=[{"id": "lyrics-job"}])
        if url.endswith("/api/generate"):
            return _FakeResponse(json_data=[{"id": "instrumental-job"}])
        raise AssertionError(f"Unexpected POST {url}")

    def fake_get(url, timeout=None, stream=False):  # pylint: disable=unused-argument
        if url.endswith("/api/get_limit"):
            return _FakeResponse(json_data={"credits_left": 10})
        if "ids=lyrics-job" in url or "ids=instrumental-job" in url:
            return _FakeResponse(
                json_data=[{"status": "complete", "audio_url": audio_url}]
            )
        if url == audio_url:
            return _FakeResponse(content=audio_bytes)
        raise AssertionError(f"Unexpected GET {url}")

    monkeypatch.setattr("ganglia_studio.music.backends.gcui_suno.requests.post", fake_post)
    monkeypatch.setattr("ganglia_studio.music.backends.gcui_suno.requests.get", fake_get)
    monkeypatch.setenv("SUNO_API_URL", "https://fake-suno")
    monkeypatch.setenv("GANGLIA_TEMP_DIR", str(tmp_path))

    return tmp_path


def test_start_generation_instrumental_records_start_time(mock_gcui_api):
    backend = GcuiSunoBackend()

    job_id = backend.start_generation(
        prompt="Calm ambient texture",
        title="Ambient",
        tags="ambient calm",
        with_lyrics=False,
    )

    assert job_id == "instrumental-job"
    start_file = Path(mock_gcui_api) / "music" / "instrumental-job_start_time"
    assert start_file.exists()


def test_get_result_downloads_audio_file(mock_gcui_api):
    backend = GcuiSunoBackend()
    audio_path = backend.get_result("instrumental-job")

    assert audio_path is not None
    audio_file = Path(audio_path)
    assert audio_file.exists()
    assert audio_file.read_bytes().startswith(b"\x11\x11")


def test_generate_with_lyrics_returns_audio_and_lyrics(monkeypatch, mock_gcui_api):
    backend = GcuiSunoBackend()

    monkeypatch.setattr(
        GcuiSunoBackend,
        "check_progress",
        lambda self, job_id: ("complete", 100.0),
    )
    monkeypatch.setattr(
        GcuiSunoBackend,
        "get_result",
        lambda self, job_id: str(Path(mock_gcui_api) / f"{job_id}.mp3"),
    )

    audio_path, lyrics = backend.generate_with_lyrics(
        prompt="Gentle folk tune",
        story_text="Line one\nLine two",
        title="Folk Song",
        tags="folk",
        wait_audio=True,
    )

    assert audio_path.endswith(".mp3")
    assert "Line one" in lyrics
