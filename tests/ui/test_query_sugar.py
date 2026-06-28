"""Query sugar contracts for the UI path box."""

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


def test_query_sugar_canonicalizes_to_arg_query_url() -> None:
    payload = _node_eval(
        textwrap.dedent(
            """
            import { canonicalizeInput } from './ui/modules/router.js';
            console.log(JSON.stringify({
              canonical: canonicalizeInput('/grep?-i "two words"/jq?.items[]/data.json')
            }));
            """
        )
    )

    assert (
        payload["canonical"]
        == "/grep?arg=-i&arg=two%20words/jq?arg=.items%5B%5D/data.json"
    )


def test_query_sugar_preserves_named_params_and_decodes_for_display() -> None:
    payload = _node_eval(
        textwrap.dedent(
            """
            import { canonicalizeInput, displayInput } from './ui/modules/router.js';
            const canonical = canonicalizeInput('/cmd?mode=fast bare "two words"');
            console.log(JSON.stringify({
              canonical,
              display: displayInput(canonical)
            }));
            """
        )
    )

    assert payload["canonical"] == "/cmd?mode=fast&arg=bare&arg=two%20words"
    assert payload["display"] == '/cmd?mode=fast bare "two words"'


def test_shell_contains_decode_preview() -> None:
    html = (REPO_ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    app = (REPO_ROOT / "ui" / "app.js").read_text(encoding="utf-8")

    assert 'id="canonical-preview"' in html
    assert "canonicalizeInput" in app
    assert "updatePreview" in app
