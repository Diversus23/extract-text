"""Ограниченные HTTP-запросы: проверка до соединения и каждого редиректа."""

import ipaddress
import socket
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from requests.cookies import extract_cookies_to_jar
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import NewConnectionError
from urllib3.util.connection import create_connection

from app.config import settings


def is_public_ip(address):
    """Запрещает специальные адреса и дополнительные диапазоны из конфигурации."""
    ip = ipaddress.ip_address(address)
    if not ip.is_global or ip.is_multicast or ip.is_unspecified:
        return False
    if getattr(ip, "ipv4_mapped", None):
        return is_public_ip(str(ip.ipv4_mapped))
    return not any(
        ip in ipaddress.ip_network(item.strip())
        for item in settings.BLOCKED_IP_RANGES.split(",")
        if item.strip()
    )


class _PublicConnection:
    def _new_conn(self):
        # Проверяем именно адрес соединения. Повторное DNS-разрешение HTTP-клиентом
        # после предварительной проверки URL позволило бы DNS rebinding.
        addresses = socket.getaddrinfo(self.host, self.port, type=socket.SOCK_STREAM)
        if not addresses or any(not is_public_ip(item[4][0]) for item in addresses):
            raise ValueError("Access to internal IP addresses is prohibited")
        error = None
        for _, _, _, _, address in addresses:
            try:
                return create_connection(
                    (address[0], self.port),
                    self.timeout,
                    source_address=self.source_address,
                    socket_options=self.socket_options,
                )
            except OSError as exc:
                error = exc
        raise NewConnectionError(self, "Unable to connect to public address") from error


class _HTTPConnection(_PublicConnection, HTTPConnection):
    pass


class _HTTPSConnection(_PublicConnection, HTTPSConnection):
    pass


class _HTTPPool(HTTPConnectionPool):
    ConnectionCls = _HTTPConnection


class _HTTPSPool(HTTPSConnectionPool):
    ConnectionCls = _HTTPSConnection


class _PublicAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        super().init_poolmanager(*args, **kwargs)
        self.poolmanager.pool_classes_by_scheme = {
            "http": _HTTPPool,
            "https": _HTTPSPool,
        }


def web_session():
    """Отдельная сессия без прокси и netrc из окружения сервера."""
    session = requests.Session()
    session.trust_env = False
    session.mount("http://", _PublicAdapter())
    session.mount("https://", _PublicAdapter())
    return session


def safe_request(
    session,
    method,
    url,
    is_safe_url,
    *,
    timeout,
    follow_redirects=False,
    max_redirects=5,
    headers=None,
):
    """Возвращает потоковый ответ; вызывающий код обязан его закрыть."""
    max_redirects = min(max(max_redirects, 0), 10)
    for hop in range(max_redirects + 1):
        prepared = session.prepare_request(
            requests.Request(method, url, headers=headers)
        )
        if not is_safe_url(prepared.url):
            raise ValueError("Access to internal IP addresses is prohibited")
        # Session.send даже при allow_redirects=False читает тело редиректа для
        # response.next. Adapter.send позволяет закрыть его без чтения целиком.
        response = session.get_adapter(prepared.url).send(
            prepared, stream=True, timeout=timeout, verify=True, cert=None, proxies={}
        )
        extract_cookies_to_jar(session.cookies, prepared, response.raw)
        if not response.is_redirect:
            return response
        next_url = urljoin(prepared.url, response.headers["location"])
        if not is_safe_url(next_url):
            response.close()
            raise ValueError("Redirected to blocked URL")
        if not follow_redirects:
            return response
        response.close()
        if hop == max_redirects:
            raise ValueError("Too many redirects")
        url = next_url
    raise ValueError("Too many redirects")


def read_limited(response, limit):
    """Лимит фактически распакованных байтов, независимо от Content-Length."""
    content = bytearray()
    for chunk in response.iter_content(chunk_size=8192):
        if len(content) + len(chunk) > limit:
            raise ValueError("Response too large: download limit exceeded")
        content.extend(chunk)
    return bytes(content)
