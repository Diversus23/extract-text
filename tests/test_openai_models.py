"""Model discovery advertises the configured speech model without inference."""

import pytest

from app.config import settings


@pytest.mark.parametrize(
    "enabled,upstream,count",
    [(True, "", 1), (False, "http://audio", 1), (False, "", 0)],
)
def test_models(test_client, monkeypatch, enabled, upstream, count):
    monkeypatch.setattr(settings, "AUTH_MODE", "none")
    monkeypatch.setattr(settings, "ENABLE_TRANSCRIPTION", enabled)
    monkeypatch.setattr(settings, "TRANSCRIPTION_UPSTREAM_URL", upstream)
    response = test_client.get("/v1/models")
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "list"
    assert len(body["data"]) == count
    if count:
        model = body["data"][0]
        assert model["id"] == settings.TRANSCRIPTION_MODEL
        assert model["architecture"] == {
            "input_modalities": ["audio"],
            "output_modalities": ["text"],
        }
        assert isinstance(model["created"], int)
        assert model["created"] > 0
        assert model["owned_by"] == "extract-text"


def test_version(test_client):
    assert test_client.get("/").json()["version"] == "1.14.0"
