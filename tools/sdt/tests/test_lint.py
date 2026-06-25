"""Tests for the sdt name-resolution linter."""

from __future__ import annotations

from pathlib import Path

from sdt.lint import has_errors, lint_tree


def _codes(findings: list) -> set[str]:
    return {f.code for f in findings}


def _write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_clean_tree_has_no_findings(tmp_path: Path) -> None:
    _write(tmp_path, "0/a", "zero\n")
    _write(tmp_path, "1/a", "one\n")
    _write(tmp_path, "c", "greeting /0/a\nother /1/a\n")
    findings = lint_tree(tmp_path)
    assert findings == []
    assert not has_errors(findings)


def test_dangling_target_is_error(tmp_path: Path) -> None:
    _write(tmp_path, "c", "gone /nope/missing\n")
    findings = lint_tree(tmp_path)
    assert "dangling-target" in _codes(findings)
    assert has_errors(findings)


def test_cycle_is_error(tmp_path: Path) -> None:
    _write(tmp_path, "c", "a b\nb a\n")
    findings = lint_tree(tmp_path)
    assert "name-cycle" in _codes(findings)
    assert has_errors(findings)


def test_escape_is_warning_not_error(tmp_path: Path) -> None:
    _write(tmp_path, "0/a", "zero\n")
    # outside-root target that exists, so it is an escape (not a dangling miss)
    (tmp_path.parent / "secret.txt").write_text("x", encoding="utf-8")
    _write(tmp_path, "c", "escape ../secret.txt\n")
    findings = lint_tree(tmp_path)
    assert "escape-target" in _codes(findings)
    assert not has_errors(findings)


def test_escape_without_existing_target_still_flagged(tmp_path: Path) -> None:
    # A target that lexically leaves the root is an escape regardless of existence.
    _write(tmp_path, "c", "escape ../nonexistent.txt\n")
    findings = lint_tree(tmp_path)
    assert "escape-target" in _codes(findings)


def test_malformed_c_line_is_warning(tmp_path: Path) -> None:
    _write(tmp_path, "c", "lonelyname\n")
    findings = lint_tree(tmp_path)
    assert "c-malformed-line" in _codes(findings)
    assert not has_errors(findings)


def test_chaining_resolves_clean(tmp_path: Path) -> None:
    _write(tmp_path, "1/a", "one\n")
    _write(tmp_path, "c", "chain hop\nhop /1/a\n")
    findings = lint_tree(tmp_path)
    assert findings == []


def test_nested_scope_shadowing_is_clean(tmp_path: Path) -> None:
    _write(tmp_path, "0/0/a", "deep\n")
    _write(tmp_path, "0/a", "shallow\n")
    _write(tmp_path, "c", "greeting /0/a\n")
    _write(tmp_path, "0/c", "greeting /0/0/a\n")
    findings = lint_tree(tmp_path)
    assert findings == []


def test_corpus_names_root_findings() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    names_root = repo_root / "harness" / "roots" / "names"
    if not names_root.is_dir():
        return  # corpus not present in this checkout
    findings = lint_tree(names_root)
    codes = _codes(findings)
    # The fixture deliberately includes a cycle, a dangling target, and an escape.
    assert "name-cycle" in codes
    assert "dangling-target" in codes
    assert "escape-target" in codes
    assert has_errors(findings)
