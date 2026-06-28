"""Phase 3 panel contracts: names, explain, resolved path."""

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


def test_shell_contains_explain_and_resolved_panels() -> None:
    html = (REPO_ROOT / "ui" / "index.html").read_text(encoding="utf-8")

    assert 'id="explain-panel"' in html
    assert 'id="resolved-panel"' in html
    assert 'id="help-panel"' in html


def test_panels_module_exports_phase3_helpers() -> None:
    panels = (REPO_ROOT / "ui" / "modules" / "panels.js").read_text(encoding="utf-8")
    app = (REPO_ROOT / "ui" / "app.js").read_text(encoding="utf-8")
    api = (REPO_ROOT / "ui" / "modules" / "api.js").read_text(encoding="utf-8")

    assert "renderNamesPanel" in panels
    assert "renderExplainPanel" in panels
    assert "renderResolvedPath" in panels
    assert "shadowedNamesForDirectory" in panels
    assert "renderNamesPanel" in app
    assert "getExplain" in api
    assert "getHelp" in api
    assert "What ran" in panels


def test_escape_target_message_extracts_link_target() -> None:
    payload = _node_eval(
        textwrap.dedent(
            """
            import { escapeTargetFromMessage } from './ui/modules/panels.js';
            import { framedPath } from './ui/modules/router.js';
            const target = escapeTargetFromMessage('resolves outside the root to ../outside.txt');
            console.log(JSON.stringify({
              target,
              href: framedPath(target.startsWith('/') ? target : `/${target}`),
            }));
            """
        )
    )

    assert payload["target"] == "../outside.txt"
    assert payload["href"] == "/ui/../outside.txt"


def test_names_for_target_matches_node_a() -> None:
    payload = _node_eval(
        textwrap.dedent(
            """
            import { namesForTarget } from './ui/modules/panels.js';
            const names = [
              { scope: '.', name: 'topic', target: '/0/a', inert: false },
              { scope: '.', name: 'other', target: '/1/a', inert: true },
            ];
            console.log(JSON.stringify(namesForTarget(names, '/0/a')));
            """
        )
    )

    assert payload == [
        {"scope": ".", "name": "topic", "target": "/0/a", "inert": False},
    ]


def test_shadowed_names_for_directory() -> None:
    payload = _node_eval(
        textwrap.dedent(
            """
            import { shadowedNamesForDirectory } from './ui/modules/panels.js';
            const names = [
              { scope: 'notebook', name: 'topic', target: '/0/a', inert: true },
              { scope: 'notebook', name: 'live', target: '/1/a', inert: false },
            ];
            console.log(JSON.stringify([
              ...shadowedNamesForDirectory(names, '/notebook'),
            ]));
            """
        )
    )

    assert payload == ["topic"]
