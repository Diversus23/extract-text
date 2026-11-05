"""Защита приёма POST /v1/chat/completions до чтения тела запроса."""

from fastapi import HTTPException
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from app.auth import check_api_key, extract_api_key
from app.chat_completions import CHAT_PATH, chat_body_limit, file_too_large_error
from app.openai_compat import openai_error_response


class ChatBodyGuardMiddleware:
    """Проверяет доступ и Content-Length до чтения тела.

    Порядок: доступ, единственный корректный Content-Length, сравнение с
    chat_body_limit(). Тело в этом слое не читается; точный подсчёт при чтении
    (ложный Content-Length) выполняет обработчик маршрута. Остальные пути и методы
    передаются приложению без изменений.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Сохраняет следующее приложение в цепочке middleware."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Отклоняет недопустимый запрос чата, не вызывая receive."""
        path = scope.get("path", "")
        root_path = scope.get("root_path", "")
        if root_path and path.startswith(root_path + "/"):
            path = path[len(root_path) :]
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or path.rstrip("/") != CHAT_PATH
        ):
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        try:
            check_api_key(
                extract_api_key(headers.get("x-api-key"), headers.get("authorization"))
            )
        except HTTPException as error:
            await openai_error_response(
                error.status_code,
                error.detail,
                {"WWW-Authenticate": "Bearer"} if error.status_code == 401 else None,
            )(scope, receive, send)
            return

        lengths = headers.getlist("content-length")
        if (
            len(lengths) != 1
            or not lengths[0].isascii()
            or not lengths[0].isdigit()
            or len(lengths[0]) > 20
        ):
            await openai_error_response(
                400, "A valid Content-Length header is required."
            )(scope, receive, send)
            return

        if int(lengths[0]) > chat_body_limit():
            too_large = file_too_large_error()
            await openai_error_response(
                too_large.status, too_large.message, code=too_large.code
            )(scope, receive, send)
            return

        await self.app(scope, receive, send)
