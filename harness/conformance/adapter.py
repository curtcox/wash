"""TOML adapter manifest — launch, readiness, teardown."""

from __future__ import annotations

import os
import re
import signal
import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[import-not-found,no-redef]

from conformance.capabilities import load_manifest, origin_host
from conformance.httpclient import send

DEFAULT_BIND_FAILURE_RE = re.compile(
    r"EADDRINUSE|address already in use|address in use", re.IGNORECASE
)
WASH_PORT_RE = re.compile(r"^WASH-PORT\s+(\d+)\s*$")


@dataclass
class AdapterManifest:
    name: str
    start: list[str]
    stop: str = "SIGTERM"
    port_mode: str = "assigned"
    ready: dict[str, Any] = field(default_factory=lambda: {"type": "tcp"})
    ready_timeout_sec: float = 10.0
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    capabilities: str = ""
    interpreters: list[str] = field(default_factory=lambda: ["sh"])
    bind_failure_pattern: str = ""
    path: Path | None = None

    @property
    def repo_root(self) -> Path:
        if self.path is None:
            return Path.cwd()
        # adapters live in harness/adapters; repo root is two levels up from harness
        return self.path.resolve().parent.parent.parent


def harness_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def load_adapter(path: str | Path) -> AdapterManifest:
    path = Path(path)
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return AdapterManifest(
        name=data["name"],
        start=list(data["start"]),
        stop=data.get("stop", "SIGTERM"),
        port_mode=data.get("port_mode", "assigned"),
        ready=data.get("ready", {"type": "tcp"}),
        ready_timeout_sec=float(data.get("ready_timeout_sec", 10)),
        cwd=data.get("cwd"),
        env={str(k): str(v) for k, v in data.get("env", {}).items()},
        capabilities=data.get("capabilities", ""),
        interpreters=[str(i) for i in data.get("interpreters", ["sh"])],
        bind_failure_pattern=data.get("bind_failure_pattern", ""),
        path=path,
    )


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _substitute_argv(argv: list[str], *, root: str, port: int | None) -> list[str]:
    out: list[str] = []
    for arg in argv:
        s = arg.replace("{root}", root)
        if port is not None:
            s = s.replace("{port}", str(port))
        out.append(s)
    return out


@dataclass
class LaunchedServer:
    adapter: AdapterManifest
    process: subprocess.Popen[str]
    root: str
    host: str
    port: int
    base_url: str
    stdout_lines: list[str] = field(default_factory=list)
    stderr_lines: list[str] = field(default_factory=list)
    _capture_thread: threading.Thread | None = None

    def is_alive(self) -> bool:
        return self.process.poll() is None

    def captured_output(self) -> str:
        out = "\n".join(self.stdout_lines + self.stderr_lines)
        return out.strip()


def _start_capture(server: LaunchedServer) -> None:
    def reader(stream, buf: list[str]) -> None:
        if stream is None:
            return
        for line in iter(stream.readline, ""):
            buf.append(line.rstrip("\n"))

    def run() -> None:
        t1 = threading.Thread(
            target=reader,
            args=(server.process.stdout, server.stdout_lines),
            daemon=True,
        )
        t2 = threading.Thread(
            target=reader,
            args=(server.process.stderr, server.stderr_lines),
            daemon=True,
        )
        t1.start()
        t2.start()
        t1.join()
        t2.join()

    server._capture_thread = threading.Thread(target=run, daemon=True)
    server._capture_thread.start()


def launch(
    adapter: AdapterManifest,
    *,
    root: str,
    caps: dict[str, Any] | None = None,
    max_bind_retries: int = 5,
) -> LaunchedServer:
    if caps is None and adapter.capabilities:
        cap_path = adapter.repo_root / adapter.capabilities
        caps = load_manifest(cap_path)

    host = origin_host(caps) if caps else "127.0.0.1"
    bind_re = (
        re.compile(adapter.bind_failure_pattern, re.IGNORECASE)
        if adapter.bind_failure_pattern
        else DEFAULT_BIND_FAILURE_RE
    )

    cwd = adapter.repo_root / adapter.cwd if adapter.cwd else adapter.repo_root
    env = {**os.environ, **adapter.env}

    last_output = ""
    for attempt in range(max_bind_retries):
        port: int | None
        if adapter.port_mode == "ephemeral":
            port = None
            argv = _substitute_argv(adapter.start, root=root, port=None)
        else:
            port = _free_port()
            argv = _substitute_argv(adapter.start, root=root, port=port)

        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        server = LaunchedServer(
            adapter=adapter,
            process=proc,
            root=root,
            host=host,
            port=port or 0,
            base_url="",
        )
        _start_capture(server)

        if adapter.port_mode == "ephemeral":
            actual_port = _read_ephemeral_port(
                server, timeout=adapter.ready_timeout_sec
            )
            if actual_port is None:
                shutdown(server)
                captured = server.captured_output()
                if attempt + 1 < max_bind_retries and bind_re.search(captured):
                    last_output = captured
                    continue
                raise LaunchError("ephemeral port readout failed", captured)
            server.port = actual_port
        else:
            server.port = port  # type: ignore[assignment]

        server.base_url = f"http://{host}:{server.port}"

        if wait_until_ready(server, timeout=adapter.ready_timeout_sec):
            return server

        captured = server.captured_output()
        shutdown(server)
        if adapter.port_mode == "assigned" and bind_re.search(captured):
            last_output = captured
            continue
        raise LaunchError("server not ready", captured or last_output)

    raise LaunchError("bind retries exhausted", last_output)


class LaunchError(Exception):
    def __init__(self, message: str, child_output: str = "") -> None:
        super().__init__(message)
        self.child_output = child_output


def _read_ephemeral_port(server: LaunchedServer, *, timeout: float) -> int | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if server.stdout_lines:
            line = server.stdout_lines[0]
            m = WASH_PORT_RE.match(line)
            if m:
                return int(m.group(1))
            break
        if server.process.poll() is not None:
            return None
        time.sleep(0.05)
    return None


def wait_until_ready(server: LaunchedServer, *, timeout: float | None = None) -> bool:
    timeout = timeout if timeout is not None else server.adapter.ready_timeout_sec
    ready = server.adapter.ready
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if server.process.poll() is not None:
            return False
        if ready.get("type", "tcp") == "tcp":
            if _tcp_probe(server.host, server.port):
                return True
        elif ready.get("type") == "http":
            path = ready.get("path", "/")
            snap = send(
                server.base_url,
                {"method": "GET", "target": path, "headers": {}},
                timeout=min(2.0, timeout),
            )
            if snap.status is not None:
                return True
        time.sleep(0.1)
    return False


def _tcp_probe(host: str, port: int) -> bool:
    try:
        sock = socket.create_connection((host, port), timeout=1.0)
        sock.close()
        return True
    except OSError:
        return False


def shutdown(server: LaunchedServer, *, grace_sec: float = 5.0) -> None:
    if server.process.poll() is not None:
        return
    stop = server.adapter.stop
    if stop == "SIGTERM":
        try:
            os.killpg(server.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    elif stop == "SIGKILL":
        try:
            os.killpg(server.process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
    else:
        server.process.terminate()

    try:
        server.process.wait(timeout=grace_sec)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(server.process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        server.process.wait(timeout=2.0)
