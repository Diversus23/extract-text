"""Both API credentials use the same verification and deterministic priority."""

import pytest

from app.config import settings


@pytest.fixture
def protected(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_MODE", "apikey")
    monkeypatch.setattr(settings, "API_KEYS", ["secret"])


@pytest.mark.parametrize("path", ["/v1/models", "/v1/supported-formats"])
@pytest.mark.parametrize(
    "headers,status",
    [
        ({"Authorization": "Bearer secret"}, 200),
        ({"Authorization": "bearer secret"}, 200),
        ({"X-API-Key": "secret"}, 200),
        ({"X-API-Key": "wrong", "Authorization": "Bearer secret"}, 401),
        ({"X-API-Key": "secret", "Authorization": "Bearer wrong"}, 200),
        ({"Authorization": "Basic secret"}, 401),
        ({}, 401),
    ],
)
def test_credentials(test_client, protected, path, headers, status):
    response = test_client.get(path, headers=headers)
    assert response.status_code == status
    if status == 401:
        assert ("error" if path == "/v1/models" else "detail") in response.json()
        assert response.headers["www-authenticate"] == (
            "Bearer" if path == "/v1/models" else "ApiKey"
        )


def test_ingress_rejects_before_parsing(test_client, protected):
    response = test_client.post("/v1/audio/transcriptions", content=b"not multipart")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_api_key"
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("path", ["/v1/models", "/v1/supported-formats"])
@pytest.mark.parametrize(
    "headers",
    [
        {"Authorization": "Bearer invalid"},
        {"X-API-Key": "invalid"},
        {"Authorization": "Bearer invalid", "X-API-Key": "invalid"},
    ],
)
def test_disabled_auth_ignores_invalid_credentials(
    test_client, monkeypatch, path, headers
):
    monkeypatch.setattr(settings, "AUTH_MODE", "none")
    assert test_client.get(path, headers=headers).status_code == 200
