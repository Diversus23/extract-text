"""Локальный egress-прокси Chromium: проверяет адрес до TCP-соединения."""

import select
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, urlunsplit

from app.web_fetch import _HTTPConnection


class BrowserProxy:
    """Сохраняет HTTP/WebSocket/TLS браузера, ограничивая адреса и объём сети."""

    def __init__(self, is_safe_url, limit, timeout):
        """Задаёт политику одного изолированного браузера."""
        self.is_safe_url = is_safe_url
        self.remaining = limit
        self.timeout = timeout
        self.lock = threading.Lock()
        self.sockets = set()
        self.closed = threading.Event()
        self.server = None

    def _relay(self, client, upstream):
        while not self.closed.is_set():
            readable, _, _ = select.select([client, upstream], [], [], 0.2)
            for source in readable:
                data = source.recv(8192)
                if not data:
                    return
                with self.lock:
                    self.remaining -= len(data)
                    if self.remaining < 0:
                        return
                (upstream if source is client else client).sendall(data)

    def __enter__(self):
        """Запускает прокси только на loopback, без внешнего порта сервиса."""
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            rbufsize = 0  # После заголовков тело читается напрямую из socket.

            def log_message(self, *args):
                pass

            def do_CONNECT(self):
                self.forward(tunnel=True)

            def __getattr__(self, name):
                if name.startswith("do_"):
                    return self.forward
                raise AttributeError(name)

            def forward(self, tunnel=False):
                self.close_connection = True
                upstream = None
                started = False
                try:
                    parsed = urlsplit("https://" + self.path if tunnel else self.path)
                    scheme = {"ws": "http", "wss": "https"}.get(
                        parsed.scheme, parsed.scheme
                    )
                    checked_url = urlunsplit(parsed._replace(scheme=scheme))
                    if scheme not in {"http", "https"} or not owner.is_safe_url(
                        checked_url
                    ):
                        self.send_error(403, "Blocked network address")
                        return
                    port = parsed.port or (443 if scheme == "https" else 80)
                    # _new_conn фиксирует проверенный DNS-адрес. TLS остаётся
                    # сквозным: сертификат и SNI проверяет сам Chromium.
                    upstream = _HTTPConnection(
                        parsed.hostname, port, timeout=owner.timeout
                    )._new_conn()
                    self.connection.settimeout(owner.timeout)
                    with owner.lock:
                        if owner.closed.is_set():
                            return
                        owner.sockets.update((upstream, self.connection))
                    if tunnel:
                        self.send_response(200, "Connection established")
                        self.end_headers()
                    else:
                        target = urlunsplit(
                            ("", "", parsed.path or "/", parsed.query, "")
                        )
                        lines = [f"{self.command} {target} HTTP/1.1"]
                        upgrade = self.headers.get("Upgrade", "").lower() == "websocket"
                        for key, value in self.headers.items():
                            if key.lower() in {
                                "proxy-authorization",
                                "proxy-connection",
                                "connection",
                            }:
                                continue
                            lines.append(f"{key}: {value}")
                        # Не переиспользуем HTTP-прокси-соединение для другого
                        # origin. WebSocket после Upgrade остаётся туннелем.
                        lines.append(
                            "Connection: Upgrade" if upgrade else "Connection: close"
                        )
                        upstream.sendall(
                            ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1")
                        )
                    started = True
                    owner._relay(self.connection, upstream)
                except (OSError, ValueError):
                    if not started:
                        self.send_error(502, "Network request rejected")
                finally:
                    if upstream is not None:
                        with owner.lock:
                            owner.sockets.discard(upstream)
                            owner.sockets.discard(self.connection)
                        upstream.close()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True
        )
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        return self

    def __exit__(self, *args):
        """Закрывает активные туннели вместе с браузером."""
        self.closed.set()
        with self.lock:
            for connection in self.sockets:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
