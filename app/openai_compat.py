"""OpenAI-compatible response and authentication contracts."""

import time
from typing import Optional

from fastapi import HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials
from starlette.responses import JSONResponse, PlainTextResponse

from app.auth import api_key_scheme, bearer_scheme, check_api_key, extract_api_key
from app.config import settings
from app.transcription import build_response

API_KEY_SECURITY = Security(api_key_scheme)
BEARER_SECURITY = Security(bearer_scheme)

STARTED_AT = int(time.time())
OPENAI_PATHS = {"/v1/models", "/v1/audio/transcriptions", "/v1/chat/completions"}

# Публичные идентификаторы моделей сервиса. Префикс принадлежит каталогу, а не
# конфигурации: TRANSCRIPTION_MODEL остаётся именем каталога весов (model_dir).
# Идентификатор модели извлечения обязан содержать «extract»: по этой подстроке
# клиент (1С) относит модель к извлечению текста, а не к чату.
PUBLIC_MODEL_PREFIX = "softonit/"
EXTRACTION_MODEL_ID = PUBLIC_MODEL_PREFIX + "extracttext"


def is_openai_path(path, root_path=""):
    """Identify compatibility routes without matching unrelated endpoints."""
    if root_path and path.startswith(root_path + "/"):
        path = path[len(root_path) :]
    return path.rstrip("/") in OPENAI_PATHS


class OpenAIAPIError(Exception):
    """An error belonging exclusively to the compatibility API."""

    def __init__(self, status, message, code=None, param=None, headers=None):
        """Keep all exception arguments available for copying."""
        super().__init__(status, message, code, param, headers)
        self.status = status
        self.message = message
        self.code = code
        self.param = param
        self.headers = headers


def openai_error_response(status, message, headers=None, *, code=None, param=None):
    """Build an error envelope with stable machine-readable codes."""
    default_codes = {
        400: "invalid_request",
        401: "invalid_api_key",
        405: "method_not_allowed",
        408: "request_timeout",
        413: "audio_too_large",
        415: "unsupported_audio_format",
        422: "invalid_audio",
        429: "service_busy",
        503: "service_busy",
        504: "request_timeout",
    }
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "message": str(message),
                "type": (
                    "server_error"
                    if status >= 500 or status == 429
                    else "invalid_request_error"
                ),
                "param": param,
                "code": code or default_codes.get(status, "internal_error"),
            }
        },
        headers=headers,
    )


async def openai_error_handler(request, error):
    """Render compatibility errors without affecting legacy routes."""
    return openai_error_response(
        error.status, error.message, error.headers, code=error.code, param=error.param
    )


async def openai_credentials(
    request: Request,
    x_api_key: Optional[str] = API_KEY_SECURITY,
    bearer: Optional[HTTPAuthorizationCredentials] = BEARER_SECURITY,
):
    """Validate both authentication schemes for compatibility routes."""
    try:
        check_api_key(extract_api_key(x_api_key, request.headers.get("authorization")))
    except HTTPException as error:
        raise OpenAIAPIError(
            error.status_code,
            error.detail,
            headers=(
                {"WWW-Authenticate": "Bearer"} if error.status_code == 401 else None
            ),
        ) from error


def transcription_model_id():
    """Public identifier of the speech model: prefix + weights directory name."""
    name = settings.TRANSCRIPTION_MODEL
    if name.startswith(PUBLIC_MODEL_PREFIX):
        return name
    return PUBLIC_MODEL_PREFIX + name


def is_transcription_model(model):
    """Accept the public identifier and the legacy unprefixed one."""
    return model in (transcription_model_id(), settings.TRANSCRIPTION_MODEL)


def validate_model(model):
    """Reject missing or unknown transcription model identifiers."""
    if not model:
        raise OpenAIAPIError(
            400,
            "Required parameter: model",
            code="missing_required_parameter",
            param="model",
        )
    if is_transcription_model(model):
        return
    message = (
        "Not a transcription model"
        if model == EXTRACTION_MODEL_ID
        else "Unknown transcription model"
    )
    raise OpenAIAPIError(404, message, code="model_not_found", param="model")


def validate_extraction_model(model):
    """Allow an omitted model or the extraction model; reject anything else."""
    if model and model != EXTRACTION_MODEL_ID:
        raise OpenAIAPIError(
            404, "Unknown extraction model", code="model_not_found", param="model"
        )


def validate_response_format(response_format):
    """Reject formats the local recognizer cannot produce."""
    if response_format not in {"json", "verbose_json", "text"}:
        raise OpenAIAPIError(
            400,
            "Unsupported response_format",
            code="unsupported_response_format",
            param="response_format",
        )


def models_payload():
    """Advertise the public models without loading any weights."""
    available = settings.ENABLE_TRANSCRIPTION or settings.TRANSCRIPTION_UPSTREAM_URL
    data = [
        {
            "id": EXTRACTION_MODEL_ID,
            "object": "model",
            "created": STARTED_AT,
            "owned_by": "extract-text",
            "name": "softonit.ru: извлечение текста",
            "description": "Извлечение текста из документов, изображений и "
            "архивов (POST /v1/chat/completions, часть type=file)",
            "architecture": {
                "input_modalities": ["file"],
                "output_modalities": ["text"],
            },
        }
    ]
    if available:
        data.append(
            {
                "id": transcription_model_id(),
                "object": "model",
                "created": STARTED_AT,
                "owned_by": "extract-text",
                "name": "softonit.ru: транскрибация речи",
                "description": "Распознавание русской речи GigaAM v3 "
                "(POST /v1/audio/transcriptions)",
                "architecture": {
                    "input_modalities": ["audio"],
                    "output_modalities": ["text"],
                },
            }
        )
    return {"object": "list", "data": data}


def transcription_payload(result, response_format, filename, external_id):
    """Convert the shared result to the requested response format."""
    body = build_response(
        filename=filename,
        external_id=external_id,
        duration=result.duration,
        channels=result.channels,
        detected_format=result.detected_format,
        segments=result.segments,
    )
    if response_format == "text":
        return PlainTextResponse(body["text"])
    usage = {"type": "duration", "seconds": body["duration"]}
    if response_format == "json":
        return {
            "text": body["text"],
            "usage": usage,
            "text_status": body["text_status"],
        }
    body.pop("status")
    body.pop("filename")
    body["model"] = transcription_model_id()
    body["task"] = "transcribe"
    body["usage"] = usage
    body["segments"] = [
        {"id": index, **segment} for index, segment in enumerate(body["segments"])
    ]
    return body
