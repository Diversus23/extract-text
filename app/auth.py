"""Опциональная API-key аутентификация для extract-эндпоинтов."""

import logging
import secrets
from typing import Optional

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

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


async def verify_api_key(
    x_api_key: Optional[str] = Security(api_key_scheme),
) -> None:
    """
    FastAPI-dependency: проверяет API-ключ согласно AUTH_MODE.

    AUTH_MODE=none — пропускает любые запросы (default).
    AUTH_MODE=apikey — требует заголовок X-API-Key, сверяет со списком settings.API_KEYS
    через secrets.compare_digest (constant-time, защита от timing-attack).
    """
    if settings.AUTH_MODE == "none":
        return

    if settings.AUTH_MODE != "apikey":
        logger.error(
            f"Неизвестный AUTH_MODE: {settings.AUTH_MODE!r}, ожидается 'none' или 'apikey'"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server auth misconfiguration",
        )

    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    for valid_key in settings.API_KEYS:
        if secrets.compare_digest(x_api_key, valid_key):
            return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
        headers={"WWW-Authenticate": "ApiKey"},
    )
