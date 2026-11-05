"""Авторизация и потоковый лимит документов до JSON/multipart-парсера."""

import asyncio
import time

from fastapi import HTTPException
from starlette.datastructures import Headers
from starlette.formparsers import MultiPartException
from starlette.responses import JSONResponse

from app.auth import check_api_key, extract_api_key
from app.config import settings


class DocumentIngressMiddleware:
    """Ограничивает приём документов до создания временных файлов."""

    def __init__(self, app):
        """Сохраняет следующее приложение."""
        self.app = app

    async def __call__(self, scope, receive, send):
        """Проверяет доступ, заявленный размер и фактическое чтение тела."""
        path = scope.get("path", "")
        root = scope.get("root_path", "")
        if root and path.startswith(root + "/"):
            path = path[len(root) :]
        path = path.rstrip("/")
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or path not in {"/v1/extract/file", "/v1/extract/base64", "/v1/extract/url"}
        ):
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        try:
            check_api_key(
                extract_api_key(headers.get("x-api-key"), headers.get("authorization"))
            )
        except HTTPException as error:
            await JSONResponse(
                {"detail": error.detail}, error.status_code, headers=error.headers
            )(scope, receive, send)
            return

        limit = settings.MAX_FILE_SIZE + 64 * 1024
        if path.endswith("/base64"):
            limit = 4 * ((settings.MAX_FILE_SIZE + 2) // 3) + 64 * 1024
        elif path.endswith("/url"):
            limit = 64 * 1024
        size_error = (
            "Request body too large"
            if path.endswith("/url")
            else "File size exceeds maximum allowed size"
        )
        lengths = headers.getlist("content-length")
        if lengths and (
            len(lengths) != 1
            or not lengths[0].isascii()
            or not lengths[0].isdigit()
            or len(lengths[0]) > 20
        ):
            await JSONResponse({"detail": "Invalid Content-Length"}, 400)(
                scope, receive, send
            )
            return
        if lengths and int(lengths[0]) > limit:
            await JSONResponse({"detail": size_error}, 413)(scope, receive, send)
            return

        received = 0
        rejection = None
        sent = False
        deadline = time.monotonic() + settings.PROCESSING_TIMEOUT_SECONDS

        async def bounded_receive():
            nonlocal received, rejection
            try:
                message = await asyncio.wait_for(
                    receive(), max(0, deadline - time.monotonic())
                )
            except asyncio.TimeoutError as error:
                rejection = JSONResponse({"detail": "Upload timed out"}, 408)
                raise MultiPartException("Upload timed out") from error
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    rejection = JSONResponse({"detail": size_error}, 413)
                    # MultiPartException закрывает файлы, уже созданные парсером.
                    raise MultiPartException("Request body too large")
            return message

        async def bounded_send(message):
            nonlocal sent
            if rejection is not None:
                if not sent:
                    sent = True
                    await rejection(scope, receive, send)
                return
            await send(message)

        await self.app(scope, bounded_receive, bounded_send)
