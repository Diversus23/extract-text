"""Приём аудио: отказ до чтения тела, потоковый лимит и перегрузка."""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import anyio.to_thread
import httpx
import pytest

from app.config import settings
from app.main import app
from app.transcription import Transcriber

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
def admission(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_MODE", "none")
    monkeypatch.setattr(settings, "ENABLE_TRANSCRIPTION", True)
    monkeypatch.setattr(settings, "TRANSCRIPTION_MAX_CONCURRENCY", 1)
    monkeypatch.setattr(settings, "TRANSCRIPTION_QUEUE_WAIT_SECONDS", 0.05)
    transcriber = Transcriber()
    monkeypatch.setattr("app.transcription._transcriber", transcriber)
    yield transcriber
    transcriber.close()


async def _unread_body():
    raise AssertionError("Отклонённый запрос не должен читать тело")
    yield b""  # pragma: no cover


async def _post_stream(body, length=None, headers=None):
    request_headers = {"Content-Type": "multipart/form-data; boundary=x"}
    if length is not None:
        request_headers["Content-Length"] = str(length)
    request_headers.update(headers or {})
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        return await client.post(
            "/v1/transcribe", content=body, headers=request_headers
        )


async def test_unauthorized_upload_is_rejected_before_body(admission, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_MODE", "apikey")
    monkeypatch.setattr(settings, "API_KEYS", ["test-key"])

    response = await _post_stream(_unread_body(), length=100)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "ApiKey"


async def test_auth_is_early_when_app_has_root_path(admission, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_MODE", "apikey")
    monkeypatch.setattr(settings, "API_KEYS", ["test-key"])
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, root_path="/service"),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/service/v1/transcribe",
            content=_unread_body(),
            headers={
                "Content-Type": "multipart/form-data; boundary=x",
                "Content-Length": "100",
            },
        )

    assert response.status_code == 401


@pytest.mark.parametrize("length", [None, "invalid", "-1"])
async def test_content_length_is_checked_before_body(admission, length):
    response = await _post_stream(_unread_body(), length=length)

    assert response.status_code == 400
    assert response.json()["status"] == "error"


async def test_large_declared_body_is_rejected_without_reading(admission, monkeypatch):
    monkeypatch.setattr(settings, "MAX_FILE_SIZE", 1024)

    response = await _post_stream(_unread_body(), length=1024 * 1024)

    assert response.status_code == 413


async def test_actual_body_is_bounded_when_content_length_lies(admission, monkeypatch):
    monkeypatch.setattr(settings, "MAX_FILE_SIZE", 1024)
    consumed = 0

    async def body():
        nonlocal consumed
        yield (
            b'--x\r\nContent-Disposition: form-data; name="file"; '
            b'filename="call.wav"\r\n\r\n'
        )
        for _ in range(256):
            consumed += 4096
            yield b"a" * 4096
        yield b"\r\n--x--\r\n"

    response = await _post_stream(body(), length=100)

    assert response.status_code == 413
    assert consumed < 128 * 1024


async def test_busy_uploads_do_not_read_body_or_wait_in_threadpool(admission):
    with admission.slot(0):
        responses = await asyncio.gather(
            *(_post_stream(_unread_body(), length=100) for _ in range(6))
        )

    assert all(response.status_code == 503 for response in responses)
    assert all(response.headers["retry-after"] == "30" for response in responses)


async def test_transcription_uses_its_own_worker_pool(admission, monkeypatch):
    monkeypatch.setattr(settings, "TRANSCRIPTION_TIMEOUT_SECONDS", 0.1)
    limiter = anyio.to_thread.current_default_thread_limiter()
    previous = limiter.total_tokens
    limiter.total_tokens = 1
    result = SimpleNamespace(duration=1.0, channels=1, segments=[])
    try:
        async with limiter:
            with (
                patch("app.main.validate_file_type", return_value=(True, None)),
                patch("app.main.transcribe_bytes", return_value=result),
            ):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url="http://testserver",
                ) as client:
                    response = await client.post(
                        "/v1/transcribe",
                        files={"file": ("call.wav", b"audio", "audio/wav")},
                    )
    finally:
        limiter.total_tokens = previous

    assert response.status_code == 200


async def test_slow_upload_times_out_and_releases_slot(admission, monkeypatch):
    monkeypatch.setattr(settings, "PROCESSING_TIMEOUT_SECONDS", 0.02)

    async def body():
        await asyncio.sleep(1)
        yield b"audio"

    response = await _post_stream(body(), length=100)

    assert response.status_code == 408
    with admission.slot(0):
        pass


async def test_http_timeout_does_not_release_running_worker_slot(
    admission, monkeypatch
):
    import threading

    monkeypatch.setattr(settings, "TRANSCRIPTION_TIMEOUT_SECONDS", 0.02)
    monkeypatch.setattr(settings, "TRANSCRIPTION_MAX_QUEUE_SIZE", 0)
    started = threading.Event()
    finish = threading.Event()

    def worker(*args, **kwargs):
        started.set()
        finish.wait(2)
        return SimpleNamespace(duration=1.0, channels=1, segments=[])

    try:
        with (
            patch("app.main.validate_file_type", return_value=(True, None)),
            patch("app.main.transcribe_bytes", side_effect=worker),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://testserver"
            ) as client:
                response = await client.post(
                    "/v1/transcribe",
                    files={"file": ("call.wav", b"audio", "audio/wav")},
                )
            assert started.is_set()
            assert response.status_code == 504
            busy = await _post_stream(_unread_body(), length=100)
            assert busy.status_code == 503
    finally:
        finish.set()
        await asyncio.to_thread(admission.close)
