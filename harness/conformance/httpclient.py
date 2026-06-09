"""Raw request-target HTTP/1.1 client — does not normalize URLs."""

from __future__ import annotations

import base64
import socket
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from conformance.report import HttpSnapshot


@dataclass
class RequestSpec:
    method: str
    target: str
    headers: dict[str, str] | None = None
    body: bytes = b""


def build_request_bytes(host: str, port: int, spec: RequestSpec) -> bytes:
    """Build raw HTTP/1.1 request bytes with harness framing headers."""
    lines = [f"{spec.method.upper()} {spec.target} HTTP/1.1"]
    lines.append(f"Host: {host}:{port}")
    lines.append("Connection: close")
    extra = dict(spec.headers or {})
    for key in ("Host", "Connection", "Content-Length"):
        extra.pop(key, None)
    if spec.body:
        lines.append(f"Content-Length: {len(spec.body)}")
    for name, value in extra.items():
        lines.append(f"{name}: {value}")
    raw = "\r\n".join(lines) + "\r\n\r\n"
    return raw.encode("ascii", errors="strict") + spec.body


def parse_response_headers(header_block: bytes) -> tuple[int, dict[str, list[str]]]:
    text = header_block.decode("iso-8859-1", errors="replace")
    lines = text.split("\r\n")
    if not lines:
        raise ValueError("empty response")
    status_line = lines[0]
    parts = status_line.split(" ", 2)
    if len(parts) < 2:
        raise ValueError(f"bad status line: {status_line!r}")
    status = int(parts[1])
    headers: dict[str, list[str]] = {}
    for line in lines[1:]:
        if not line:
            continue
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        key = name.strip().lower()
        headers.setdefault(key, []).append(value.strip())
    return status, headers


def read_http_response(sock: socket.socket, method: str) -> HttpSnapshot:
    """Read HTTP/1.1 response with RFC-correct entity framing."""
    header_data = bytearray()
    while b"\r\n\r\n" not in header_data:
        chunk = sock.recv(4096)
        if not chunk:
            break
        header_data.extend(chunk)
        if len(header_data) > 65536:
            raise ValueError("response headers too large")
    if b"\r\n\r\n" not in header_data:
        return HttpSnapshot(status=None, transport_error="EOF before response headers")
    head_raw, rest_raw = header_data.split(b"\r\n\r\n", 1)
    head = bytes(head_raw)
    rest = bytes(rest_raw)
    status, headers = parse_response_headers(head)

    if method.upper() == "HEAD":
        return HttpSnapshot(status=status, headers=headers, body=b"")

    te = headers.get("transfer-encoding", [])
    if any(v.lower() == "chunked" for v in te):
        body = _decode_chunked(_PrefixedSocket(sock, rest))
    else:
        cl = headers.get("content-length")
        if cl:
            expected = int(cl[-1])
            body = rest
            if len(body) < expected:
                more = _read_exact_from(
                    _PrefixedSocket(sock, b""), expected - len(body)
                )
                if more:
                    body += more
            body = body[:expected]
        else:
            body = rest
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                body += chunk

    return HttpSnapshot(status=status, headers=headers, body=body)


class _PrefixedSocket:
    """Socket wrapper that serves a prefix buffer before blocking reads."""

    def __init__(self, inner: socket.socket, prefix: bytes) -> None:
        self._inner = inner
        self._buf = prefix

    def recv(self, n: int) -> bytes:
        if self._buf:
            out = self._buf[:n]
            self._buf = self._buf[n:]
            return out
        return self._inner.recv(n)


def _decode_chunked(reader: _PrefixedSocket) -> bytes:
    chunks: list[bytes] = []
    while True:
        line = _read_line_from(reader)
        if line is None:
            break
        size_str = line.split(b";", 1)[0].strip()
        try:
            size = int(size_str, 16)
        except ValueError:
            break
        if size == 0:
            _read_line_from(reader)
            break
        data = _read_exact_from(reader, size)
        if data is None:
            break
        chunks.append(data)
        _read_line_from(reader)
    return b"".join(chunks)


def _read_line_from(reader: _PrefixedSocket) -> bytes | None:
    buf = bytearray()
    while True:
        ch = reader.recv(1)
        if not ch:
            return None if not buf else bytes(buf)
        buf.extend(ch)
        if len(buf) >= 2 and buf[-2:] == b"\r\n":
            return bytes(buf[:-2])


def _read_exact_from(reader: _PrefixedSocket, n: int) -> bytes | None:
    buf = bytearray()
    while len(buf) < n:
        chunk = reader.recv(n - len(buf))
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)


def send(
    base_url: str,
    request: dict[str, Any],
    *,
    timeout: float = 10.0,
) -> HttpSnapshot:
    """Send one request over a fresh TCP connection."""
    parsed = urlparse(base_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    body = _request_body(request)
    spec = RequestSpec(
        method=request["method"],
        target=request["target"],
        headers=request.get("headers"),
        body=body,
    )

    start = time.perf_counter()
    sock = socket.create_connection((host, port), timeout=timeout)
    try:
        sock.settimeout(timeout)
        sock.sendall(build_request_bytes(host, port, spec))
        snap = read_http_response(sock, spec.method)
        snap.elapsed_ms = (time.perf_counter() - start) * 1000.0
        return snap
    except socket.timeout:
        return HttpSnapshot(
            transport_error="timeout",
            elapsed_ms=(time.perf_counter() - start) * 1000.0,
        )
    except OSError as exc:
        return HttpSnapshot(
            transport_error=str(exc),
            elapsed_ms=(time.perf_counter() - start) * 1000.0,
        )
    finally:
        try:
            sock.close()
        except OSError:
            pass


def _request_body(request: dict[str, Any]) -> bytes:
    if "body_exact" in request:
        return request["body_exact"].encode("utf-8")
    if "body_base64" in request:
        return base64.b64decode(request["body_base64"])
    if "body_file" in request:
        from pathlib import Path

        return Path(request["body_file"]).read_bytes()
    return b""


# --- self-test against loopback echo server ---


def _echo_server(port: int, received: list[bytes], ready: threading.Event) -> None:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(1)
    ready.set()
    conn, _ = srv.accept()
    try:
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = conn.recv(4096)
            if not chunk:
                break
            data += chunk
        received.append(data)
        # Extract request line for echo verification
        first_line = data.split(b"\r\n", 1)[0]
        body = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: text/plain\r\n"
            b"Content-Length: " + str(len(first_line)).encode() + b"\r\n"
            b"Connection: close\r\n\r\n" + first_line
        )
        conn.sendall(body)
    finally:
        conn.close()
        srv.close()


def self_test() -> list[str]:
    """Verify verbatim request-target out and RFC-correct response in."""
    errors: list[str] = []
    received: list[bytes] = []
    ready = threading.Event()
    srv_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv_sock.bind(("127.0.0.1", 0))
    port = srv_sock.getsockname()[1]
    srv_sock.close()

    thread = threading.Thread(
        target=_echo_server, args=(port, received, ready), daemon=True
    )
    thread.start()
    ready.wait(timeout=5.0)

    target = "/grep?arg=needle/jq?arg=.items%5B%5D/haystack.json"
    snap = send(
        f"http://127.0.0.1:{port}",
        {"method": "GET", "target": target, "headers": {}},
        timeout=5.0,
    )
    thread.join(timeout=5.0)

    if not received:
        errors.append("echo server received no data")
        return errors

    req = received[0]
    if f"GET {target} HTTP/1.1".encode() not in req:
        errors.append(f"request line not verbatim: {req[:120]!r}")
    if b"Host: 127.0.0.1:" not in req:
        errors.append("missing Host header")
    if b"Connection: close" not in req:
        errors.append("missing Connection: close")

    if snap.status != 200:
        errors.append(f"expected status 200, got {snap.status}")
    if snap.body != f"GET {target} HTTP/1.1".encode():
        errors.append(f"unexpected echo body: {snap.body!r}")

    # chunked response test
    errors.extend(_self_test_chunked())
    return errors


def _self_test_chunked() -> list[str]:
    errors: list[str] = []
    ready = threading.Event()

    def chunked_srv(port: int) -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", port))
        srv.listen(1)
        ready.set()
        conn, _ = srv.accept()
        try:
            _ = conn.recv(4096)
            resp = (
                b"HTTP/1.1 200 OK\r\n"
                b"Transfer-Encoding: chunked\r\n"
                b"Connection: close\r\n\r\n"
                b"5\r\nhello\r\n"
                b"0\r\n\r\n"
            )
            conn.sendall(resp)
        finally:
            conn.close()
            srv.close()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    t = threading.Thread(target=chunked_srv, args=(port,), daemon=True)
    t.start()
    ready.wait(timeout=5.0)
    snap = send(
        f"http://127.0.0.1:{port}", {"method": "GET", "target": "/"}, timeout=5.0
    )
    t.join(timeout=5.0)
    if snap.body != b"hello":
        errors.append(f"chunked decode failed: {snap.body!r}")
    return errors
