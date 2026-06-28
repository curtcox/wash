"""Renderer contracts for content-type matrix and escape hatches."""

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


def test_renderer_has_error_diagnostic_path() -> None:
    render = (REPO_ROOT / "ui" / "modules" / "render.js").read_text(encoding="utf-8")
    api = (REPO_ROOT / "ui" / "modules" / "api.js").read_text(encoding="utf-8")

    assert 'Accept: "application/json' in api
    assert "resource.ok" in render
    assert "renderErrorDiagnostic" in render
    assert "exit_status" in render
    assert "pipeline" in render


def test_renderer_supports_markdown_and_escape_hatches() -> None:
    render = (REPO_ROOT / "ui" / "modules" / "render.js").read_text(encoding="utf-8")
    markdown = (REPO_ROOT / "ui" / "vendor" / "markdown.js").read_text(encoding="utf-8")

    for name in (
        "renderMarkdown",
        "renderEscapeBar",
        "renderMarkdownToHtml",
        "View raw",
        "Download",
    ):
        assert name in render or name in markdown


def test_markdown_vendor_renders_basic_markdown() -> None:
    payload = _node_eval(
        textwrap.dedent(
            """
            import { renderMarkdownToHtml } from './ui/vendor/markdown.js';
            console.log(JSON.stringify({
              html: renderMarkdownToHtml('# Title\\n\\nHello **world**.'),
            }));
            """
        )
    )

    assert "<h1>Title</h1>" in payload["html"]
    assert "<strong>world</strong>" in payload["html"]


def test_api_exports_feature_probe() -> None:
    api = (REPO_ROOT / "ui" / "modules" / "api.js").read_text(encoding="utf-8")
    app = (REPO_ROOT / "ui" / "app.js").read_text(encoding="utf-8")

    assert "probeFeatures" in api
    assert "probeFeatures" in app
    assert "executionHeaders" in api
