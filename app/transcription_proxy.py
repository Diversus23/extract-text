"""Пересылка /v1/transcribe в сервис api-audio, когда этот сервис сам не расшифровывает."""

import asyncio
import logging
import time
from typing import AsyncIterator, Optional

import httpx
from starlette.datastructures import Headers
from starlette.responses import JSONResponse, Response
from starlette.types import Receive, Scope, Send

from app.config import settings

logger = logging.getLogger(__name__)

UPSTREAM_CONNECT_TIMEOUT_SECONDS = 5
# Запас сверх таймаута расшифровки и ожидания в очереди: собственный ответ api-audio
# (включая 504) должен дойти раньше, чем оборвёт прокси.
UPSTREAM_RESPONSE_MARGIN_SECONDS = 30
UPSTREAM_RETRY_AFTER_SECONDS = 30
READINESS_PROBE_TIMEOUT_SECONDS = 5

_HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)
# host задаёт httpx по адресу api-audio; origin не пересылаем, чтобы CORS-заголовки
# выставлял только этот сервис, а не оба.
_REQUEST_SKIP = _HOP_BY_HOP | {"host", "origin"}
# date и server добавляет uvicorn; длину и кодирование тела пересчитывает Response.
_RESPONSE_SKIP = _HOP_BY_HOP | {"date", "server", "content-length", "content-encoding"}


def proxy_enabled() -> bool:
    """Расшифровка выключена здесь, но задан сервис, куда её пересылать."""
    return not settings.ENABLE_TRANSCRIPTION and bool(
        settings.TRANSCRIPTION_UPSTREAM_URL
    )


def error_response(
    code: int, message: str, headers: Optional[dict] = None
) -> JSONResponse:
    """Ошибка /v1/transcribe до разбора формы: имя файла ещё неизвестно."""
    return JSONResponse(
        status_code=code,
        content={"status": "error", "filename": "unknown_file", "message": message},
        headers=headers,
    )


def _make_client(timeout: httpx.Timeout) -> httpx.AsyncClient:
    # trust_env=False: внутренний адрес не должен уходить через HTTP(S)_PROXY окружения.
    return httpx.AsyncClient(timeout=timeout, trust_env=False)


class _UploadRejected(Exception):
    """Загрузка отклонена по размеру или времени, ответ клиенту уже готов."""

    def __init__(self, response: Response) -> None:
        super().__init__()
        self.response = response


class _ClientGone(Exception):
    """Клиент закрыл соединение, не дослав тело запроса."""


async def forward_transcribe(
    scope: Scope,
    receive: Receive,
    send: Send,
    *,
    limit: int,
    size_error_message: str,
) -> None:
    """Потоком пересылает запрос в api-audio и возвращает его ответ без изменений."""
    upload_done = asyncio.Event()
    received = 0
    upload_deadline = time.monotonic() + settings.PROCESSING_TIMEOUT_SECONDS

    async def request_body() -> AsyncIterator[bytes]:
        nonlocal received
        while True:
            try:
                message = await asyncio.wait_for(
                    receive(), timeout=max(0, upload_deadline - time.monotonic())
                )
            except asyncio.TimeoutError as error:
                raise _UploadRejected(
                    error_response(408, "Превышено время загрузки аудиофайла.")
                ) from error
            if message["type"] == "http.disconnect":
                raise _ClientGone
            body = message.get("body", b"")
            received += len(body)
            if received > limit:
                raise _UploadRejected(error_response(413, size_error_message))
            if body:
                yield body
            if not message.get("more_body", False):
                upload_done.set()
                return

    headers = [
        (name, value)
        for name, value in Headers(scope=scope).items()
        if name not in _REQUEST_SKIP
    ]
    timeout = httpx.Timeout(
        settings.TRANSCRIPTION_TIMEOUT_SECONDS
        + settings.TRANSCRIPTION_QUEUE_WAIT_SECONDS
        + UPSTREAM_RESPONSE_MARGIN_SECONDS,
        connect=UPSTREAM_CONNECT_TIMEOUT_SECONDS,
    )
    try:
        async with _make_client(timeout) as client:
            request = client.build_request(
                "POST",
                f"{settings.TRANSCRIPTION_UPSTREAM_URL}/v1/transcribe",
                headers=headers,
                content=request_body(),
            )
            response = await _send_unless_client_left(
                client, request, receive, upload_done
            )
    except _ClientGone:
        await _client_closed(scope, receive, send)
        return
    except _UploadRejected as rejected:
        await rejected.response(scope, receive, send)
        return
    except (httpx.ConnectError, httpx.ConnectTimeout) as error:
        logger.error(
            f"Сервис расшифровки {settings.TRANSCRIPTION_UPSTREAM_URL}: {error!r}"
        )
        await error_response(
            503,
            "Сервис расшифровки аудио временно недоступен.",
            {"Retry-After": str(UPSTREAM_RETRY_AFTER_SECONDS)},
        )(scope, receive, send)
        return
    except httpx.TimeoutException:
        logger.error("Сервис расшифровки не ответил за отведённое время")
        await error_response(
            504, "Сервис расшифровки аудио не ответил за отведённое время."
        )(scope, receive, send)
        return
    except httpx.HTTPError as error:
        logger.error(f"Некорректный ответ сервиса расшифровки: {error!r}")
        await error_response(
            502, "Сервис расшифровки аудио вернул некорректный ответ."
        )(scope, receive, send)
        return

    if response is None:
        await _client_closed(scope, receive, send)
        return
    await Response(
        content=response.content,
        status_code=response.status_code,
        headers={
            name: value
            for name, value in response.headers.items()
            if name not in _RESPONSE_SKIP
        },
    )(scope, receive, send)


async def _client_closed(scope: Scope, receive: Receive, send: Send) -> None:
    """Клиент ушёл: uvicorn отбросит ответ, но вышестоящим middleware он нужен."""
    logger.info("Клиент закрыл соединение до завершения запроса")
    await error_response(499, "Клиент закрыл соединение.")(scope, receive, send)


async def _send_unless_client_left(
    client: httpx.AsyncClient,
    request: httpx.Request,
    receive: Receive,
    upload_done: asyncio.Event,
) -> Optional[httpx.Response]:
    """Ждёт ответ api-audio; если клиент ушёл раньше, прерывает запрос и даёт None."""

    async def client_left() -> None:
        await upload_done.wait()
        while (await receive())["type"] != "http.disconnect":
            pass

    sending = asyncio.ensure_future(client.send(request))
    watching = asyncio.ensure_future(client_left())
    try:
        await asyncio.wait({sending, watching}, return_when=asyncio.FIRST_COMPLETED)
        return sending.result() if sending.done() else None
    finally:
        sending.cancel()
        watching.cancel()
        await asyncio.gather(sending, watching, return_exceptions=True)


async def probe_readiness() -> JSONResponse:
    """Готовность модели в api-audio для GET /health?check=transcription."""
    try:
        async with _make_client(
            httpx.Timeout(READINESS_PROBE_TIMEOUT_SECONDS)
        ) as client:
            response = await client.get(
                f"{settings.TRANSCRIPTION_UPSTREAM_URL}/health",
                params={"check": "transcription"},
            )
        return JSONResponse(status_code=response.status_code, content=response.json())
    except (httpx.HTTPError, ValueError) as error:
        logger.warning(f"Проба сервиса расшифровки не прошла: {error!r}")
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "transcription": "unreachable"},
        )
