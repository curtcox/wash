"""Phase 5 packaging contracts: install, manifest, posture, self-protection."""

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


def test_manifest_lists_bundle_paths() -> None:
    manifest = (REPO_ROOT / "ui" / ".ui-manifest").read_text(encoding="utf-8")
    required = [
        "ui/index.html",
        "ui/app.js",
        "ui/modules/keyboard.js",
        "bin/ui",
        "bin/wash-ui-install",
        "env/path",
        "exec",
    ]
    for rel in required:
        assert rel in manifest


def test_recovery_documents_redrop_and_curl_floor() -> None:
    recovery = (REPO_ROOT / "ui" / "RECOVERY.md").read_text(encoding="utf-8")

    assert "wash-ui-install" in recovery
    assert "curl" in recovery


def test_shell_contains_posture_and_integrity_banners() -> None:
    html = (REPO_ROOT / "ui" / "index.html").read_text(encoding="utf-8")

    assert 'id="posture-banner"' in html
    assert 'id="integrity-banner"' in html


def test_integrity_module_exports_phase5_helpers() -> None:
    integrity = (REPO_ROOT / "ui" / "modules" / "integrity.js").read_text(
        encoding="utf-8"
    )
    app = (REPO_ROOT / "ui" / "app.js").read_text(encoding="utf-8")
    chrome = (REPO_ROOT / "ui" / "modules" / "chrome.js").read_text(encoding="utf-8")

    assert "isNonLocalOrigin" in integrity
    assert "bundlePathWarning" in integrity
    assert "loadManifest" in integrity
    assert "renderPostureBanner" in chrome
    assert "renderIntegrityBanner" in chrome
    assert "loadManifest" in app
    assert "bundlePathWarning" in app


def test_is_non_local_origin_heuristic() -> None:
    payload = _node_eval(
        textwrap.dedent(
            """
            import { isNonLocalOrigin } from './ui/modules/integrity.js';
            console.log(JSON.stringify({
              local: isNonLocalOrigin('http://127.0.0.1:8080'),
              remote: isNonLocalOrigin('http://example.com:8080'),
            }));
            """
        )
    )

    assert payload["local"] is False
    assert payload["remote"] is True


def test_bundle_path_warning_matches_manifest_entries() -> None:
    payload = _node_eval(
        textwrap.dedent(
            """
            import { bundlePathWarning, isBundlePath } from './ui/modules/integrity.js';
            const manifest = ['ui/app.js', 'bin/ui'];
            console.log(JSON.stringify({
              ui: isBundlePath('/ui/app.js', manifest),
              other: isBundlePath('/notes.txt', manifest),
              warning: bundlePathWarning('/bin/ui', manifest),
            }));
            """
        )
    )

    assert payload["ui"] is True
    assert payload["other"] is False
    assert payload["warning"] is not None
    assert "RECOVERY.md" in payload["warning"]


def test_wash_ui_install_aborts_on_conflict(tmp_path: Path) -> None:
    target = tmp_path / "root"
    target.mkdir()
    installer = REPO_ROOT / "bin" / "wash-ui-install"
    subprocess.run([str(installer), str(target)], check=True)
    (target / "bin" / "ui").write_text("#!/bin/sh\necho conflict\n", encoding="utf-8")

    result = subprocess.run(
        [str(installer), str(target)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert result.returncode == 1
    assert "conflicts:" in result.stderr
    assert "bin/ui" in result.stderr


def test_layout_supports_large_screen_breakpoint() -> None:
    css = (REPO_ROOT / "ui" / "style.css").read_text(encoding="utf-8")

    assert "min-width: 1400px" in css
    assert "28vw" in css
