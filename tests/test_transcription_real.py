"""Smoke-тесты транскрибации с настоящей моделью GigaAM v3.

Выполняются только там, где есть веса (в собранном образе, MODELS_DIR) и фикстура
tests/audio/ru_short.wav — синтезированная русская фраза без персональных данных.
Вне образа пропускаются.
"""

import subprocess
import threading
import time
import wave
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.transcription import model_dir, transcribe_bytes, vad_dir

SAMPLE = Path(__file__).parent / "audio" / "ru_short.wav"

MODEL_READY = (
    model_dir(settings.MODELS_DIR, settings.TRANSCRIPTION_MODEL).is_dir()
    and model_dir(settings.MODELS_DIR, settings.TRANSCRIPTION_FALLBACK_MODEL).is_dir()
    and vad_dir(settings.MODELS_DIR).is_dir()
)

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not (MODEL_READY and SAMPLE.exists()),
        reason="нет весов модели в MODELS_DIR или фикстуры tests/audio/ru_short.wav",
    ),
]


def _wav_bytes(channels: list, sample_rate: int = 16000) -> bytes:
    """WAV (PCM 16 бит) из списка одномерных int16-массивов, по одному на канал."""
    interleaved = np.stack(channels, axis=1).astype("<i2")
    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(len(channels))
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(interleaved.tobytes())
    return buffer.getvalue()


def _sample_samples() -> np.ndarray:
    """Отсчёты фикстуры (моно, 16 кГц, int16)."""
    with wave.open(str(SAMPLE), "rb") as wav:
        assert wav.getnchannels() == 1 and wav.getframerate() == 16000
        return np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")


def _transcribe(content: bytes, labels=None):
    """Расшифровка с настоящей моделью; возвращает результат и затраченное время."""
    started = time.monotonic()
    result = transcribe_bytes(
        content,
        channel_labels=labels or [],
        cancel_event=threading.Event(),
        deadline=time.monotonic() + settings.TRANSCRIPTION_TIMEOUT_SECONDS,
    )
    return result, time.monotonic() - started


def test_real_mono_has_text_and_monotonic_timestamps():
    """Моно: непустой текст, неубывающие тайм-коды внутри длительности записи."""
    result, elapsed = _transcribe(SAMPLE.read_bytes())

    print(
        f"\nRTF={elapsed / result.duration:.2f} text={[s.text for s in result.segments]}"
    )
    assert result.segments
    # Фраза целиком, включая конец после паузы: с настройками VAD по умолчанию
    # короткие сегменты возвращали пустой текст и конец фразы терялся.
    text = " ".join(s.text for s in result.segments).lower()
    assert "помочь" in text
    assert all(s.speaker is None and s.channel is None for s in result.segments)
    starts = [s.start for s in result.segments]
    assert starts == sorted(starts)
    assert all(0 <= s.start < s.end <= result.duration + 0.5 for s in result.segments)


def test_real_stereo_assigns_speakers():
    """Стерео: фраза в левом канале, затем та же фраза в правом — метки по каналам."""
    clip = _sample_samples()
    silence = np.zeros_like(clip)
    content = _wav_bytes(
        [np.concatenate([clip, silence]), np.concatenate([silence, clip])]
    )

    result, _ = _transcribe(content, labels=["client", "operator"])

    speakers = [s.speaker for s in result.segments]
    assert result.channels == 2
    assert speakers[0] == "client"
    assert speakers[-1] == "operator"
    assert speakers == sorted(speakers, key=["client", "operator"].index)
    clip_seconds = len(clip) / 16000
    assert all(s.end <= clip_seconds + 0.5 for s in result.segments if s.channel == 0)
    assert all(s.start >= clip_seconds - 0.5 for s in result.segments if s.channel == 1)


def test_real_silence_is_no_speech():
    """Десять секунд тишины: пустой результат без ошибки."""
    content = _wav_bytes([np.zeros(16000 * 10, dtype=np.int16)])

    result, _ = _transcribe(content)

    assert result.segments == []
    assert result.duration == pytest.approx(10.0, abs=0.1)


def test_real_short_utterance_is_recognized():
    """Отдельная короткая реплика не превращается в no_speech."""
    result, _ = _transcribe(_wav_bytes([_sample_samples()[:32000]]))

    assert "компани" in " ".join(s.text for s in result.segments).lower()


def test_real_pause_does_not_erase_first_utterance():
    clip = _sample_samples()
    content = _wav_bytes(
        [np.concatenate([clip[:32000], np.zeros(48000, dtype=np.int16), clip[32000:]])]
    )

    result, _ = _transcribe(content)

    text = " ".join(s.text for s in result.segments).lower()
    assert "компани" in text
    assert "помочь" in text


@pytest.mark.parametrize("rate,samples", [(16000, 1), (16000, 300), (8000, 240)])
def test_real_very_short_file_is_no_speech(rate, samples):
    """Оборванная запись короче 36 мс: 200 и no_speech, а не 500 из-за VAD."""
    content = _wav_bytes([np.zeros(samples, dtype=np.int16)], sample_rate=rate)

    with TestClient(app) as client:
        response = client.post(
            "/v1/transcribe",
            files={"file": ("short.wav", content, "audio/wav")},
        )

    assert response.status_code == 200
    assert response.json()["text_status"] == "no_speech"
    assert response.json()["segments"] == []


def test_real_full_http_cycle():
    """Полный цикл через HTTP: загрузка файла, расшифровка, ответ по контракту."""
    with TestClient(app) as client:
        response = client.post(
            "/v1/transcribe",
            files={"file": ("ru_short.wav", SAMPLE.read_bytes(), "audio/wav")},
            data={"external_id": "smoke-1"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["filename"] == "ru_short.wav"
    assert body["external_id"] == "smoke-1"
    assert body["language"] == "ru"
    assert body["text_status"] == "ok"
    assert body["text"] == " ".join(s["text"] for s in body["segments"])
    assert body["detected_format"] == "wav"


@pytest.fixture(scope="module")
def m4a_sample(tmp_path_factory):
    """Публичная синтетическая фраза в контейнере M4A, без личных записей."""
    path = tmp_path_factory.mktemp("audio_detection") / "sample.m4a"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(SAMPLE),
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path.read_bytes()


@pytest.mark.parametrize("filename", ["iphone.ogg", "recording.bin", "recording"])
def test_real_m4a_transcribed_regardless_of_filename(m4a_sample, filename):
    with TestClient(app) as client:
        response = client.post(
            "/v1/transcribe",
            files={"file": (filename, m4a_sample, "application/octet-stream")},
            data={"external_id": "m4a-detection-smoke"},
        )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["filename"] == filename
    assert body["detected_format"] == "m4a"
    assert body["external_id"] == "m4a-detection-smoke"
    assert "помочь" in body["text"].lower()
