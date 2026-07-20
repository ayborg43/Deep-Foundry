"""Minimal authenticated forward proxy with DNS pinning and SSRF denial."""

from __future__ import annotations

import base64
import ipaddress
import os
import select
import socket
import socketserver
from urllib.parse import urlsplit

MAX_HEADER_BYTES = 32 * 1024
CONNECT_TIMEOUT = float(os.environ.get("PROXY_CONNECT_TIMEOUT_SECONDS", "10"))
IDLE_TIMEOUT = float(os.environ.get("PROXY_IDLE_TIMEOUT_SECONDS", "20"))
MAX_TRANSFER_BYTES = int(os.environ.get("BROWSER_MAX_TRANSFER_BYTES", str(25 * 1024 * 1024)))
TOKEN = os.environ.get("BROWSER_PROXY_TOKEN", "")


def _public_addresses(host: str, port: int) -> list[str]:
    try:
        rows = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("Destination could not be resolved.") from exc
    addresses: list[str] = []
    for row in rows:
        candidate = row[4][0]
        if candidate not in addresses:
            addresses.append(candidate)
    if not addresses or not all(ipaddress.ip_address(value).is_global for value in addresses):
        raise ValueError("Private, local, mixed, or reserved destinations are blocked.")
    return sorted(addresses, key=lambda value: ipaddress.ip_address(value).version)


def _connect_pinned(host: str, port: int) -> socket.socket:
    last_error: OSError | None = None
    for address in _public_addresses(host, port):
        try:
            return socket.create_connection((address, port), timeout=CONNECT_TIMEOUT)
        except OSError as exc:
            last_error = exc
    raise ValueError(f"Could not connect to the public destination: {last_error}")


def _authorized(headers: list[bytes]) -> bool:
    if not TOKEN:
        return False
    expected = "Basic " + base64.b64encode(f"browser:{TOKEN}".encode()).decode()
    for line in headers:
        key, separator, value = line.decode("latin-1").partition(":")
        if separator and key.strip().lower() == "proxy-authorization":
            return value.strip() == expected
    return False


def _relay(left: socket.socket, right: socket.socket) -> None:
    sockets = [left, right]
    transferred = 0
    for item in sockets:
        item.setblocking(False)
    while True:
        readable, _, exceptional = select.select(sockets, [], sockets, IDLE_TIMEOUT)
        if exceptional or not readable:
            return
        for source in readable:
            target = right if source is left else left
            try:
                chunk = source.recv(64 * 1024)
                if not chunk:
                    return
                transferred += len(chunk)
                if transferred > MAX_TRANSFER_BYTES:
                    return
                target.sendall(chunk)
            except (BlockingIOError, BrokenPipeError, ConnectionResetError, OSError):
                return


class ProxyHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        self.request.settimeout(IDLE_TIMEOUT)
        data = b""
        while b"\r\n\r\n" not in data and len(data) <= MAX_HEADER_BYTES:
            chunk = self.request.recv(4096)
            if not chunk:
                return
            data += chunk
        if len(data) > MAX_HEADER_BYTES or b"\r\n\r\n" not in data:
            self._reply(431, "Request Header Fields Too Large")
            return
        header_block, remainder = data.split(b"\r\n\r\n", 1)
        lines = header_block.split(b"\r\n")
        try:
            method, target, version = lines[0].decode("latin-1").split(" ", 2)
        except ValueError:
            self._reply(400, "Bad Request")
            return
        if not _authorized(lines[1:]):
            self.request.sendall(
                b"HTTP/1.1 407 Proxy Authentication Required\r\n"
                b'Proxy-Authenticate: Basic realm="research-browser"\r\n'
                b"Connection: close\r\n\r\n"
            )
            return
        try:
            if method.upper() == "CONNECT":
                self._handle_connect(target)
            else:
                self._handle_http(method, target, version, lines[1:], remainder)
        except ValueError:
            self._reply(403, "Forbidden")
        except OSError:
            self._reply(502, "Bad Gateway")

    def _handle_connect(self, target: str) -> None:
        host, separator, raw_port = target.rpartition(":")
        if not separator or not host:
            raise ValueError("CONNECT requires host:port.")
        port = int(raw_port)
        if port != 443:
            raise ValueError("Only HTTPS port 443 is permitted.")
        upstream = _connect_pinned(host.strip("[]"), port)
        try:
            self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            _relay(self.request, upstream)
        finally:
            upstream.close()

    def _handle_http(
        self,
        method: str,
        target: str,
        version: str,
        headers: list[bytes],
        remainder: bytes,
    ) -> None:
        parsed = urlsplit(target)
        if parsed.scheme.lower() != "http" or not parsed.hostname:
            raise ValueError("Only absolute public HTTP URLs are permitted.")
        port = parsed.port or 80
        if port != 80:
            raise ValueError("Only HTTP port 80 is permitted.")
        upstream = _connect_pinned(parsed.hostname, port)
        try:
            path = parsed.path or "/"
            if parsed.query:
                path += f"?{parsed.query}"
            forwarded = [f"{method} {path} {version}".encode("latin-1")]
            for line in headers:
                key = line.split(b":", 1)[0].strip().lower()
                if key not in {
                    b"proxy-authorization",
                    b"proxy-connection",
                    b"connection",
                }:
                    forwarded.append(line)
            forwarded.extend([b"Connection: close", b"", b""])
            upstream.sendall(b"\r\n".join(forwarded) + remainder)
            _relay(self.request, upstream)
        finally:
            upstream.close()

    def _reply(self, status: int, reason: str) -> None:
        self.request.sendall(
            f"HTTP/1.1 {status} {reason}\r\nConnection: close\r\nContent-Length: 0\r\n\r\n".encode()
        )


class ThreadingProxy(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("BROWSER_PROXY_TOKEN is required.")
    with ThreadingProxy(("0.0.0.0", 8080), ProxyHandler) as server:
        server.serve_forever()
