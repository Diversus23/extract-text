"""Определение аудио по содержимому: настоящий ffmpeg и подмена только ASR."""

import subprocess

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.transcription import Transcriber

pytestmark = pytest.mark.integration


class SilentModel:
    def recognize(self, waveform, *, sample_rate):
        return iter([])


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_MODE", "none")
    transcriber = Transcriber(model_factory=SilentModel)
    monkeypatch.setattr("app.transcription._transcriber", transcriber)
    yield TestClient(app)
    transcriber.close()


def _encoded_audio(tmp_path, muxer, codec):
    path = tmp_path / "encoded.bin"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=16000:cl=mono",
            "-t",
            "1",
            "-c:a",
            codec,
            "-f",
            muxer,
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path.read_bytes()


@pytest.mark.parametrize(
    "muxer,codec,detected",
    [
        ("mp4", "aac", "m4a"),
        ("wav", "pcm_s16le", "wav"),
        ("mp3", "libmp3lame", "mp3"),
        ("ogg", "libvorbis", "ogg"),
        ("ogg", "libopus", "opus"),
        ("flac", "flac", "flac"),
        ("adts", "aac", "aac"),
        ("asf", "wmav2", "wma"),
    ],
)
def test_supported_formats_detected_without_extension(
    client, tmp_path, muxer, codec, detected
):
    response = client.post(
        "/v1/transcribe",
        files={
            "file": (
                "recording",
                _encoded_audio(tmp_path, muxer, codec),
                "application/octet-stream",
            )
        },
        data={"external_id": "detection-test"},
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["filename"] == "recording"
    assert body["external_id"] == "detection-test"
    assert body["detected_format"] == detected
    assert body["duration"] == pytest.approx(1.0, abs=0.3)


@pytest.mark.parametrize("filename", ["iphone.ogg", "recording.bin", "wrong.exe"])
def test_m4a_accepted_with_wrong_name_and_content_type(client, tmp_path, filename):
    response = client.post(
        "/v1/transcribe",
        files={
            "file": (filename, _encoded_audio(tmp_path, "mp4", "aac"), "text/plain")
        },
    )

    assert response.status_code == 200, response.json()
    assert response.json()["filename"] == filename
    assert response.json()["detected_format"] == "m4a"


def test_known_but_unsupported_container_is_rejected(client, tmp_path):
    response = client.post(
        "/v1/transcribe",
        files={
            "file": (
                "voice.m4a",
                _encoded_audio(tmp_path, "matroska", "aac"),
                "audio/mp4",
            )
        },
    )

    assert response.status_code == 415


@pytest.mark.parametrize(
    "payload",
    [
        b"plain text",
        b"ffconcat version 1.0\nfile /etc/passwd\n",
        b"#EXTM3U\nhttp://127.0.0.1:9/a.mp3\n",
    ],
)
def test_non_audio_and_playlists_cannot_masquerade_as_audio(client, payload):
    response = client.post(
        "/v1/transcribe", files={"file": ("voice.mp3", payload, "audio/mpeg")}
    )

    assert response.status_code == 415


def test_recognizable_but_damaged_wav_is_422(client, tmp_path):
    content = _encoded_audio(tmp_path, "wav", "pcm_s16le")
    response = client.post(
        "/v1/transcribe", files={"file": ("recording", content[:40], "audio/wav")}
    )

    assert response.status_code == 422
