"""Contract tests for the bundled wash UI helper commands."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_helper(name: str, root: Path, *args: str, stdin: bytes = b"") -> dict:
    proc = subprocess.run(
        [str(REPO_ROOT / "bin" / name), *args],
        cwd=root,
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return json.loads(proc.stdout)


def _write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_names_reports_sdt_linter_findings(tmp_path: Path) -> None:
    outside = tmp_path.parent / "wash-ui-outside.txt"
    outside.write_text("secret", encoding="utf-8")
    _write(tmp_path, "ok/a", "ok\n")
    _write(
        tmp_path,
        "c",
        "\n".join(
            [
                "good /ok/a",
                "gone /missing",
                "loopa loopb",
                "loopb loopa",
                f"escape ../{outside.name}",
                "badline",
            ]
        )
        + "\n",
    )

    payload = _run_helper("names", tmp_path)

    codes = {finding["code"] for finding in payload["findings"]}
    assert {
        "dangling-target",
        "name-cycle",
        "escape-target",
        "c-malformed-line",
    } <= codes
    severities = {
        finding["code"]: finding["severity"] for finding in payload["findings"]
    }
    assert severities["dangling-target"] == "error"
    assert severities["escape-target"] == "warning"


def test_names_reports_winning_targets(tmp_path: Path) -> None:
    _write(tmp_path, "0/a", "zero\n")
    _write(tmp_path, "1/a", "one\n")
    _write(tmp_path, "c", "topic /0/a\ntopic /1/a\n")

    payload = _run_helper("names", tmp_path)

    assert payload["names"] == [
        {
            "scope": ".",
            "name": "topic",
            "target": "/1/a",
            "winner": True,
            "inert": False,
        }
    ]


def test_explain_classifies_command_args_and_input(tmp_path: Path) -> None:
    _write(tmp_path, "env/path", "bin\n")
    _write(tmp_path, "env/meta/grep", "arity 1\nmime text/plain\n")
    _write(tmp_path, "bin/grep", "#!/bin/sh\n")
    _write(tmp_path, "data.txt", "needle\n")

    payload = _run_helper("explain", tmp_path, "grep/needle/data.txt")

    assert payload["target"] == "grep/needle/data.txt"
    assert payload["effective_pipeline"] == "cat data.txt | grep needle"
    assert [segment["role"] for segment in payload["segments"]] == [
        "command",
        "arg",
        "input",
    ]
    assert payload["segments"][0]["metadata"]["arity"] == 1


def test_append_emits_created_node_manifest_and_writes_provenance(
    tmp_path: Path,
) -> None:
    payload = _run_helper("append", tmp_path, ".", stdin=b"hello\n")

    node = tmp_path / "0"
    assert payload["manifest"] == "Created Node"
    assert payload["location"] == "/0"
    assert payload["created"] == "0"
    assert (node / "a").read_bytes() == b"hello\n"
    provenance = json.loads((node / "b").read_text(encoding="utf-8"))
    assert provenance["ordinal"] == "0"
    assert provenance["parent"] == str(tmp_path)


def test_search_finds_needle_in_a_files(tmp_path: Path) -> None:
    _write(tmp_path, "0/a", "alpha beta\n")
    _write(tmp_path, "1/a", "gamma\n")

    payload = _run_helper("search", tmp_path, "beta")

    assert payload["query"] == "beta"
    assert any(match["path"] == "0/a" for match in payload["matches"])


def test_concurrent_append_allocates_unique_ordinals(tmp_path: Path) -> None:
    append = REPO_ROOT / "bin" / "append"
    procs = [
        subprocess.Popen(
            [str(append), "."],
            cwd=tmp_path,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(8)
    ]
    payloads = []
    for index, proc in enumerate(procs):
        assert proc.stdin is not None
        proc.stdin.write(f"turn-{index}\n".encode())
        proc.stdin.close()
        stdout, stderr = proc.communicate(timeout=10)
        assert proc.returncode == 0, stderr.decode("utf-8")
        payloads.append(json.loads(stdout))

    ordinals = {payload["created"] for payload in payloads}
    assert len(ordinals) == len(procs)
    for ordinal in ordinals:
        assert (tmp_path / ordinal / "a").is_file()


def test_installed_bundle_helpers_are_self_contained(tmp_path: Path) -> None:
    target = tmp_path / "root"
    target.mkdir()
    subprocess.run(
        [str(REPO_ROOT / "bin" / "wash-ui-install"), str(target)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _write(target, "ok/a", "ok\n")
    _write(target, "c", "gone /missing\n")

    names = subprocess.run(
        [str(target / "bin" / "names")],
        cwd=target,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    append = subprocess.run(
        [str(target / "bin" / "append"), "."],
        cwd=target,
        input=b"installed\n",
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert "dangling-target" in names.stdout.decode("utf-8")
    assert json.loads(append.stdout)["manifest"] == "Created Node"
    assert (target / "0" / "a").read_bytes() == b"installed\n"
