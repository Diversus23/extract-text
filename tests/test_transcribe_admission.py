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


async def _post_stream(body, length=None, headers=None, path="/v1/transcribe"):
    request_headers = {"Content-Type": "multipart/form-data; boundary=x"}
    if length is not None:
        request_headers["Content-Length"] = str(length)
    request_headers.update(headers or {})
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        return await client.post(path, content=body, headers=request_headers)


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
    monkeypatch.setattr(settings, "MAX_AUDIO_FILE_SIZE", 1024)

    response = await _post_stream(_unread_body(), length=1024 * 1024)

    assert response.status_code == 413


@pytest.mark.parametrize("path", ["/v1/transcribe", "/v1/audio/transcriptions"])
async def test_actual_body_is_bounded_when_content_length_lies(
    admission, monkeypatch, path
):
    monkeypatch.setattr(settings, "MAX_AUDIO_FILE_SIZE", 1024)
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

    response = await _post_stream(body(), length=100, path=path)

    assert response.status_code == 413
    if path == "/v1/audio/transcriptions":
        assert response.json()["error"]["code"] == "audio_too_large"
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
    result = SimpleNamespace(
        duration=1.0, channels=1, segments=[], detected_format="wav"
    )
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


@pytest.mark.parametrize("path", ["/v1/transcribe", "/v1/audio/transcriptions"])
async def test_slow_upload_times_out_and_releases_slot(admission, monkeypatch, path):
    monkeypatch.setattr(settings, "PROCESSING_TIMEOUT_SECONDS", 0.02)

    async def body():
        await asyncio.sleep(1)
        yield b"audio"

    response = await _post_stream(body(), length=100, path=path)

    assert response.status_code == 408
    if path == "/v1/audio/transcriptions":
        assert response.json()["error"]["code"] == "request_timeout"
    with admission.slot(0):
        pass


@pytest.mark.parametrize("path", ["/v1/transcribe", "/v1/audio/transcriptions"])
async def test_http_timeout_does_not_release_running_worker_slot(
    admission, monkeypatch, path
):
    import threading

    monkeypatch.setattr(settings, "TRANSCRIPTION_TIMEOUT_SECONDS", 0.02)
    monkeypatch.setattr(settings, "TRANSCRIPTION_MAX_QUEUE_SIZE", 0)
    started = threading.Event()
    finish = threading.Event()

    def worker(*args, **kwargs):
        started.set()
        finish.wait(2)
        return SimpleNamespace(
            duration=1.0, channels=1, segments=[], detected_format="wav"
        )

    try:
        with (
            patch("app.main.validate_file_type", return_value=(True, None)),
            patch("app.main.transcribe_bytes", side_effect=worker),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://testserver"
            ) as client:
                response = await client.post(
                    path,
                    data={"model": settings.TRANSCRIPTION_MODEL},
                    files={"file": ("call.wav", b"audio", "audio/wav")},
                )
            assert started.is_set()
            assert response.status_code == 504
            if path == "/v1/audio/transcriptions":
                assert response.json()["error"]["code"] == "request_timeout"
            busy = await _post_stream(_unread_body(), length=100, path=path)
            assert busy.status_code == 503
    finally:
        finish.set()
        await asyncio.to_thread(admission.close)


@pytest.mark.parametrize(
    "length,status", [(None, 400), ("invalid", 400), (1000000000, 413)]
)
async def test_openai_admission_before_body(admission, length, status):
    headers = {"Content-Type": "multipart/form-data; boundary=x"}
    if length is not None:
        headers["Content-Length"] = str(length)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/audio/transcriptions", content=_unread_body(), headers=headers
        )
    assert response.status_code == status
    assert "error" in response.json()


async def test_openai_busy_before_body(admission, monkeypatch):
    monkeypatch.setattr(settings, "TRANSCRIPTION_MAX_QUEUE_SIZE", 0)
    slot = await admission.reserve()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/v1/audio/transcriptions",
                content=_unread_body(),
                headers={"Content-Length": "100"},
            )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "service_busy"
        assert "retry-after" in response.headers
    finally:
        slot.release()


async def test_openai_cancellation_keeps_slot_until_worker_finishes(
    admission, monkeypatch
):
    import threading

    monkeypatch.setattr(settings, "TRANSCRIPTION_TIMEOUT_SECONDS", 5)
    monkeypatch.setattr(settings, "TRANSCRIPTION_MAX_QUEUE_SIZE", 0)
    started = threading.Event()
    finish = threading.Event()
    captured = {}

    def worker(*args, cancel_event, **kwargs):
        captured["cancel_event"] = cancel_event
        started.set()
        finish.wait(5)
        return SimpleNamespace(
            duration=1.0, channels=1, segments=[], detected_format="wav"
        )

    task = None
    try:
        with patch("app.main.transcribe_bytes", side_effect=worker):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                task = asyncio.create_task(
                    client.post(
                        "/v1/audio/transcriptions",
                        files={"file": ("call.wav", b"audio", "audio/wav")},
                        data={"model": settings.TRANSCRIPTION_MODEL},
                    )
                )
                assert await asyncio.to_thread(started.wait, 2)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                assert captured["cancel_event"].is_set()
                response = await _post_stream(
                    _unread_body(), length=100, path="/v1/audio/transcriptions"
                )
                assert response.status_code == 503
                assert response.json()["error"]["code"] == "service_busy"
                finish.set()
                # Executor completion, not HTTP cancellation, releases this slot.
                await asyncio.to_thread(admission.close)
                with admission.slot(0):
                    pass
    finally:
        finish.set()
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await asyncio.to_thread(admission.close)
