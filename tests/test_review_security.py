"""Регрессии ревью: сеть, ограничение входящих данных и чужие временные файлы."""

import base64
import gzip
import hashlib
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest

from app.config import settings
from app.extractors import TextExtractor
from app.main import app
from tests.test_chat_ingress import Recorder, make_scope


@pytest.fixture
def web_server(monkeypatch):
    seen = []
    monkeypatch.setattr("app.web_fetch.is_public_ip", lambda ip: ip == "127.0.0.1")

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self):
            seen.append(self.path)
            body = self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            seen.append(self.path)
            if self.path == "/cookie-start":
                self.send_response(302)
                self.send_header("Location", "/cookie-finish")
                self.send_header("Set-Cookie", "session=allowed; Path=/")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if (
                self.path == "/cookie-finish"
                and "session=allowed" not in self.headers.get("Cookie", "")
            ):
                self.send_error(403)
                return
            if self.path == "/socket":
                key = (
                    self.headers["Sec-WebSocket-Key"]
                    + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
                )
                accept = base64.b64encode(hashlib.sha1(key.encode()).digest()).decode()
                self.send_response(101)
                self.send_header("Upgrade", "websocket")
                self.send_header("Connection", "Upgrade")
                self.send_header("Sec-WebSocket-Accept", accept)
                self.end_headers()
                self.wfile.write(b"\x81\x09websocket")
                self.wfile.flush()
                self.close_connection = True
                return
            if self.path in {"/relative", "/loop"}:
                self.send_response(302)
                self.send_header("Location", "/loop" if self.path == "/loop" else "/ok")
                body = b""
            elif self.path == "/redirect":
                self.send_response(302)
                self.send_header(
                    "Location", f"http://localhost:{self.server.server_port}/internal"
                )
                body = b""
            else:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                body = b"<html>safe</html>"
                if self.path == "/large":
                    body = gzip.compress(b"x" * 100_000)
                    self.send_header("Content-Encoding", "gzip")
                if self.path == "/browser":
                    body = (
                        '<html><body><p id="result">before</p>'
                        '<script>document.querySelector("#result").textContent="rendered";'
                        f'fetch("http://localhost:{self.server.server_port}/internal");'
                        f'new WebSocket("ws://localhost:{self.server.server_port}/internal-ws");'
                        "</script></body></html>"
                    ).encode()
                if self.path == "/interactive":
                    body = (
                        '<html><body><p id="result">before</p><script>'
                        'Promise.all([fetch("/post", {method:"POST", body:"payload"}).then(r=>r.text()),'
                        'new Promise(resolve=>{const s=new WebSocket("ws://"+location.host+"/socket");'
                        "s.onmessage=e=>resolve(e.data);})]).then(parts=>"
                        'document.querySelector("#result").textContent=parts.join("|"));'
                        "</script></body></html>"
                    ).encode()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    extractor = TextExtractor()
    # Только тестовый сервер считается публичным, localhost остаётся запрещённым.
    monkeypatch.setattr(
        extractor, "_is_safe_url", lambda url: urlparse(url).hostname == "127.0.0.1"
    )
    yield extractor, f"http://127.0.0.1:{server.server_port}", seen
    server.shutdown()
    server.server_close()
    thread.join()
    extractor._thread_pool.shutdown()


@pytest.mark.parametrize(
    "method",
    [
        "_extract_page_with_requests",
        "_determine_content_type",
        "_download_and_extract_file",
    ],
)
def test_redirect_is_rejected_before_internal_request(web_server, method):
    extractor, url, seen = web_server
    options = SimpleNamespace(
        web_page_timeout=3, follow_redirects=True, max_redirects=5
    )
    with pytest.raises(ValueError):
        getattr(extractor, method)(url + "/redirect", extraction_options=options)
    assert seen == ["/redirect"]


def test_image_redirect_never_contacts_internal_host(web_server):
    extractor, url, seen = web_server
    assert extractor._process_single_image({"src": "/redirect"}, url) is None
    assert seen == ["/redirect"]


def test_html_limit_counts_decompressed_bytes(web_server, monkeypatch):
    extractor, url, _ = web_server
    monkeypatch.setattr(settings, "MAX_FILE_SIZE", 1024)
    with pytest.raises(ValueError, match="[Ll]arge|limit"):
        extractor._extract_page_with_requests(url + "/large")


def test_safe_relative_redirect_and_html_still_work(web_server):
    extractor, url, seen = web_server
    options = SimpleNamespace(follow_redirects=True, max_redirects=2)
    html, final = extractor._extract_page_with_requests(
        url + "/relative", extraction_options=options
    )
    assert html == "<html>safe</html>"
    assert final == url + "/ok"
    assert seen == ["/relative", "/ok"]


def test_redirect_preserves_session_cookie(web_server):
    extractor, url, _ = web_server
    options = SimpleNamespace(follow_redirects=True, max_redirects=2)
    html, _ = extractor._extract_page_with_requests(
        url + "/cookie-start", extraction_options=options
    )
    assert html == "<html>safe</html>"


@pytest.mark.parametrize("limit", [0, 2])
def test_redirect_budget_stops_before_extra_request(web_server, limit):
    extractor, url, seen = web_server
    options = SimpleNamespace(follow_redirects=True, max_redirects=limit)
    with pytest.raises(ValueError, match="Too many redirects"):
        extractor._extract_page_with_requests(url + "/loop", extraction_options=options)
    assert len(seen) == limit + 1


def test_connection_rechecks_ip_after_url_validation(web_server, monkeypatch):
    extractor, url, seen = web_server
    # URL-проверка разрешила адрес, а DNS перед соединением вернул запрещённый IP.
    monkeypatch.setattr("app.web_fetch.is_public_ip", lambda ip: False)
    with pytest.raises(ValueError, match="internal IP"):
        extractor._extract_page_with_requests(url)
    assert seen == []


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "::1",
        "::ffff:127.0.0.1",
        "224.0.0.1",
        "0.0.0.0",
    ],
)
def test_special_addresses_never_pass_connection_guard(address):
    from app.web_fetch import is_public_ip

    assert not is_public_ip(address)


def test_large_image_is_rejected_before_ocr(web_server, monkeypatch):
    extractor, url, _ = web_server
    monkeypatch.setattr(settings, "MAX_FILE_SIZE", 1024)

    def unexpected_ocr(*args):
        pytest.fail("Oversized image reached OCR")

    monkeypatch.setattr(extractor, "_safe_tesseract_ocr", unexpected_ocr)
    assert extractor._process_single_image({"src": "/large"}, url) is None


def test_browser_blocks_internal_subrequests_but_executes_js(web_server):
    extractor, url, seen = web_server
    options = SimpleNamespace(
        web_page_timeout=5,
        js_render_timeout=1000,
        web_page_delay=0.2,
        enable_lazy_loading_wait=False,
        enable_javascript=True,
    )
    html, _ = extractor._extract_page_with_playwright(
        url + "/browser", extraction_options=options
    )
    assert "rendered</p>" in html
    assert "/internal" not in seen
    assert "/internal-ws" not in seen


def test_browser_preserves_post_and_websocket_content(web_server):
    extractor, url, seen = web_server
    options = SimpleNamespace(
        web_page_timeout=5,
        js_render_timeout=2,
        web_page_delay=0,
        enable_lazy_loading_wait=False,
        enable_javascript=True,
    )
    html, _ = extractor._extract_page_with_playwright(
        url + "/interactive", extraction_options=options
    )
    assert "payload|websocket</p>" in html
    assert "/post" in seen and "/socket" in seen


@pytest.mark.parametrize("path", ["/v1/extract/file", "/v1/extract/base64"])
@pytest.mark.asyncio
async def test_documents_auth_before_receive(monkeypatch, path):
    monkeypatch.setattr(settings, "AUTH_MODE", "apikey")
    monkeypatch.setattr(settings, "API_KEYS", ["secret"])
    recorder = Recorder([b"invalid body"])
    await app(
        make_scope(
            [("content-type", "application/json"), ("content-length", "12")], path=path
        ),
        recorder.receive,
        recorder.send,
    )
    assert recorder.status == 401
    assert recorder.consumed == 0


@pytest.mark.parametrize("path", ["/v1/extract/file", "/v1/extract/base64"])
@pytest.mark.asyncio
async def test_documents_reject_declared_size_before_receive(monkeypatch, path):
    monkeypatch.setattr(settings, "AUTH_MODE", "none")
    monkeypatch.setattr(settings, "MAX_FILE_SIZE", 1024)
    recorder = Recorder([b"{}"])
    await app(
        make_scope(
            [("content-type", "application/json"), ("content-length", "1000000")],
            path=path,
        ),
        recorder.receive,
        recorder.send,
    )
    assert recorder.status == 413
    assert recorder.consumed == 0


@pytest.mark.parametrize("path", ["/v1/extract/file", "/v1/extract/base64"])
@pytest.mark.asyncio
async def test_documents_enforce_actual_body_limit(monkeypatch, path):
    monkeypatch.setattr(settings, "AUTH_MODE", "none")
    monkeypatch.setattr(settings, "MAX_FILE_SIZE", 1024)
    content_type = "application/json"
    body = b" " * 70000
    if path.endswith("/file"):
        content_type = "multipart/form-data; boundary=test"
        body = (
            b'--test\r\nContent-Disposition: form-data; name="file"; filename="x.txt"\r\n\r\n'
            + body
        )
    recorder = Recorder([body, b" " * 70000])
    await app(
        make_scope(
            [("content-type", content_type), ("content-length", "2")], path=path
        ),
        recorder.receive,
        recorder.send,
    )
    assert recorder.status == 413
    assert len(recorder.chunks) == 1


@pytest.mark.asyncio
async def test_chunked_multipart_success_and_limit_cleanup(monkeypatch):
    import starlette.formparsers

    monkeypatch.setattr(settings, "AUTH_MODE", "none")
    monkeypatch.setattr(settings, "MAX_FILE_SIZE", 1024)
    files = []
    original = starlette.formparsers.SpooledTemporaryFile

    def track_file(*args, **kwargs):
        file = original(*args, **kwargs)
        files.append(file)
        return file

    monkeypatch.setattr(starlette.formparsers, "SpooledTemporaryFile", track_file)
    header = b'--test\r\nContent-Disposition: form-data; name="file"; filename="x.txt"\r\nContent-Type: text/plain\r\n\r\n'
    for chunks, status in [
        ([header + b"hello", b"\r\n--test--\r\n"], 200),
        ([header + b"hello", b"x" * 70000], 413),
    ]:
        recorder = Recorder(chunks)
        scope = make_scope(
            [("content-type", "multipart/form-data; boundary=test")],
            path="/v1/extract/file",
        )
        await app(scope, recorder.receive, recorder.send)
        assert recorder.status == status
        assert files and all(file.closed for file in files)


@pytest.mark.parametrize("fail", [False, True])
@pytest.mark.asyncio
async def test_document_does_not_delete_other_request_files(
    tmp_path, monkeypatch, fail
):
    import tempfile

    from app.main import ExtractionError, _extract_document

    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    other = tmp_path / "tmp_other.pdf"
    other.write_bytes(b"active request")
    if fail:

        def broken(*args):
            raise ValueError("corrupt document")

        monkeypatch.setattr("app.main.text_extractor.extract_text", broken)
        with pytest.raises(ExtractionError):
            await _extract_document(b"hello", "x.txt")
    else:
        await _extract_document(b"hello", "x.txt")
    assert other.read_bytes() == b"active request"
