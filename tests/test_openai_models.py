"""Model discovery advertises the public models without inference."""

import pytest

from app.config import settings
from app.openai_compat import EXTRACTION_MODEL_ID, PUBLIC_MODEL_PREFIX

TRANSCRIPTION_ID = "softonit/gigaam-v3-e2e-rnnt"


def get_models(test_client, monkeypatch, enabled, upstream):
    monkeypatch.setattr(settings, "AUTH_MODE", "none")
    monkeypatch.setattr(settings, "ENABLE_TRANSCRIPTION", enabled)
    monkeypatch.setattr(settings, "TRANSCRIPTION_UPSTREAM_URL", upstream)
    response = test_client.get("/v1/models")
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "list"
    return body["data"]


@pytest.mark.parametrize(
    "enabled,upstream",
    [(True, ""), (False, "http://audio")],
)
def test_models_with_transcription(test_client, monkeypatch, enabled, upstream):
    data = get_models(test_client, monkeypatch, enabled, upstream)
    assert [model["id"] for model in data] == [EXTRACTION_MODEL_ID, TRANSCRIPTION_ID]
    extraction, transcription = data
    assert extraction["architecture"] == {
        "input_modalities": ["file"],
        "output_modalities": ["text"],
    }
    assert transcription["architecture"] == {
        "input_modalities": ["audio"],
        "output_modalities": ["text"],
    }
    for model in data:
        assert model["object"] == "model"
        assert model["owned_by"] == "extract-text"
        assert isinstance(model["created"], int)
        assert model["created"] > 0
        assert model["name"]
        assert model["description"]


def test_models_without_transcription_keep_extraction(test_client, monkeypatch):
    data = get_models(test_client, monkeypatch, False, "")
    assert [model["id"] for model in data] == [EXTRACTION_MODEL_ID]


def test_extraction_description_points_to_chat_completions(test_client, monkeypatch):
    data = get_models(test_client, monkeypatch, False, "")
    description = data[0]["description"]
    assert "/v1/chat/completions" in description
    assert "type=file" in description
    assert "/v1/extract/file" not in description


def test_model_ids_contract():
    # 1С относит модель к извлечению текста по подстроке «extract» в идентификаторе
    assert EXTRACTION_MODEL_ID == "softonit/extracttext"
    assert EXTRACTION_MODEL_ID.startswith(PUBLIC_MODEL_PREFIX)
    assert "extract" in EXTRACTION_MODEL_ID


def test_prefix_is_not_doubled(test_client, monkeypatch):
    monkeypatch.setattr(settings, "TRANSCRIPTION_MODEL", TRANSCRIPTION_ID)
    data = get_models(test_client, monkeypatch, True, "")
    assert data[1]["id"] == TRANSCRIPTION_ID


def test_version(test_client):
    assert test_client.get("/").json()["version"] == "1.16.0"
