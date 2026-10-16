"""Контрактные тесты эндпоинта POST /v1/transcribe (обработка подменена)."""

import asyncio
import threading
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import main as app_main
from app.config import settings
from app.main import app
from app.transcription import (
    AudioFormatError,
    AudioTooLongError,
    ModelUnavailableError,
    Segment,
    TranscriberBusyError,
    TranscriptionCancelled,
    TranscriptionResult,
)

pytestmark = pytest.mark.integration

CONTENT = b"fake audio bytes"


def _result(segments=None, channels=2, duration=183.44) -> TranscriptionResult:
    """Результат обработки для подмены transcribe_bytes."""
    if segments is None:
        segments = [
            Segment(0.523, 3.104, "operator", 1, "Добрый день"),
            Segment(3.4, 5.85, "client", 0, "Здравствуйте"),
        ]
    return TranscriptionResult(duration=duration, channels=channels, segments=segments)


@pytest.fixture
def valid_type():
    """Проверка соответствия типа файла считается пройденной."""
    with patch("app.main.validate_file_type", return_value=(True, None)):
        yield


@pytest.fixture
def transcribe():
    """Подмена тяжёлой обработки; по умолчанию возвращает обычный результат."""
    with patch("app.main.transcribe_bytes", return_value=_result()) as mocked:
        yield mocked


def _post(client, name="call.mp3", content=CONTENT, **data):
    """POST /v1/transcribe с файлом и полями формы."""
    return client.post(
        "/v1/transcribe",
        files={"file": (name, BytesIO(content), "audio/mpeg")},
        data=data,
    )


class TestTranscribeSuccess:
    """Успешные ответы."""

    def test_200_contract(self, test_client, valid_type, transcribe):
        """Поля ответа соответствуют контракту, filename и external_id возвращены."""
        response = _post(
            test_client,
            name="звонок.mp3",
            channel_labels="client,operator",
            external_id="rec-123",
        )

        assert response.status_code == 200
        body = response.json()
        assert body == {
            "status": "success",
            "filename": "звонок.mp3",
            "external_id": "rec-123",
            "duration": 183.4,
            "channels": 2,
            "model": settings.TRANSCRIPTION_MODEL,
            "language": "ru",
            "text_status": "ok",
            "text": "Добрый день Здравствуйте",
            "segments": [
                {
                    "start": 0.52,
                    "end": 3.1,
                    "speaker": "operator",
                    "channel": 1,
                    "text": "Добрый день",
                },
                {
                    "start": 3.4,
                    "end": 5.85,
                    "speaker": "client",
                    "channel": 0,
                    "text": "Здравствуйте",
                },
            ],
        }

    def test_processing_arguments(self, test_client, valid_type, transcribe):
        """В обработку уходят содержимое, расширение, метки, флаг отмены и дедлайн."""
        _post(test_client, channel_labels=" client , ,operator")

        args, kwargs = transcribe.call_args
        assert args == (CONTENT,)
        assert kwargs["extension"] == "mp3"
        assert kwargs["channel_labels"] == ["client", "", "operator"]
        assert isinstance(kwargs["cancel_event"], threading.Event)
        assert isinstance(kwargs["deadline"], float)

    def test_no_speech_is_200(self, test_client, valid_type, transcribe):
        """Отсутствие речи — это успешный ответ с text_status=no_speech."""
        transcribe.return_value = _result(segments=[], channels=1, duration=3.0)

        response = _post(test_client)

        assert response.status_code == 200
        body = response.json()
        assert body["text_status"] == "no_speech"
        assert body["text"] == ""
        assert body["segments"] == []
        assert body["external_id"] is None

    def test_external_id_unicode_and_max_length(
        self, test_client, valid_type, transcribe
    ):
        """external_id с юникодом и длиной ровно 128 символов возвращается как есть."""
        unicode_id = "запись №1 🙂"
        long_id = "я" * 128

        assert _post(test_client, external_id=unicode_id).json()["external_id"] == (
            unicode_id
        )
        assert _post(test_client, external_id=long_id).json()["external_id"] == long_id


class TestTranscribeErrors:
    """Ошибки запроса и обработки."""

    def test_external_id_too_long_400(self, test_client, valid_type, transcribe):
        """external_id длиннее 128 символов отклоняется."""
        response = _post(test_client, external_id="я" * 129)

        assert response.status_code == 400
        assert response.json()["status"] == "error"
        transcribe.assert_not_called()

    def test_missing_content_length_400(self):
        """Без размера файла (нет Content-Length) — 400."""
        fake_file = SimpleNamespace(filename="call.mp3", size=None)

        response = asyncio.run(
            app_main.transcribe(file=fake_file, channel_labels=None, external_id=None)
        )

        assert response.status_code == 400
        assert b"Content-Length" in response.body

    def test_empty_file_422(self, test_client, valid_type, transcribe):
        """Пустой файл — 422."""
        response = _post(test_client, content=b"")

        assert response.status_code == 422
        assert response.json()["status"] == "error"
        transcribe.assert_not_called()

    def test_too_large_413(self, test_client, valid_type, transcribe, monkeypatch):
        """Файл больше MAX_FILE_SIZE — 413 в формате ошибки API."""
        monkeypatch.setattr(settings, "MAX_FILE_SIZE", 5)

        response = _post(test_client)

        assert response.status_code == 413
        assert response.json()["status"] == "error"
        assert response.json()["filename"] == "call.mp3"
        transcribe.assert_not_called()

    def test_unsupported_extension_415(self, test_client, transcribe):
        """Расширение вне AUDIO_FORMATS — 415 с перечнем допустимых."""
        response = _post(test_client, name="notes.txt")

        assert response.status_code == 415
        assert "mp3" in response.json()["message"]
        transcribe.assert_not_called()

    def test_mime_mismatch_415(self, test_client, transcribe):
        """Текст под видом mp3 отклоняется проверкой содержимого."""
        response = _post(test_client, content=b"just some plain text, not audio")

        assert response.status_code == 415
        transcribe.assert_not_called()

    @pytest.mark.parametrize(
        "error,status",
        [
            (AudioTooLongError("Запись слишком длинная."), 413),
            (AudioFormatError("Файл повреждён."), 422),
            (ModelUnavailableError("Модель недоступна."), 503),
            (TranscriberBusyError("Занято."), 503),
        ],
    )
    def test_transcription_errors_map_to_status(
        self, test_client, valid_type, transcribe, error, status
    ):
        """Ошибки обработки возвращаются со своим кодом и сообщением."""
        transcribe.side_effect = error

        response = _post(test_client)

        assert response.status_code == status
        body = response.json()
        assert body["status"] == "error"
        assert body["filename"] == "call.mp3"
        assert body["message"] == error.message

    def test_busy_503_has_retry_after(self, test_client, valid_type, transcribe):
        """Занятый сервис просит повторить запрос позже."""
        transcribe.side_effect = TranscriberBusyError("Занято.")

        response = _post(test_client)

        assert response.headers["retry-after"] == "30"

    def test_disabled_503(self, test_client, valid_type, transcribe, monkeypatch):
        """При ENABLE_TRANSCRIPTION=false эндпоинт отвечает 503."""
        monkeypatch.setattr(settings, "ENABLE_TRANSCRIPTION", False)

        response = _post(test_client)

        assert response.status_code == 503
        assert response.json()["status"] == "error"
        transcribe.assert_not_called()

    def test_timeout_504_sets_cancel_event(self, test_client, valid_type, monkeypatch):
        """По таймауту клиент получает 504, а рабочий поток — флаг отмены."""
        monkeypatch.setattr(settings, "TRANSCRIPTION_TIMEOUT_SECONDS", 0.05)
        captured = {}

        def blocking(content, *, cancel_event, **kwargs):
            captured["event"] = cancel_event
            cancel_event.wait(timeout=5)
            raise TranscriptionCancelled()

        with patch("app.main.transcribe_bytes", side_effect=blocking):
            response = _post(test_client)

        assert response.status_code == 504
        assert response.json()["status"] == "error"
        assert captured["event"].is_set()

    def test_cancelled_from_worker_is_504(self, test_client, valid_type, transcribe):
        """Отмена, пришедшая из рабочего потока (дедлайн), тоже даёт 504."""
        transcribe.side_effect = TranscriptionCancelled()

        response = _post(test_client)

        assert response.status_code == 504

    def test_unexpected_error_is_500_without_details(
        self, test_client, valid_type, transcribe
    ):
        """Непредвиденный сбой — 500 без внутренних деталей в ответе."""
        transcribe.side_effect = RuntimeError("секретная внутренняя деталь")

        response = _post(test_client)

        assert response.status_code == 500
        assert response.json()["status"] == "error"
        assert "секретная" not in response.text


class TestTranscribeSecurity:
    """Авторизация и изоляция от /v1/extract/*."""

    def test_api_key_required(self, monkeypatch, valid_type):
        """При AUTH_MODE=apikey запрос без ключа получает 401, с ключом — 200."""
        monkeypatch.setattr(settings, "AUTH_MODE", "apikey")
        monkeypatch.setattr(settings, "API_KEYS", ["test-key-123"])

        with patch("app.main.transcribe_bytes", return_value=_result()):
            with TestClient(app) as client:
                assert _post(client).status_code == 401
                ok = client.post(
                    "/v1/transcribe",
                    files={"file": ("call.mp3", BytesIO(CONTENT), "audio/mpeg")},
                    headers={"X-API-Key": "test-key-123"},
                )

        assert ok.status_code == 200

    def test_extract_endpoint_still_rejects_audio(self, test_client):
        """/v1/extract/file по-прежнему не принимает аудио."""
        response = test_client.post(
            "/v1/extract/file",
            files={"file": ("call.mp3", BytesIO(b"ID3" + b"\x00" * 64), "audio/mpeg")},
        )

        assert response.status_code == 415
