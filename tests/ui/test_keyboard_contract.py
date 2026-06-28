"""Keyboard shortcut contracts for the framed UI shell."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_keyboard_module_exports_shortcuts() -> None:
    keyboard = (REPO_ROOT / "ui" / "modules" / "keyboard.js").read_text(encoding="utf-8")
    app = (REPO_ROOT / "ui" / "app.js").read_text(encoding="utf-8")

    assert "bindKeyboardShortcuts" in keyboard
    assert "bindKeyboardShortcuts" in app
    assert "focusPath" in app
