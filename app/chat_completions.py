"""Извлечение текста через POST /v1/chat/completions (OpenAI-совместимый вход).

Модуль не импортирует app.main: общая функция извлечения живёт в main.py (её
подменяют тесты прежних маршрутов), а здесь только чистые функции разбора запроса
и сборки ответа. Тело запроса и содержимое file_data в логи не попадают.
"""

import base64
import json
import math
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List

from fastapi import Request

from app.config import settings
from app.openai_compat import (
    EXTRACTION_MODEL_ID,
    OpenAIAPIError,
    is_transcription_model,
)

# Запас на всё, кроме base64 файла: имя файла, роли, текстовые части, служебные
# параметры OpenAI. Новых переменных окружения нет: константа в коде.
CHAT_BODY_OVERHEAD_BYTES = 256 * 1024

CHAT_PATH = "/v1/chat/completions"


class ExtractionError(Exception):
    """Ошибка общей функции извлечения; каждый маршрут показывает её по-своему.

    status - HTTP-код прежнего маршрута /v1/extract/file; message - его текст;
    legacy_detail - если задан, прежний маршрут отвечает HTTPException с этим
    detail; internal - непредвиденное исключение: прежний маршрут отвечает 422,
    новый - 500.
    """

    def __init__(self, status, message, legacy_detail=None, internal=False):
        """Сохраняет все аргументы для копирования исключения."""
        super().__init__(status, message, legacy_detail, internal)
        self.status = status
        self.message = message
        self.legacy_detail = legacy_detail
        self.internal = internal


@dataclass(frozen=True)
class ChatFile:
    """Единственный файл запроса: имя и декодированное содержимое."""

    filename: str
    content: bytes


def chat_body_limit() -> int:
    """Предельный размер тела: base64 файла MAX_FILE_SIZE плюс запас."""
    return math.ceil(settings.MAX_FILE_SIZE / 3) * 4 + CHAT_BODY_OVERHEAD_BYTES


def file_too_large_error() -> OpenAIAPIError:
    """Ошибка 413 с кодом file_too_large и лимитом в тексте."""
    limit = settings.MAX_FILE_SIZE
    return OpenAIAPIError(
        413,
        "Request body or file exceeds the limit. "
        f"File size is limited to {limit} bytes ({limit / (1024 * 1024):g} MiB).",
        code="file_too_large",
    )


async def read_limited_body(request: Request, limit: int) -> bytes:
    """Читает тело потоком и прекращает чтение при превышении лимита.

    Не зависит от Content-Length: заниженный или ложный заголовок не позволяет
    обойти лимит.
    """
    chunks: List[bytes] = []
    received = 0
    async for chunk in request.stream():
        received += len(chunk)
        if received > limit:
            raise file_too_large_error()
        chunks.append(chunk)
    return b"".join(chunks)


def _invalid(message, code="invalid_request", param=None) -> OpenAIAPIError:
    """Ошибка 400 разбора запроса."""
    return OpenAIAPIError(400, message, code=code, param=param)


def validate_chat_model(model: Any) -> None:
    """Проверяет model: обязательна, допустима только модель извлечения."""
    if model is None or model == "":
        raise _invalid(
            "Required parameter: model", "missing_required_parameter", "model"
        )
    if not isinstance(model, str):
        raise _invalid("model must be a string", param="model")
    if model == EXTRACTION_MODEL_ID:
        return
    message = (
        "Not an extraction model"
        if is_transcription_model(model)
        else "Unknown extraction model"
    )
    raise OpenAIAPIError(404, message, code="model_not_found", param="model")


def _collect_file_parts(messages: Any) -> List[Dict[str, Any]]:
    """Собирает file-части всех сообщений, проверяя допустимость типов частей."""
    if messages is None:
        raise _invalid(
            "Required parameter: messages", "missing_required_parameter", "messages"
        )
    if not isinstance(messages, list) or not messages:
        raise _invalid("messages must be a non-empty array", param="messages")
    parts: List[Dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            raise _invalid("Each message must be an object", param="messages")
        content = message.get("content")
        if isinstance(content, str):
            continue
        if not isinstance(content, list):
            raise _invalid(
                "message content must be a string or an array of parts",
                param="messages",
            )
        for part in content:
            if not isinstance(part, dict):
                raise _invalid("Each content part must be an object", param="messages")
            kind = part.get("type")
            if kind == "text":
                continue
            if kind != "file":
                raise _invalid(
                    "Unsupported content part type: only text and file are accepted",
                    "unsupported_content_type",
                    "messages",
                )
            parts.append(part)
    return parts


def _decode_file_data(file_data: Any) -> bytes:
    """Декодирует data:<mime>;base64,<данные>; MIME игнорируется."""
    if not isinstance(file_data, str) or not file_data:
        raise _invalid(
            "Required parameter: file.file_data",
            "missing_required_parameter",
            "messages",
        )
    head, separator, encoded = file_data.partition(",")
    if (
        not file_data.startswith("data:")
        or not separator
        or not head.endswith(";base64")
    ):
        raise _invalid(
            "file_data must be a data URL: data:<mime>;base64,<data>",
            "invalid_file_data",
            "messages",
        )
    # Переносы строк внутри base64 допускаются; остальное проверяет декодер.
    # Размер оценивается до декодирования, чтобы не выделять память под лишнее.
    if "\n" in encoded or "\r" in encoded:
        encoded = encoded.replace("\r", "").replace("\n", "")
    padding = 2 if encoded.endswith("==") else int(encoded.endswith("="))
    if len(encoded) * 3 // 4 - padding > settings.MAX_FILE_SIZE:
        raise file_too_large_error()
    try:
        content = base64.b64decode(encoded, validate=True)
    except ValueError as error:  # binascii.Error - подкласс ValueError
        raise _invalid(
            "file_data is not valid base64", "invalid_file_data", "messages"
        ) from error
    if len(content) > settings.MAX_FILE_SIZE:
        raise file_too_large_error()
    return content


def parse_chat_request(payload: Any) -> ChatFile:
    """Разбирает тело запроса и возвращает единственный файл.

    Порядок проверок: model, stream, части сообщений, размер файла. Прочие
    параметры OpenAI принимаются и игнорируются.
    """
    if not isinstance(payload, dict):
        raise _invalid("Request body must be a JSON object")
    validate_chat_model(payload.get("model"))
    stream = payload.get("stream")
    if stream is True:
        raise OpenAIAPIError(
            400,
            "Streaming is not supported",
            code="unsupported_parameter",
            param="stream",
        )
    if stream is not None and stream is not False:
        raise _invalid("stream must be a boolean", param="stream")

    parts = _collect_file_parts(payload.get("messages"))
    if not parts:
        raise _invalid(
            "Required content part: file", "missing_required_parameter", "messages"
        )
    if len(parts) > 1:
        raise _invalid(
            "Exactly one file part is accepted", "too_many_files", "messages"
        )

    file_info = parts[0].get("file")
    if not isinstance(file_info, dict):
        raise _invalid("Required parameter: file", "missing_required_parameter", "file")
    if file_info.get("file_id") is not None:
        raise _invalid(
            "file_id is not supported: pass file_data",
            "unsupported_parameter",
            "messages",
        )
    filename = file_info.get("filename")
    if filename is None or filename == "":
        raise _invalid(
            "Required parameter: file.filename",
            "missing_required_parameter",
            "messages",
        )
    if not isinstance(filename, str) or not filename.strip():
        raise _invalid("file.filename must be a non-empty string", param="messages")
    return ChatFile(
        filename=filename, content=_decode_file_data(file_info.get("file_data"))
    )


def format_extraction_content(files: List[Dict[str, Any]]) -> str:
    """Собирает content из files[] результата извлечения.

    Блок на каждый файл, включая единственный: «--- FILE: имя ---», перевод
    строки, текст; блоки соединяются переводом строки. Элемент без text
    пропускается, текст не обрезается.
    """
    blocks = []
    for item in files:
        text = item.get("text")
        if text is None:
            continue
        name = str(item.get("filename", "")).strip()
        blocks.append(f"--- FILE: {name} ---\n{text}")
    return "\n".join(blocks)


def build_chat_response(content: str) -> Dict[str, Any]:
    """Не потоковый ответ chat.completion с нулевым usage."""
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": EXTRACTION_MODEL_ID,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def parse_json_body(body: bytes) -> Any:
    """Разбирает JSON тела; ошибка разбора - 400 без цитирования содержимого."""
    try:
        return json.loads(body.decode("utf-8"))
    except (ValueError, RecursionError) as error:
        raise _invalid("Request body is not valid JSON") from error
