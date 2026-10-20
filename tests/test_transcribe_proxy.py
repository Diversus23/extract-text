"""Проксирование /v1/transcribe с основного сервиса в сервис api-audio."""

import asyncio

import httpx
import pytest

from app.config import settings
from app.main import app
from app.transcription import Transcriber
from app.transcription_ingress import TranscriptionIngressMiddleware

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

UPSTREAM = "http://audio.internal:7556"
MULTIPART = "multipart/form-data; boundary=x"


@pytest.fixture
def proxy_mode(monkeypatch):
    """Основной сервис: расшифровка выключена, задан адрес api-audio."""
    monkeypatch.setattr(settings, "AUTH_MODE", "none")
    monkeypatch.setattr(settings, "ENABLE_TRANSCRIPTION", False)
    monkeypatch.setattr(settings, "TRANSCRIPTION_UPSTREAM_URL", UPSTREAM)


def use_upstream(monkeypatch, handler):
    """Подменяет сеть: запросы к api-audio обрабатывает handler."""
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "app.transcription_proxy._make_client",
        lambda timeout: httpx.AsyncClient(transport=transport, timeout=timeout),
    )


def forbid_upstream(monkeypatch):
    """Любое обращение к api-audio считается ошибкой теста."""

    def handler(request):
        raise AssertionError(f"Запрос не должен уходить в api-audio: {request.url}")

    use_upstream(monkeypatch, handler)


def gateway():
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    )


async def _post_stream(body, length=None, headers=None):
    request_headers = {"Content-Type": MULTIPART}
    if length is not None:
        request_headers["Content-Length"] = str(length)
    request_headers.update(headers or {})
    async with gateway() as client:
        return await client.post(
            "/v1/transcribe", content=body, headers=request_headers
        )


async def test_request_is_forwarded_and_upstream_response_returned(
    proxy_mode, monkeypatch
):
    seen = {}

    async def handler(request):
        seen["method"] = request.method
        seen["url"] = str(request.url)
        seen["content_type"] = request.headers["content-type"]
        seen["content_length"] = request.headers["content-length"]
        seen["body"] = await request.aread()
        return httpx.Response(
            200, json={"status": "success", "text": "привет"}, headers={"X-Extra": "1"}
        )

    use_upstream(monkeypatch, handler)

    async with gateway() as client:
        response = await client.post(
            "/v1/transcribe",
            files={"file": ("call.wav", b"audio-bytes", "audio/wav")},
            data={"external_id": "42"},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "success", "text": "привет"}
    assert response.headers["x-extra"] == "1"
    assert seen["method"] == "POST"
    assert seen["url"] == f"{UPSTREAM}/v1/transcribe"
    assert seen["content_type"].startswith("multipart/form-data; boundary=")
    assert seen["content_length"] == str(len(seen["body"]))
    assert b"audio-bytes" in seen["body"]
    assert b'name="external_id"' in seen["body"]


async def test_upstream_error_and_retry_after_are_passed_through(
    proxy_mode, monkeypatch
):
    use_upstream(
        monkeypatch,
        lambda request: httpx.Response(
            503,
            json={"status": "error", "filename": "unknown_file", "message": "занято"},
            headers={"Retry-After": "30"},
        ),
    )

    response = await _post_stream(b"audio", length=5)

    assert response.status_code == 503
    assert response.headers["retry-after"] == "30"
    assert response.json()["message"] == "занято"


async def test_api_key_is_forwarded_to_upstream(proxy_mode, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_MODE", "apikey")
    monkeypatch.setattr(settings, "API_KEYS", ["test-key"])
    seen = {}

    async def handler(request):
        seen["key"] = request.headers.get("x-api-key")
        await request.aread()
        return httpx.Response(200, json={"status": "success"})

    use_upstream(monkeypatch, handler)

    response = await _post_stream(b"audio", length=5, headers={"X-API-Key": "test-key"})

    assert response.status_code == 200
    assert seen["key"] == "test-key"


async def test_unauthorized_request_is_not_forwarded(proxy_mode, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_MODE", "apikey")
    monkeypatch.setattr(settings, "API_KEYS", ["test-key"])
    forbid_upstream(monkeypatch)

    response = await _post_stream(b"audio", length=5)

    assert response.status_code == 401


async def test_origin_is_not_forwarded_so_cors_headers_are_set_once(
    proxy_mode, monkeypatch
):
    seen = {}

    async def handler(request):
        seen["origin"] = request.headers.get("origin")
        await request.aread()
        return httpx.Response(200, json={"status": "success"})

    use_upstream(monkeypatch, handler)

    response = await _post_stream(
        b"audio", length=5, headers={"Origin": "https://client.example"}
    )

    assert response.status_code == 200
    assert seen["origin"] is None
    assert response.headers.get_list("access-control-allow-origin") == ["*"]


@pytest.mark.parametrize("length", [None, "invalid"])
async def test_missing_content_length_is_rejected_without_forwarding(
    proxy_mode, monkeypatch, length
):
    forbid_upstream(monkeypatch)

    async def body():
        yield b"audio"

    # Генератор без явной длины уходит chunked: заголовка Content-Length нет
    response = await _post_stream(body(), length=length)

    assert response.status_code == 400
    assert response.json()["status"] == "error"


async def test_large_declared_body_is_rejected_without_forwarding(
    proxy_mode, monkeypatch
):
    monkeypatch.setattr(settings, "MAX_AUDIO_FILE_SIZE", 1024)
    forbid_upstream(monkeypatch)

    response = await _post_stream(b"audio", length=1024 * 1024)

    assert response.status_code == 413


async def test_actual_body_is_bounded_when_content_length_lies(proxy_mode, monkeypatch):
    monkeypatch.setattr(settings, "MAX_AUDIO_FILE_SIZE", 1024)
    consumed = 0

    async def handler(request):
        await request.aread()
        return httpx.Response(200, json={"status": "success"})

    use_upstream(monkeypatch, handler)

    async def body():
        nonlocal consumed
        for _ in range(256):
            consumed += 4096
            yield b"a" * 4096

    response = await _post_stream(body(), length=100)

    assert response.status_code == 413
    assert consumed < 128 * 1024


async def test_slow_upload_times_out_with_408(proxy_mode, monkeypatch):
    monkeypatch.setattr(settings, "PROCESSING_TIMEOUT_SECONDS", 0.02)

    async def handler(request):
        await request.aread()
        return httpx.Response(200, json={"status": "success"})

    use_upstream(monkeypatch, handler)

    async def body():
        await asyncio.sleep(1)
        yield b"audio"

    response = await _post_stream(body(), length=100)

    assert response.status_code == 408


async def test_unreachable_upstream_returns_503_with_retry_after(
    proxy_mode, monkeypatch
):
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    use_upstream(monkeypatch, handler)

    response = await _post_stream(b"audio", length=5)

    assert response.status_code == 503
    assert response.headers["retry-after"] == "30"
    body = response.json()
    assert body["status"] == "error"
    assert body["filename"] == "unknown_file"


async def test_upstream_read_timeout_returns_504(proxy_mode, monkeypatch):
    async def handler(request):
        await request.aread()
        raise httpx.ReadTimeout("slow", request=request)

    use_upstream(monkeypatch, handler)

    response = await _post_stream(b"audio", length=5)

    assert response.status_code == 504
    assert response.json()["status"] == "error"


async def test_broken_upstream_returns_502(proxy_mode, monkeypatch):
    async def handler(request):
        await request.aread()
        raise httpx.RemoteProtocolError("garbage", request=request)

    use_upstream(monkeypatch, handler)

    response = await _post_stream(b"audio", length=5)

    assert response.status_code == 502
    assert response.json()["status"] == "error"


def call_middleware(messages, disconnect):
    """Вызывает middleware напрямую: клиент шлёт messages, затем ждёт disconnect."""
    pending = list(messages)
    sent = []

    async def receive():
        if pending:
            return pending.pop(0)
        await disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    async def never_called(scope, receive, send):
        raise AssertionError("Приложение не должно вызываться в режиме прокси")

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/v1/transcribe",
        "root_path": "",
        "query_string": b"",
        "headers": [
            (b"content-type", MULTIPART.encode()),
            (b"content-length", b"10"),
        ],
    }
    task = asyncio.create_task(
        TranscriptionIngressMiddleware(never_called)(scope, receive, send)
    )
    return task, sent


async def test_client_disconnect_cancels_upstream_request(proxy_mode, monkeypatch):
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def handler(request):
        await request.aread()
        started.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    use_upstream(monkeypatch, handler)
    disconnect = asyncio.Event()
    task, sent = call_middleware(
        [{"type": "http.request", "body": b"0123456789", "more_body": False}],
        disconnect,
    )

    await asyncio.wait_for(started.wait(), 2)
    disconnect.set()
    await asyncio.wait_for(task, 2)

    assert cancelled.is_set()
    # BaseHTTPMiddleware падает с "No response returned", если ответа не было вовсе;
    # uvicorn отбрасывает ответ закрытому соединению.
    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 499


async def test_client_disconnect_during_upload_gets_a_response(proxy_mode, monkeypatch):
    async def handler(request):
        await request.aread()
        return httpx.Response(200, json={"status": "success"})

    use_upstream(monkeypatch, handler)
    disconnect = asyncio.Event()
    task, sent = call_middleware(
        [{"type": "http.request", "body": b"01234", "more_body": True}], disconnect
    )

    await asyncio.sleep(0.05)
    disconnect.set()
    await asyncio.wait_for(task, 2)

    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 499


async def test_local_mode_does_not_forward_even_with_upstream_url(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_MODE", "none")
    monkeypatch.setattr(settings, "ENABLE_TRANSCRIPTION", True)
    monkeypatch.setattr(settings, "TRANSCRIPTION_UPSTREAM_URL", UPSTREAM)
    monkeypatch.setattr(settings, "TRANSCRIPTION_QUEUE_WAIT_SECONDS", 0.05)
    transcriber = Transcriber()
    monkeypatch.setattr("app.transcription._transcriber", transcriber)
    forbid_upstream(monkeypatch)

    try:
        with transcriber.slot(0):
            response = await _post_stream(b"audio", length=5)
    finally:
        transcriber.close()

    assert response.status_code == 503
    assert response.headers["retry-after"] == "30"


async def test_disabled_without_upstream_url_returns_503(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_MODE", "none")
    monkeypatch.setattr(settings, "ENABLE_TRANSCRIPTION", False)
    monkeypatch.setattr(settings, "TRANSCRIPTION_UPSTREAM_URL", "")
    forbid_upstream(monkeypatch)

    response = await _post_stream(b"audio", length=5)

    assert response.status_code == 503
    assert response.json()["message"] == "Расшифровка аудио отключена на этом сервере."


async def test_readiness_probe_is_taken_from_upstream(proxy_mode, monkeypatch):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"status": "ok", "transcription": "ready"})

    use_upstream(monkeypatch, handler)

    async with gateway() as client:
        response = await client.get("/health?check=transcription")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "transcription": "ready"}
    assert seen["url"] == f"{UPSTREAM}/health?check=transcription"


async def test_readiness_probe_passes_upstream_unavailable(proxy_mode, monkeypatch):
    use_upstream(
        monkeypatch,
        lambda request: httpx.Response(
            503, json={"status": "unavailable", "transcription": "not_loaded"}
        ),
    )

    async with gateway() as client:
        response = await client.get("/health?check=transcription")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "transcription": "not_loaded"}


async def test_readiness_probe_reports_unreachable_upstream(proxy_mode, monkeypatch):
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    use_upstream(monkeypatch, handler)

    async with gateway() as client:
        response = await client.get("/health?check=transcription")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "transcription": "unreachable"}


async def test_plain_health_does_not_call_upstream(proxy_mode, monkeypatch):
    forbid_upstream(monkeypatch)

    async with gateway() as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
