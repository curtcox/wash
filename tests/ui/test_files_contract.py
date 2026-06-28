"""Files browser contracts for Phase 2."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


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
