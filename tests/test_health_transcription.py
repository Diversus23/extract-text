"""Тесты прогрева модели при старте и пробы готовности /health?check=transcription."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.transcription import ModelUnavailableError

pytestmark = pytest.mark.integration


def _fake_transcriber(status: str = "ready", warm_up_error=None) -> MagicMock:
    """Transcriber-заглушка с заданным статусом готовности."""
    fake = MagicMock()
    fake.status = status
    fake.warm_up.side_effect = warm_up_error
    return fake


class TestReadinessProbe:
    """Проба готовности модели для Docker healthcheck."""

    @pytest.mark.parametrize("status", ["ready", "unavailable", "not_loaded"])
    def test_plain_health_is_unchanged(self, test_client, status):
        """Обычный /health всегда отвечает так же, как раньше."""
        with patch("app.main.get_transcriber", return_value=_fake_transcriber(status)):
            response = test_client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_probe_ready_is_200(self, test_client):
        """Модель загружена: проба отвечает 200."""
        with patch("app.main.get_transcriber", return_value=_fake_transcriber("ready")):
            response = test_client.get("/health?check=transcription")

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "transcription": "ready"}

    @pytest.mark.parametrize("status", ["unavailable", "not_loaded"])
    def test_probe_not_ready_is_503(self, test_client, status):
        """Модель не загружена или недоступна: проба отвечает 503."""
        with patch("app.main.get_transcriber", return_value=_fake_transcriber(status)):
            response = test_client.get("/health?check=transcription")

        assert response.status_code == 503
        assert response.json() == {"status": "unavailable", "transcription": status}

    def test_probe_when_disabled_is_503(self, test_client, monkeypatch):
        """Расшифровка отключена: проба сообщает disabled."""
        monkeypatch.setattr(settings, "ENABLE_TRANSCRIPTION", False)

        response = test_client.get("/health?check=transcription")

        assert response.status_code == 503
        assert response.json() == {"status": "unavailable", "transcription": "disabled"}


class TestWarmUpAtStartup:
    """Прогрев модели в lifespan."""

    def test_warm_up_runs_when_enabled(self):
        """При включённой расшифровке модель прогревается на старте."""
        fake = _fake_transcriber()

        with patch("app.main.get_transcriber", return_value=fake):
            with TestClient(app):
                pass

        fake.warm_up.assert_called_once_with()

    def test_warm_up_skipped_when_disabled(self, monkeypatch):
        """При отключённой расшифровке модель не грузится."""
        monkeypatch.setattr(settings, "ENABLE_TRANSCRIPTION", False)
        fake = _fake_transcriber()

        with patch("app.main.get_transcriber", return_value=fake):
            with TestClient(app):
                pass

        fake.warm_up.assert_not_called()

    def test_warm_up_failure_does_not_break_startup(self):
        """Сбой прогрева не роняет API: документы продолжают обрабатываться."""
        fake = _fake_transcriber(
            status="unavailable", warm_up_error=ModelUnavailableError("нет весов")
        )

        with patch("app.main.get_transcriber", return_value=fake):
            with TestClient(app) as client:
                health = client.get("/health")
                formats = client.get("/v1/supported-formats")

        assert health.status_code == 200
        assert formats.status_code == 200
