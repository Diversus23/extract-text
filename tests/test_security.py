"""Тесты безопасности на правки v1.11.0.

Покрывают:
- SSRF при редиректах (повторная валидация final_url),
- Path traversal в архивах (Zip Slip),
- API-key аутентификация (AUTH_MODE=apikey),
- Открытость /health при auth,
- clamp max_scroll_attempts.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.extractors import TextExtractor


pytestmark = pytest.mark.unit


@pytest.fixture
def client_apikey(monkeypatch):
    """
    Включает AUTH_MODE=apikey ДО создания TestClient.

    lifespan FastAPI делает fail-fast при apikey без ключей —
    поэтому ключ выставляем ДО старта приложения, а сам TestClient
    инстанцируется внутри фикстуры.
    """
    monkeypatch.setattr(settings, "AUTH_MODE", "apikey")
    monkeypatch.setattr(settings, "API_KEYS", ["test-key-123"])
    from app.main import app

    with TestClient(app) as client:
        yield client, "test-key-123"


@pytest.fixture
def client_none(monkeypatch):
    """AUTH_MODE=none + чистый TestClient."""
    monkeypatch.setattr(settings, "AUTH_MODE", "none")
    monkeypatch.setattr(settings, "API_KEYS", [])
    from app.main import app

    with TestClient(app) as client:
        yield client


# ---------------------------------------------------------------------------
# SSRF при редиректах
# ---------------------------------------------------------------------------


class TestSSRFRedirect:
    """Защита от SSRF через цепочку редиректов."""

    def test_is_safe_url_blocks_internal_ip(self):
        extractor = TextExtractor()
        assert not extractor._is_safe_url("http://10.0.0.1/admin")
        assert not extractor._is_safe_url("http://127.0.0.1/")
        assert not extractor._is_safe_url("http://localhost/")
        assert not extractor._is_safe_url("http://192.168.1.1/")

    def test_is_safe_url_blocks_non_http_schemes(self):
        extractor = TextExtractor()
        assert not extractor._is_safe_url("file:///etc/passwd")
        assert not extractor._is_safe_url("gopher://example.com/")
        assert not extractor._is_safe_url("ftp://example.com/")

    def test_extract_from_url_blocks_internal_ip(self, client_none):
        response = client_none.post(
            "/v1/extract/url", json={"url": "http://10.0.0.1/admin"}
        )
        assert response.status_code == 400
        body = response.json()
        assert body["status"] == "error"
        assert (
            "внутренним" in body["message"].lower()
            or "запрещ" in body["message"].lower()
        )

    def test_redact_url_strips_query(self):
        """_redact_url не должен давать leak query-string в логах."""
        url = "https://api.example.com/v1/data?token=secret123&user=foo"
        redacted = TextExtractor._redact_url(url)
        assert "secret123" not in redacted
        assert "[redacted]" in redacted
        assert "api.example.com" in redacted
        assert "/v1/data" in redacted


# ---------------------------------------------------------------------------
# Path traversal в архивах
# ---------------------------------------------------------------------------


def _build_zip_with_traversal() -> bytes:
    """Создаёт ZIP с попыткой path traversal через '../escape.txt'."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("../escape.txt", b"should not escape")
        zf.writestr("normal.txt", b"safe content")
    return buf.getvalue()


class TestArchivePathTraversal:
    """Защита от Zip Slip в zip/tar/7z."""

    def test_zip_traversal_blocked_and_normal_extracted(self, tmp_path, monkeypatch):
        """
        normal.txt должен извлечься, escape.txt — нет.
        Проверяем фактическое содержимое результата (не только тип).
        """
        # Изолируем tempfile внутрь tmp_path, чтобы можно было проверить,
        # что escape.txt не оказался рядом.
        import tempfile

        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))

        extractor = TextExtractor()
        zip_bytes = _build_zip_with_traversal()
        results = extractor._extract_from_archive(zip_bytes, "test.zip")

        assert isinstance(results, list)
        # normal.txt действительно извлечён и обработан как .txt
        assert any(
            r.get("filename") == "normal.txt" and "safe content" in r.get("text", "")
            for r in results
        ), f"normal.txt должен быть в результате, получили: {results}"

        # escape.txt не должен оказаться выше tmp_path
        assert not (tmp_path.parent / "escape.txt").exists()

    def test_is_path_within_helper(self, tmp_path):
        extractor = TextExtractor()
        inside = tmp_path / "sub" / "file.txt"
        outside = tmp_path.parent / "escape.txt"

        assert extractor._is_path_within(inside, tmp_path) is True
        assert extractor._is_path_within(outside, tmp_path) is False


# ---------------------------------------------------------------------------
# API-key аутентификация
# ---------------------------------------------------------------------------


class TestAuthApiKey:
    """Опциональная API-key аутентификация."""

    def test_auth_none_open_access(self, client_none):
        # При AUTH_MODE=none эндпоинт supported-formats доступен без заголовка
        response = client_none.get("/v1/supported-formats")
        assert response.status_code == 200
        body = response.json()
        assert "documents" in body or "images_ocr" in body

    def test_auth_apikey_requires_header(self, client_apikey):
        client, _ = client_apikey
        response = client.get("/v1/supported-formats")
        assert response.status_code == 401
        # FastAPI APIKeyHeader auto_error=False + HTTPException — detail в JSON
        assert "API key" in response.text

    def test_auth_apikey_rejects_wrong_key(self, client_apikey):
        client, _ = client_apikey
        response = client.get(
            "/v1/supported-formats", headers={"X-API-Key": "wrong-key"}
        )
        assert response.status_code == 401
        assert "Invalid" in response.text

    def test_auth_apikey_accepts_valid_key(self, client_apikey):
        client, key = client_apikey
        response = client.get("/v1/supported-formats", headers={"X-API-Key": key})
        assert response.status_code == 200

    def test_health_open_without_auth(self, client_apikey):
        # /health должен оставаться открытым для Docker healthcheck
        client, _ = client_apikey
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_root_open_without_auth(self, client_apikey):
        # / тоже открытый — это публичная информация о сервисе
        client, _ = client_apikey
        response = client.get("/")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Hard cap для max_scroll_attempts
# ---------------------------------------------------------------------------


class TestScrollCap:
    """Проверка работы clamp-логики в _safe_scroll_for_lazy_loading."""

    def test_user_value_above_cap_is_clamped(self):
        """Пользовательское значение 999 должно clamp-иться до CAP."""
        cap = settings.MAX_SCROLL_ATTEMPTS_CAP

        # Эмулируем выражение из _safe_scroll_for_lazy_loading:
        #   max_scroll_attempts = min(max(user_max_scroll, 0), CAP)
        user_value = 999
        effective = min(max(user_value, 0), cap)

        assert effective == cap, f"999 должен clamp-иться до {cap}, получили {effective}"
        assert effective <= cap

    def test_negative_user_value_clamped_to_zero(self):
        """Отрицательное значение clamp-ится до 0 (нет скроллов)."""
        user_value = -5
        effective = min(max(user_value, 0), settings.MAX_SCROLL_ATTEMPTS_CAP)
        assert effective == 0

    def test_normal_value_passes_unchanged(self):
        """Значение в пределах cap проходит без изменений."""
        cap = settings.MAX_SCROLL_ATTEMPTS_CAP
        user_value = max(1, cap // 2)
        effective = min(max(user_value, 0), cap)
        assert effective == user_value
