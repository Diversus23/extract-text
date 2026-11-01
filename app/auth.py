"""Опциональная API-key аутентификация для extract-эндпоинтов."""

import logging
import secrets
from typing import Optional

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

logger = logging.getLogger(__name__)

# Security scheme регистрируется в OpenAPI — Swagger UI покажет кнопку
# "Authorize" с полем X-API-Key, ReDoc — секцию "Authentication".
# auto_error=False, чтобы при AUTH_MODE=none запросы без заголовка не отклонялись
# на уровне scheme — решение принимает verify_api_key.
api_key_scheme = APIKeyHeader(
    name="X-API-Key",
    description=(
        "API-ключ для доступа к extract-эндпоинтам. "
        "Требуется только при AUTH_MODE=apikey, иначе игнорируется."
    ),
    auto_error=False,
)


bearer_scheme = HTTPBearer(auto_error=False)


def extract_api_key(x_api_key=None, authorization=None):
    """Извлекает ключ: непустой X-API-Key имеет приоритет над Bearer."""
    if x_api_key:
        return x_api_key
    if authorization:
        scheme, _, credentials = authorization.partition(" ")
        if scheme.lower() == "bearer":
            return credentials.strip() or None
    return None


def check_api_key(key):
    """Проверяет режим доступа и сравнивает ключи за постоянное время."""
    if settings.AUTH_MODE == "none":
        return
    if settings.AUTH_MODE != "apikey":
        raise HTTPException(500, "Server auth misconfiguration")
    if key and any(
        secrets.compare_digest(key.encode("utf-8"), valid.encode("utf-8"))
        for valid in settings.API_KEYS
    ):
        return
    raise HTTPException(
        401,
        "Invalid API key" if key else "API key required",
        headers={"WWW-Authenticate": "ApiKey"},
    )


async def verify_api_key(
    request: Request,
    x_api_key: Optional[str] = Security(api_key_scheme),
    bearer: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
) -> None:
    """Проверяет оба способа авторизации для прежних маршрутов API."""
    check_api_key(extract_api_key(x_api_key, request.headers.get("authorization")))
