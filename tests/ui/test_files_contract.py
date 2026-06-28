"""Files browser contracts for Phase 2."""

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


def test_files_module_exists_and_links_entries() -> None:
    files = (REPO_ROOT / "ui" / "modules" / "files.js").read_text(encoding="utf-8")
    app = (REPO_ROOT / "ui" / "app.js").read_text(encoding="utf-8")

    assert "renderFilesBrowser" in files
    assert "fetchListing" in files
    assert "renderFilesBrowser" in app
    assert "hideFilesBrowser" in app


def test_files_module_marks_shadowed_names() -> None:
    files = (REPO_ROOT / "ui" / "modules" / "files.js").read_text(encoding="utf-8")

    assert "shadowedNamesForDirectory" in files
    assert "shadows-name" in files


def test_files_module_marks_live_mutating_commands() -> None:
    files = (REPO_ROOT / "ui" / "modules" / "files.js").read_text(encoding="utf-8")
    app = (REPO_ROOT / "ui" / "app.js").read_text(encoding="utf-8")

    assert "commandForFileEntry" in files
    assert "mutatesBadge" in files
    assert "commands: commandCatalog" in app
    assert "rootPath: rootInfo.root" in app


def test_command_for_file_entry_uses_live_command_paths() -> None:
    payload = _node_eval(
        textwrap.dedent(
            """
            import { commandForFileEntry } from './ui/modules/files.js';
            const commands = [
              { name: 'show', path: '/tmp/root/bin/show', mutates: false },
              { name: 'zap', path: '/tmp/root/bin/zap', mutates: true },
            ];
            console.log(JSON.stringify({
              match: commandForFileEntry(commands, '/bin/zap', { rootPath: '/tmp/root' }),
              miss: commandForFileEntry(commands, '/zap', { rootPath: '/tmp/root' }),
            }));
            """
        )
    )

    assert payload["match"]["name"] == "zap"
    assert payload["match"]["mutates"] is True
    assert payload["miss"] is None
