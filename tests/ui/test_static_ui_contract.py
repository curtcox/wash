"""Static contracts for the zero-build UI shell."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_shell_contains_backing_files_panel() -> None:
    html = (REPO_ROOT / "ui" / "index.html").read_text(encoding="utf-8")

    assert "Backing Files" in html
    assert 'id="backing-panel"' in html


def test_app_populates_backing_files_from_response_headers() -> None:
    app = (REPO_ROOT / "ui" / "app.js").read_text(encoding="utf-8")

    assert "backing-panel" in app
    assert "backingFilesFromHeaders" in app
    assert "No backing files reported" in app
    assert "resolved path" in app
