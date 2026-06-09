"""Harness self-tests."""

from __future__ import annotations

import ast
from pathlib import Path

from conformance import pytest_plugin as _pytest_plugin

test_httpclient_self_test = _pytest_plugin.test_httpclient_self_test
test_validate_roots_corpus = _pytest_plugin.test_validate_roots_corpus
test_validate_vectors_schema = _pytest_plugin.test_validate_vectors_schema


def test_conformance_package_does_not_import_reference_wash() -> None:
    harness_root = Path(__file__).resolve().parent.parent
    violations: list[str] = []

    for path in sorted((harness_root / "conformance").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue

            if any(name == "wash" or name.startswith("wash.") for name in names):
                violations.append(f"{path.relative_to(harness_root)}:{node.lineno}")

    assert violations == []
