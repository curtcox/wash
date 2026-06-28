"""Phase 4 editor contracts: meta validation, name scope, mutation planning."""

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


def test_shell_contains_author_panel() -> None:
    html = (REPO_ROOT / "ui" / "index.html").read_text(encoding="utf-8")

    assert 'id="author-panel"' in html


def test_editor_module_exports_phase4_helpers() -> None:
    editor = (REPO_ROOT / "ui" / "modules" / "editor.js").read_text(encoding="utf-8")
    app = (REPO_ROOT / "ui" / "app.js").read_text(encoding="utf-8")

    assert "validateMetaText" in editor
    assert "defaultNameScope" in editor
    assert "availableMutations" in editor
    assert "formatNamePreview" in editor
    assert "renderAuthorPanel" in editor
    assert "renderAuthorPanel" in app


def test_validate_meta_rejects_get_with_mutates() -> None:
    payload = _node_eval(
        textwrap.dedent(
            """
            import { validateMetaText } from './ui/modules/editor.js';
            console.log(JSON.stringify(validateMetaText('methods GET\\nmutates true')));
            """
        )
    )

    assert any("GET" in error and "mutates" in error for error in payload["errors"])


def test_default_name_scope_uses_nearest_directory() -> None:
    payload = _node_eval(
        textwrap.dedent(
            """
            import { defaultNameScope } from './ui/modules/editor.js';
            console.log(JSON.stringify({
              root: defaultNameScope('/'),
              notebook: defaultNameScope('/notebook/0/a'),
            }));
            """
        )
    )

    assert payload["root"] == "."
    assert payload["notebook"] == "notebook"


def test_available_mutations_for_plain_file_and_sdt_node() -> None:
    payload = _node_eval(
        textwrap.dedent(
            """
            import { availableMutations } from './ui/modules/editor.js';
            console.log(JSON.stringify({
              plain: availableMutations({ kind: 'plain-file', resourceOk: true }),
              directory: availableMutations({ kind: 'directory', resourceOk: true }),
              sdt: availableMutations({ kind: 'sdt-node', resourceOk: true }),
            }));
            """
        )
    )

    assert "save" in payload["plain"]
    assert "delete" in payload["plain"]
    assert "delete" in payload["directory"]
    assert "append-child" in payload["sdt"]
    assert "append-sibling" in payload["sdt"]


def test_name_preview_formats_error_warning_and_inert_states() -> None:
    payload = _node_eval(
        textwrap.dedent(
            """
            import { formatNamePreview } from './ui/modules/editor.js';
            console.log(JSON.stringify({
              dangling: formatNamePreview({
                valid: false,
                status: 'error',
                messages: ['unknown name'],
              }),
              escape: formatNamePreview({
                valid: true,
                status: 'warning',
                messages: ['resolves outside the root'],
              }),
              inert: formatNamePreview({
                valid: true,
                status: 'info',
                messages: ['name is inert because a literal child already exists'],
              }),
            }));
            """
        )
    )

    assert payload["dangling"]["className"] == "error"
    assert "unknown name" in payload["dangling"]["text"]
    assert payload["escape"]["className"] == "warning"
    assert "outside" in payload["escape"]["text"]
    assert payload["inert"]["className"] == "info"
    assert "inert" in payload["inert"]["text"]


def test_body_editor_supports_file_upload() -> None:
    editor = (REPO_ROOT / "ui" / "modules" / "editor.js").read_text(encoding="utf-8")

    assert 'type = "file"' in editor
    assert "Upload file" in editor
    assert "file.text()" in editor
