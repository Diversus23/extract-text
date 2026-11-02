"""Необязательное поле model в POST /v1/extract/file."""

from unittest.mock import patch

import pytest

from app.config import settings

PATH = "/v1/extract/file"
CONTENT = "Тестовый текст для проверки\nВторая строка".encode("utf-8")

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def open_api(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_MODE", "none")


def post(client, data=None, content=CONTENT, name="test.txt"):
    return client.post(
        PATH,
        files={"file": (name, content, "text/plain")},
        data=data or {},
    )


def test_without_model_is_unchanged(test_client):
    response = post(test_client)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["filename"] == "test.txt"
    assert body["files"][0]["text"].startswith("Тестовый текст")
    assert set(body) == {"status", "filename", "count", "files"}


@pytest.mark.parametrize("model", ["", "softonit/extracttext"])
def test_empty_and_own_model_give_identical_body(test_client, model):
    baseline = post(test_client)
    response = post(test_client, {"model": model})
    assert response.status_code == 200
    assert response.json() == baseline.json()


@pytest.mark.parametrize(
    "model",
    ["other", "gigaam-v3-e2e-rnnt", "softonit/gigaam-v3-e2e-rnnt", "extracttext"],
)
def test_foreign_model_is_rejected_in_route_format(test_client, model):
    with patch("app.extractors.TextExtractor.extract_text") as extract:
        response = post(test_client, {"model": model}, name="doc.txt")
    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"status", "filename", "message"}
    assert body["status"] == "error"
    assert body["filename"] == "doc.txt"
    assert model in body["message"]
    assert "error" not in body
    extract.assert_not_called()


def test_long_model_is_truncated_in_message(test_client):
    response = post(test_client, {"model": "x" * 500})
    assert response.status_code == 404
    assert len(response.json()["message"]) < 200


def test_model_field_does_not_break_size_check(test_client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_FILE_SIZE", 10)
    response = post(test_client, {"model": "softonit/extracttext"})
    assert response.status_code == 413
    # без model результат тот же: file.size определяется при разборе multipart
    assert post(test_client).status_code == 413


def test_model_is_checked_before_file_is_read(test_client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_FILE_SIZE", 10)
    response = post(test_client, {"model": "other"})
    assert response.status_code == 404
