"""Term helper contracts for host-terminal launch matrix."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_term_returns_copyable_cd_and_directory(tmp_path: Path) -> None:
    notebook = tmp_path / "notebook"
    notebook.mkdir()
    env = {"WASH_UI_LAUNCH_TERMINAL": "0", "CI": "1"}
    proc = subprocess.run(
        [str(REPO_ROOT / "bin" / "term"), "notebook"],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    payload = json.loads(proc.stdout)

    assert payload["launched"] is False
    assert payload["command"] == f"cd {tmp_path / 'notebook'}"
    assert payload["directory"] == str(tmp_path / "notebook")


def test_term_respects_terminal_env_without_launching(tmp_path: Path) -> None:
    term = (REPO_ROOT / "bin" / "term").read_text(encoding="utf-8")

    assert "TERMINAL" in term
    assert "WASH_UI_LAUNCH_TERMINAL" in term
