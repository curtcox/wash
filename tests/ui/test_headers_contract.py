"""Track A-0 header audit: reference impl emits execution metadata headers."""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHONPATH = str(REPO_ROOT / "impls" / "reference")

REQUIRED_HEADERS = (
    "x-webshell-source",
    "x-webshell-command",
    "x-webshell-pipeline",
    "x-webshell-resolved-path",
)


def _write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _wait_for_server(port: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=0.3):
                return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.05)
    raise RuntimeError(f"server on port {port} did not start")


def _start_server(root: Path) -> tuple[subprocess.Popen[str], int]:
    env = os.environ.copy()
    env["PYTHONPATH"] = PYTHONPATH + (
        f":{env['PYTHONPATH']}" if env.get("PYTHONPATH") else ""
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", "wash.server", "--root", str(root), "--port", "0"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
    )
    assert proc.stdout is not None
    port = None
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        line = proc.stdout.readline().strip()
        if line.startswith("WASH-PORT "):
            port = int(line.split()[1])
            break
    if port is None:
        proc.kill()
        raise RuntimeError("wash.server did not report WASH-PORT")
    _wait_for_server(port)
    return proc, port


def test_pipeline_response_emits_four_execution_headers(tmp_path: Path) -> None:
    _write(tmp_path, "env/path", "bin\n")
    _write(tmp_path, "env/meta/grep", "arity 1\nmime text/plain\n")
    _write(tmp_path, "bin/grep", "#!/bin/sh\ngrep \"$@\"\n")
    _write(tmp_path, "exec", "* sh\n")
    _write(tmp_path, "data.txt", "needle haystack\n")
    (tmp_path / "bin" / "grep").chmod(0o755)

    proc, port = _start_server(tmp_path)
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/grep/needle/data.txt",
            timeout=5,
        ) as response:
            headers = {key.lower(): value for key, value in response.headers.items()}
            for header in REQUIRED_HEADERS:
                assert headers.get(header), f"missing {header}"
    finally:
        proc.terminate()
        proc.wait(timeout=5)
