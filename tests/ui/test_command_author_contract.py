"""Phase 4 command authoring contracts: env/path wiring and exec rules."""

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


def test_editor_exports_command_author_helpers() -> None:
    editor = (REPO_ROOT / "ui" / "modules" / "editor.js").read_text(encoding="utf-8")
    app = (REPO_ROOT / "ui" / "app.js").read_text(encoding="utf-8")

    for name in (
        "commandNameFromScriptPath",
        "envPathNeedsWire",
        "appendLineFileEntry",
        "suggestExecRule",
        "planCommandSetup",
    ):
        assert name in editor
    assert "Command setup" in editor
    assert "onCreateCommand" in app
    assert "onWireEnvPath" in app


def test_env_path_needs_wire_and_append() -> None:
    payload = _node_eval(
        textwrap.dedent(
            """
            import {
              appendLineFileEntry,
              envPathNeedsWire,
            } from './ui/modules/editor.js';
            console.log(JSON.stringify({
              empty: envPathNeedsWire(''),
              wired: envPathNeedsWire('bin\\n'),
              merged: appendLineFileEntry('shared\\n', 'bin'),
            }));
            """
        )
    )

    assert payload["empty"] is True
    assert payload["wired"] is False
    assert payload["merged"] == "shared\nbin\n"


def test_suggest_exec_rule_from_shebang_and_extension() -> None:
    payload = _node_eval(
        textwrap.dedent(
            """
            import { suggestExecRule } from './ui/modules/editor.js';
            console.log(JSON.stringify({
              pyExt: suggestExecRule('tool.py'),
              shBody: suggestExecRule('tool', '#!/bin/sh\\necho hi'),
              pyBody: suggestExecRule('tool', '#!/usr/bin/env python3\\nprint(1)'),
            }));
            """
        )
    )

    assert payload["pyExt"] == "* python3"
    assert payload["shBody"] == "* sh"
    assert payload["pyBody"] == "* python3"


def test_plan_command_setup_lists_missing_pieces() -> None:
    payload = _node_eval(
        textwrap.dedent(
            """
            import { planCommandSetup } from './ui/modules/editor.js';
            console.log(JSON.stringify(planCommandSetup({
              commandName: 'greet',
              pathText: '',
              execText: '',
              metaExists: false,
              scriptBody: '#!/usr/bin/env python3\\nprint(1)',
            })));
            """
        )
    )

    labels = {step["label"] for step in payload["steps"]}
    assert "Create env/meta" in labels
    assert "Wire bin into env/path" in labels
    assert "Add exec interpreter rule" in labels


def test_shell_meta_form_present_for_env_meta_paths() -> None:
    editor = (REPO_ROOT / "ui" / "modules" / "editor.js").read_text(encoding="utf-8")

    assert "renderMetaForm" in editor
    assert "meta-form" in editor
