"""Chrome contracts for stderr merge disclosure."""

from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _node_eval(source: str) -> dict:
    proc = subprocess.run(
        ["node", "--input-type=module", "--no-warnings", "-e", source],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout)


def test_chrome_exports_stderr_merge_helpers() -> None:
    chrome = (REPO_ROOT / "ui" / "modules" / "chrome.js").read_text(encoding="utf-8")
    app = (REPO_ROOT / "ui" / "app.js").read_text(encoding="utf-8")

    assert "stderrMergeNote" in chrome
    assert "runPanelValues" in chrome
    assert "runPanelValues" in app


def test_stderr_merge_note_detects_boundary_and_metadata() -> None:
    payload = _node_eval(
        textwrap.dedent(
            """
            import { stderrMergeNote } from './ui/modules/chrome.js';
            console.log(JSON.stringify({
              boundary: stderrMergeNote('/noisy/&/data.txt'),
              metadata: stderrMergeNote('/cmd/x', {
                segments: [{ metadata: { stderr: 'merge' } }],
              }),
              none: stderrMergeNote('/plain.txt'),
            }));
            """
        )
    )

    assert "merge boundary" in payload["boundary"]
    assert "stderr merge" in payload["metadata"]
    assert payload["none"] == ""
