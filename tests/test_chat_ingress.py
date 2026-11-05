"""Предохранитель POST /v1/chat/completions: доступ и размер до чтения тела."""

import json

import pytest

from app.chat_completions import CHAT_BODY_OVERHEAD_BYTES, chat_body_limit
from app.chat_ingress import ChatBodyGuardMiddleware
from app.config import settings
from app.main import app
from app.openai_compat import EXTRACTION_MODEL_ID

PATH = "/v1/chat/completions"
JSON_HEADERS = [("content-type", "application/json")]

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class Recorder:
    """Фиксирует вызовы receive и ответ приложения."""

    def __init__(self, chunks=()):
        self.chunks = list(chunks)
        self.receive_calls = 0
        self.consumed = 0
        self.messages = []

    async def receive(self):
        self.receive_calls += 1
        if not self.chunks:
            return {"type": "http.disconnect"}
        chunk = self.chunks.pop(0)
        self.consumed += len(chunk)
        return {
            "type": "http.request",
            "body": chunk,
            "more_body": bool(self.chunks),
        }

    async def send(self, message):
        self.messages.append(message)

    @property
    def status(self):
        return self.messages[0]["status"]

    @property
    def headers(self):
        return {
            key.decode().lower(): value.decode()
            for key, value in self.messages[0]["headers"]
        }

    @property
    def body(self):
        return b"".join(m.get("body", b"") for m in self.messages[1:])

    @property
    def error(self):
        return json.loads(self.body)["error"]


def make_scope(headers, method="POST", path=PATH, root_path="", scope_type="http"):
    return {
        "type": scope_type,
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": root_path + path,
        "raw_path": (root_path + path).encode(),
        "root_path": root_path,
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }


class StubApp:
    """Следующее приложение: считает вызовы и отвечает 204."""

    def __init__(self):
        self.calls = 0

    async def __call__(self, scope, receive, send):
        self.calls += 1
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})


@pytest.fixture(autouse=True)
def open_api(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_MODE", "none")


@pytest.fixture
def protected(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_MODE", "apikey")
    monkeypatch.setattr(settings, "API_KEYS", ["secret"])


async def guard(headers, chunks=(b"{}",), **scope_args):
    stub = StubApp()
    recorder = Recorder(chunks)
    middleware = ChatBodyGuardMiddleware(stub)
    await middleware(make_scope(headers, **scope_args), recorder.receive, recorder.send)
    return stub, recorder


# --- доступ ------------------------------------------------------------------


async def test_unauthorized_request_is_rejected_before_body(protected):
    stub, rec = await guard(JSON_HEADERS + [("content-length", "2")])

    assert rec.status == 401
    assert rec.error["code"] == "invalid_api_key"
    assert rec.error["type"] == "invalid_request_error"
    assert rec.headers["www-authenticate"] == "Bearer"
    assert rec.receive_calls == 0
    assert stub.calls == 0


async def test_wrong_key_is_rejected_before_body(protected):
    stub, rec = await guard(
        JSON_HEADERS + [("content-length", "2"), ("x-api-key", "wrong")]
    )
    assert rec.status == 401
    assert rec.receive_calls == 0
    assert stub.calls == 0


async def test_auth_goes_before_content_length_checks(protected):
    stub, rec = await guard([])
    assert rec.status == 401
    assert rec.receive_calls == 0


@pytest.mark.parametrize(
    "credentials",
    [
        [("authorization", "Bearer secret")],
        [("x-api-key", "secret")],
        [("x-api-key", "secret"), ("authorization", "Bearer wrong")],
    ],
)
async def test_valid_credentials_pass(protected, credentials):
    stub, rec = await guard(
        JSON_HEADERS + [("content-length", "2")] + credentials,
    )
    assert rec.status == 204
    assert stub.calls == 1


async def test_x_api_key_has_priority_over_bearer(protected):
    stub, rec = await guard(
        [
            ("content-length", "2"),
            ("x-api-key", "wrong"),
            ("authorization", "Bearer secret"),
        ]
    )
    assert rec.status == 401
    assert stub.calls == 0


async def test_misconfigured_auth_mode_is_reported(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_MODE", "broken")
    stub, rec = await guard([("content-length", "2")])
    assert rec.status == 500
    assert rec.error["type"] == "server_error"
    assert stub.calls == 0


# --- Content-Length ----------------------------------------------------------


@pytest.mark.parametrize(
    "lengths",
    [
        [],
        ["abc"],
        ["-1"],
        ["1.5"],
        [" "],
        [""],
        ["١٢٣"],
        ["2", "2"],
        ["1" * 21],
    ],
)
async def test_content_length_must_be_single_and_numeric(lengths):
    headers = JSON_HEADERS + [("content-length", value) for value in lengths]
    stub, rec = await guard(headers)

    assert rec.status == 400
    assert rec.error["code"] == "invalid_request"
    assert rec.receive_calls == 0
    assert stub.calls == 0


async def test_declared_body_above_limit_is_rejected_without_reading():
    declared = chat_body_limit() + 1
    stub, rec = await guard(JSON_HEADERS + [("content-length", str(declared))])

    assert rec.status == 413
    assert rec.error["code"] == "file_too_large"
    assert str(settings.MAX_FILE_SIZE) in rec.error["message"]
    assert rec.receive_calls == 0
    assert stub.calls == 0


async def test_declared_body_equal_to_limit_passes():
    stub, rec = await guard(JSON_HEADERS + [("content-length", str(chat_body_limit()))])
    assert rec.status == 204
    assert stub.calls == 1


async def test_limit_follows_max_file_size(monkeypatch):
    monkeypatch.setattr(settings, "MAX_FILE_SIZE", 3)
    limit = 4 + CHAT_BODY_OVERHEAD_BYTES
    _, over = await guard(JSON_HEADERS + [("content-length", str(limit + 1))])
    _, equal = await guard(JSON_HEADERS + [("content-length", str(limit))])
    assert over.status == 413
    assert equal.status == 204


async def test_huge_declared_length_is_rejected():
    _, rec = await guard(JSON_HEADERS + [("content-length", "9" * 20)])
    assert rec.status == 413


# --- чужие запросы -----------------------------------------------------------


@pytest.mark.parametrize(
    "scope_args",
    [
        {"method": "GET"},
        {"method": "OPTIONS"},
        {"method": "PUT"},
        {"path": "/v1/models"},
        {"path": "/v1/extract/file"},
        {"path": "/v1/chat/completions/extra"},
    ],
)
async def test_other_requests_pass_through_untouched(protected, scope_args):
    stub, rec = await guard([], **scope_args)
    assert rec.status == 204
    assert stub.calls == 1
    assert rec.receive_calls == 0


async def test_non_http_scopes_pass_through(protected):
    stub = StubApp()
    middleware = ChatBodyGuardMiddleware(stub)
    recorder = Recorder()
    await middleware(
        make_scope([], scope_type="websocket"), recorder.receive, recorder.send
    )
    assert stub.calls == 1


async def test_trailing_slash_is_guarded(protected):
    stub, rec = await guard([], path=PATH + "/")
    assert rec.status == 401
    assert stub.calls == 0


async def test_root_path_is_respected(protected):
    stub, rec = await guard([], root_path="/service")
    assert rec.status == 401
    assert stub.calls == 0


# --- через всё приложение ----------------------------------------------------


async def call_app(headers, chunks, method="POST", path=PATH):
    recorder = Recorder(chunks)
    await app(make_scope(headers, method, path), recorder.receive, recorder.send)
    return recorder


async def test_app_rejects_unauthorized_without_reading_body(protected):
    rec = await call_app(JSON_HEADERS + [("content-length", "100")], [b"x" * 100])
    assert rec.status == 401
    assert rec.error["code"] == "invalid_api_key"
    assert rec.receive_calls == 0


async def test_app_rejects_oversized_declared_length_without_reading(monkeypatch):
    monkeypatch.setattr(settings, "MAX_FILE_SIZE", 3)
    declared = chat_body_limit() + 1
    rec = await call_app(
        JSON_HEADERS + [("content-length", str(declared))], [b"x" * 10]
    )
    assert rec.status == 413
    assert rec.error["code"] == "file_too_large"
    assert rec.receive_calls == 0


async def test_false_content_length_does_not_bypass_the_limit(monkeypatch):
    monkeypatch.setattr(settings, "MAX_FILE_SIZE", 3)
    chunk = 64 * 1024
    total_chunks = 40
    rec = await call_app(
        JSON_HEADERS + [("content-length", "100")],
        [b" " * chunk for _ in range(total_chunks)],
    )

    assert rec.status == 413
    assert rec.error["code"] == "file_too_large"
    assert rec.consumed <= chat_body_limit() + chunk
    assert rec.consumed < chunk * total_chunks


async def test_missing_content_length_is_400_through_the_app():
    rec = await call_app(JSON_HEADERS, [b"{}"])
    assert rec.status == 400
    assert rec.error["code"] == "invalid_request"
    assert rec.receive_calls == 0


async def test_valid_request_through_the_app_with_chunked_body():
    payload = {
        "model": EXTRACTION_MODEL_ID,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "file",
                        "file": {
                            "filename": "a.txt",
                            "file_data": "data:text/plain;base64,"
                            "0J/RgNC40LLQtdGCINC80LjRgCE=",
                        },
                    }
                ],
            }
        ],
    }
    body = json.dumps(payload).encode("utf-8")
    parts = [body[:30], body[30:90], body[90:]]
    rec = await call_app(
        JSON_HEADERS + [("content-length", str(len(body)))],
        parts,
    )
    assert rec.status == 200
    content = json.loads(rec.body)["choices"][0]["message"]["content"]
    assert content == "--- FILE: a.txt ---\nПривет мир!"


async def test_get_through_the_app_is_405_in_the_envelope():
    rec = await call_app([], [], method="GET")
    assert rec.status == 405
    assert rec.error["code"] == "method_not_allowed"
