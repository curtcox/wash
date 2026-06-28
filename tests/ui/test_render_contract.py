"""Renderer contracts for runtime diagnostics."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_renderer_has_error_diagnostic_path() -> None:
    render = (REPO_ROOT / "ui" / "modules" / "render.js").read_text(encoding="utf-8")
    api = (REPO_ROOT / "ui" / "modules" / "api.js").read_text(encoding="utf-8")

    assert 'Accept: "application/json' in api
    assert "resource.ok" in render
    assert "renderErrorDiagnostic" in render
    assert "exit_status" in render
    assert "pipeline" in render
