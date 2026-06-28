"""Autocomplete contracts for the UI path box."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_path_box_has_datalist_autocomplete() -> None:
    html = (REPO_ROOT / "ui" / "index.html").read_text(encoding="utf-8")

    assert 'list="path-options"' in html
    assert 'id="path-options"' in html


def test_app_populates_autocomplete_from_commands_and_names() -> None:
    app = (REPO_ROOT / "ui" / "app.js").read_text(encoding="utf-8")

    assert "populateAutocomplete" in app
    assert "commands.commands" in app
    assert "names.findings" in app
    assert 'document.createElement("option")' in app
