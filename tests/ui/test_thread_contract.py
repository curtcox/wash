"""Notebook thread contracts for Phase 2."""

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


def test_shell_contains_thread_and_files_panels() -> None:
    html = (REPO_ROOT / "ui" / "index.html").read_text(encoding="utf-8")

    assert 'id="thread-panel"' in html
    assert 'id="files-panel"' in html
    assert 'id="node-kind"' in html
    assert "View mode" in html


def test_collect_main_line_finds_sdt_path() -> None:
    payload = _node_eval(
        textwrap.dedent(
            """
            import { collectMainLine, nodeDirectoryFor } from './ui/modules/thread.js';
            const nodeDir = nodeDirectoryFor('/notebook/0/2/a');
            console.log(JSON.stringify({
              nodeDir,
              ...collectMainLine(nodeDir)
            }));
            """
        )
    )

    assert payload["nodeDir"] == "/notebook/0/2"
    assert payload["collectionRoot"] == "/notebook"
    assert payload["mainLine"] == [
        {"ordinal": "0", "path": "/notebook/0"},
        {"ordinal": "2", "path": "/notebook/0/2"},
    ]


def test_detect_node_kind_classifies_sdt_and_commands() -> None:
    payload = _node_eval(
        textwrap.dedent(
            """
            import { detectNodeKind } from './ui/modules/thread.js';
            console.log(JSON.stringify({
              sdt: detectNodeKind('/0/1/a', { commands: [{ name: 'grep' }] }),
              command: detectNodeKind('/grep/x/y', { commands: [{ name: 'grep' }] }),
              env: detectNodeKind('/env/path', { commands: [] }),
            }));
            """
        )
    )

    assert payload["sdt"] == "sdt-node"
    assert payload["command"] == "command"
    assert payload["env"] == "env-config"


def test_thread_renders_in_tree_name_chips() -> None:
    thread = (REPO_ROOT / "ui" / "modules" / "thread.js").read_text(encoding="utf-8")

    assert "thread-names" in thread
    assert "namesForNode" in thread


def test_shell_directory_uses_root_for_pipeline_results() -> None:
    payload = _node_eval(
        textwrap.dedent(
            """
            import { shellDirectory } from './ui/modules/thread.js';
            console.log(JSON.stringify({
              pipeline: shellDirectory('/grep/x/y', { pipeline: 'cat y | grep x' }),
              node: shellDirectory('/0/1/a', {}),
            }));
            """
        )
    )

    assert payload["pipeline"] == "."
    assert payload["node"] == "0/1"
