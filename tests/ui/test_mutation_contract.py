"""Phase 4 mutation contracts: API helpers and confirm chrome."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_api_exports_mutation_helpers() -> None:
    api = (REPO_ROOT / "ui" / "modules" / "api.js").read_text(encoding="utf-8")

    assert "putResource" in api
    assert "deleteResource" in api
    assert "postAppend" in api
    assert "postNameNew" in api
    assert "postNameSet" in api
    assert "postNameRm" in api
    assert "getNamePreview" in api
    assert "URLSearchParams" in api


def test_chrome_exports_mutation_confirm_and_badge() -> None:
    chrome = (REPO_ROOT / "ui" / "modules" / "chrome.js").read_text(encoding="utf-8")
    app = (REPO_ROOT / "ui" / "app.js").read_text(encoding="utf-8")

    assert "confirmMutation" in chrome
    assert "mutatesBadge" in chrome
    assert "mutation-confirm" in chrome
    assert "window.confirm" not in chrome
    assert "confirmMutation" in app


def test_app_wires_explicit_method_controls() -> None:
    app = (REPO_ROOT / "ui" / "app.js").read_text(encoding="utf-8")

    assert "Save" in app or "save" in app
    assert "Delete" in app or "delete" in app
    assert "resolved path" in app.lower() or "resolvedPath" in app


def test_app_blocks_invalid_meta_before_normal_save() -> None:
    app = (REPO_ROOT / "ui" / "app.js").read_text(encoding="utf-8")

    assert "validateMetaText(body)" in app
    assert "commandNameFromMetaPath(target)" in app
    assert "Meta is invalid" in app
    assert "putResource(target, body)" in app


def test_commands_panel_uses_mutates_badge() -> None:
    app = (REPO_ROOT / "ui" / "app.js").read_text(encoding="utf-8")
    panels = (REPO_ROOT / "ui" / "modules" / "panels.js").read_text(encoding="utf-8")

    assert "mutatesBadge" in app
    assert "command.mutates" in app
    assert "segment.metadata?.mutates" in panels
    assert "mutatesBadge" in panels


def test_confirm_includes_action_method_and_resolved_paths() -> None:
    chrome = (REPO_ROOT / "ui" / "modules" / "chrome.js").read_text(encoding="utf-8")

    assert "action" in chrome
    assert "method" in chrome
    assert "resolved path" in chrome
    assert "mutatesBadge()" in chrome
