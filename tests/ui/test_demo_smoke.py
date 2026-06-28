"""Headless smoke for the demo root and framed UI shell."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHONPATH = str(REPO_ROOT / "impls" / "reference")


def _wait_for_server(port: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=0.3):
                return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.05)
    raise RuntimeError(f"server on port {port} did not start")


def _fetch(url: str) -> tuple[int, str, dict[str, str]]:
    with urllib.request.urlopen(url, timeout=5) as response:
        body = response.read().decode("utf-8")
        headers = {key.lower(): value for key, value in response.headers.items()}
        return response.status, body, headers


def _materialize_demo_root(tmp_path: Path) -> Path:
    root = tmp_path / "demo-root"
    shutil.copytree(REPO_ROOT / "demo", root)
    subprocess.run(
        [str(REPO_ROOT / "bin" / "wash-ui-install"), str(root)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return root


def _start_server(root: Path) -> tuple[subprocess.Popen[bytes], int]:
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


def test_demo_fixture_has_notebook_command_and_names() -> None:
    demo = REPO_ROOT / "demo"
    assert (demo / "notebook" / "0" / "a").is_file()
    assert (demo / "bin" / "greet").is_file()
    assert (demo / "notes.md").is_file()
    assert (demo / "c").is_file()
    assert "gone /missing/path" in (demo / "c").read_text(encoding="utf-8")


def test_demo_root_serves_framed_ui_and_helpers(tmp_path: Path) -> None:
    root = _materialize_demo_root(tmp_path)
    proc, port = _start_server(root)
    base = f"http://127.0.0.1:{port}"
    try:
        status, html, _ = _fetch(f"{base}/ui/")
        assert status == 200
        assert "wash" in html
        assert 'id="content"' in html
        assert 'type="module"' in html

        status, body, headers = _fetch(f"{base}/ui/notebook/0/a")
        assert status == 200
        assert "wash" in body

        status, notebook, _ = _fetch(f"{base}/notebook/0/a")
        assert status == 200
        assert "Hello from the wash UI demo notebook." in notebook

        status, names_raw, _ = _fetch(f"{base}/names")
        assert status == 200
        names = json.loads(names_raw)
        assert any(entry["name"] == "topic" for entry in names["names"])
        assert any(
            finding["code"] == "dangling-target" for finding in names["findings"]
        )

        status, greet, headers = _fetch(f"{base}/greet")
        assert status == 200
        assert "hello from greet" in greet.lower()
        assert headers.get("x-webshell-command")
    finally:
        proc.terminate()
        proc.wait(timeout=5)
