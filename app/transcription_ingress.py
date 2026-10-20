"""Защита приёма аудио до разбора multipart и записи временных файлов."""

import asyncio
import time

from fastapi import HTTPException
from starlette.datastructures import Headers
from starlette.formparsers import MultiPartException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.auth import verify_api_key
from app.config import settings
from app.transcription import TranscriptionError, get_transcriber
from app.transcription_proxy import error_response as _error
from app.transcription_proxy import forward_transcribe, proxy_enabled

# Небольшой запас для заголовков multipart и полей формы; размер самого файла
# дополнительно проверяет эндпоинт. Общий объём тела ограничен и при ложном CL.
MULTIPART_OVERHEAD_BYTES = 64 * 1024


class TranscriptionIngressMiddleware:
    """Проверяет доступ, размер запроса и свободный слот до чтения тела.

    Если расшифровка выключена, но задан TRANSCRIPTION_UPSTREAM_URL, после тех же
    проверок запрос пересылается в сервис api-audio.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Сохраняет следующее приложение в цепочке middleware."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Ограничивает приём аудио, остальные маршруты передаёт приложению."""
        path = scope.get("path", "")
        root_path = scope.get("root_path", "")
        if root_path and path.startswith(root_path + "/"):
            path = path[len(root_path) :]
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or path.rstrip("/") != "/v1/transcribe"
        ):
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        try:
            await verify_api_key(headers.get("x-api-key"))
        except HTTPException as error:
            await JSONResponse(
                status_code=error.status_code,
                content={"detail": error.detail},
                headers=error.headers,
            )(scope, receive, send)
            return

        forwarding = proxy_enabled()
        if not settings.ENABLE_TRANSCRIPTION and not forwarding:
            await _error(503, "Расшифровка аудио отключена на этом сервере.")(
                scope, receive, send
            )
            return

        lengths = headers.getlist("content-length")
        if (
            len(lengths) != 1
            or not lengths[0].isascii()
            or not lengths[0].isdigit()
            or len(lengths[0]) > 20
        ):
            await _error(400, "Требуется корректный заголовок Content-Length.")(
                scope, receive, send
            )
            return

        file_limit = settings.MAX_AUDIO_FILE_SIZE
        limit = file_limit + MULTIPART_OVERHEAD_BYTES
        size_error_message = (
            "Размер тела запроса превышает допустимый лимит. "
            f"Аудиофайл — до {file_limit / (1024 * 1024):g} МиБ ({file_limit} байт)."
        )
        if int(lengths[0]) > limit:
            await _error(413, size_error_message)(scope, receive, send)
            return

        if forwarding:
            await forward_transcribe(
                scope,
                receive,
                send,
                limit=limit,
                size_error_message=size_error_message,
            )
            return

        try:
            slot = await get_transcriber().reserve()
        except TranscriptionError as error:
            retry = (
                {"Retry-After": str(error.retry_after)} if error.retry_after else None
            )
            await _error(error.status_code, error.message, retry)(scope, receive, send)
            return

        scope.setdefault("state", {})["transcription_slot"] = slot
        received = 0
        rejection = None
        error_sent = False
        upload_deadline = time.monotonic() + settings.PROCESSING_TIMEOUT_SECONDS

        async def bounded_receive() -> Message:
            nonlocal received, rejection
            try:
                message = await asyncio.wait_for(
                    receive(), timeout=max(0, upload_deadline - time.monotonic())
                )
            except asyncio.TimeoutError as error:
                rejection = _error(408, "Превышено время загрузки аудиофайла.")
                raise MultiPartException("Превышено время загрузки.") from error
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    rejection = _error(413, size_error_message)
                    # Парсер закрывает уже созданные временные файлы при этой ошибке.
                    raise MultiPartException("Превышен размер тела запроса.")
            return message

        async def bounded_send(message: Message) -> None:
            nonlocal error_sent
            if rejection is not None:
                if not error_sent:
                    error_sent = True
                    await rejection(scope, receive, send)
                return
            await send(message)

        try:
            await self.app(scope, bounded_receive, bounded_send)
        finally:
            slot.release(unless_transferred=True)
