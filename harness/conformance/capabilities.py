"""Capability manifest loading, validation, and predicate evaluation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import jsonschema

from conformance.spec import SPEC_VERSION

_SCHEMA: dict[str, Any] | None = None

LOOPBACK_HOSTS = frozenset(
    {
        "127.0.0.1",
        "::1",
        "localhost",
        "[::1]",
    }
)


def harness_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def schema_path() -> Path:
    return harness_dir() / "capabilities.schema.json"


def load_schema() -> dict[str, Any]:
    global _SCHEMA
    if _SCHEMA is None:
        _SCHEMA = json.loads(schema_path().read_text(encoding="utf-8"))
    return _SCHEMA


def load_manifest(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_manifest(data, path=path)
    return data


def validate_manifest(data: dict[str, Any], *, path: Path | None = None) -> list[str]:
    """Validate manifest against JSON Schema and additional harness rules."""
    errors: list[str] = []
    try:
        jsonschema.validate(data, load_schema())
    except jsonschema.ValidationError as exc:
        loc = ".".join(str(p) for p in exc.absolute_path) or "<root>"
        errors.append(f"{path or 'manifest'}: {loc}: {exc.message}")
        return errors

    if data.get("spec_version") != SPEC_VERSION:
        errors.append(
            f"spec_version {data.get('spec_version')!r} != harness SPEC_VERSION {SPEC_VERSION!r}"
        )

    origin_errors = _validate_origin_form(data.get("origin_form", ""))
    errors.extend(origin_errors)

    for name in data.get("default_index_files", []):
        if not _is_safe_filename(name):
            errors.append(f"unsafe default_index_files entry: {name!r}")

    for rel in data.get("runtime_artifact_paths", []):
        if not _is_root_relative_path(rel):
            errors.append(f"unsafe runtime_artifact_paths entry: {rel!r}")

    return errors


def _validate_origin_form(origin_form: str) -> list[str]:
    errors: list[str] = []
    parsed = urlparse(origin_form)
    if parsed.scheme != "http":
        errors.append("origin_form must use http scheme")
    if parsed.path or parsed.query or parsed.fragment or parsed.params:
        errors.append("origin_form must not contain path, query, or fragment")
    if parsed.username or parsed.password:
        errors.append("origin_form must not contain userinfo")
    if parsed.port is not None:
        errors.append("origin_form must not embed a port")
    host = parsed.hostname or ""
    if not host or host not in LOOPBACK_HOSTS:
        errors.append(f"origin_form host must be a loopback literal/name, got {host!r}")
    return errors


def _is_safe_filename(name: str) -> bool:
    if not name or name in {".", ".."}:
        return False
    if "/" in name or "\\" in name:
        return False
    if any(ord(c) < 32 or ord(c) == 127 for c in name):
        return False
    return True


def _is_root_relative_path(path: str) -> bool:
    if not path or path.startswith(("/", "\\")):
        return False
    if "\\" in path:
        return False
    if any(ord(c) < 32 or ord(c) == 127 for c in path):
        return False
    for part in path.split("/"):
        if part in {"", ".", ".."}:
            return False
    return True


def get_path_value(manifest: dict[str, Any], dotted: str) -> Any:
    cur: Any = manifest
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def evaluate_predicate(manifest: dict[str, Any], predicate: Any) -> tuple[bool, str]:
    """Evaluate a capability predicate. Returns (result, explanation)."""
    if isinstance(predicate, str):
        val = get_path_value(manifest, predicate)
        ok = bool(val)
        return ok, f"{predicate} is {val!r}"

    if not isinstance(predicate, dict):
        return False, f"invalid predicate type: {type(predicate).__name__}"

    if "all" in predicate:
        parts = predicate["all"]
        reasons = []
        for p in parts:
            ok, reason = evaluate_predicate(manifest, p)
            if not ok:
                reasons.append(reason)
        if reasons:
            return False, "all failed: " + "; ".join(reasons)
        return True, "all predicates satisfied"

    if "any" in predicate:
        parts = predicate["any"]
        reasons = []
        for p in parts:
            ok, reason = evaluate_predicate(manifest, p)
            if ok:
                return True, reason
            reasons.append(reason)
        return False, "any failed: " + "; ".join(reasons)

    path = predicate.get("path", "")
    value = get_path_value(manifest, path)

    if "equals" in predicate:
        expected = predicate["equals"]
        ok = value == expected
        return ok, f"{path} == {expected!r} (got {value!r})"

    if "not_equals" in predicate:
        expected = predicate["not_equals"]
        ok = value != expected
        return ok, f"{path} != {expected!r} (got {value!r})"

    if predicate.get("present"):
        ok = value is not None
        return ok, f"{path} present ({value!r})"

    if predicate.get("absent"):
        ok = value is None
        return ok, f"{path} absent"

    if predicate.get("nonempty"):
        ok = bool(value) and (
            (isinstance(value, (list, dict, str)) and len(value) > 0)
            or not isinstance(value, (list, dict, str))
        )
        return ok, f"{path} nonempty ({value!r})"

    if "contains" in predicate:
        needle = predicate["contains"]
        if isinstance(value, list):
            ok = needle in value
        elif isinstance(value, dict):
            ok = needle in value.values() or needle in value
        elif isinstance(value, str):
            ok = needle in value
        else:
            ok = False
        return ok, f"{path} contains {needle!r}"

    if "matches_key" in predicate:
        key = predicate["matches_key"]
        ok = isinstance(value, dict) and key in value
        return ok, f"{path} has key {key!r}"

    return False, f"unknown predicate operator in {predicate!r}"


def requires_capability(
    manifest: dict[str, Any], gate: str | dict[str, Any] | None
) -> tuple[bool, str]:
    if gate is None:
        return True, "no capability gate"
    ok, reason = evaluate_predicate(manifest, gate)
    return ok, reason


def forbidden_when(
    manifest: dict[str, Any], gate: dict[str, Any] | None
) -> tuple[bool, str]:
    if gate is None:
        return False, "no forbidden_when gate"
    ok, reason = evaluate_predicate(manifest, gate)
    return ok, f"forbidden_when: {reason}"


def foreign_origin(manifest: dict[str, Any]) -> str:
    return manifest.get("cross_origin_probe", "http://cross-origin.invalid")


def origin_host(manifest: dict[str, Any]) -> str:
    parsed = urlparse(manifest["origin_form"])
    return parsed.hostname or "127.0.0.1"


def max_error_body_bytes(manifest: dict[str, Any]) -> int:
    return int(manifest.get("max_error_body_bytes", 8192))


def check_error_body_cap(manifest: dict[str, Any], status: int, body: bytes) -> str | None:
    """SHOULD-tier check against declared max_error_body_bytes."""
    if 400 <= status < 600 and body and len(body) > max_error_body_bytes(manifest):
        return (
            f"error body {len(body)} bytes exceeds declared max "
            f"{max_error_body_bytes(manifest)}"
        )
    return None
