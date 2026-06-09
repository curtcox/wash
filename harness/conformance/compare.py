"""Vector expectation matching — all matchers from PLAN §7.1."""

from __future__ import annotations

import base64
import json
import re
from typing import Any

from conformance.capabilities import (
    check_error_body_cap,
    forbidden_when,
    get_path_value,
    requires_capability,
)
from conformance.report import HttpSnapshot
from conformance.rootcorpus import TreeSnapshot


def select_expect(
    expect: dict[str, Any],
    caps: dict[str, Any],
) -> dict[str, Any]:
    """Resolve policy branches and one_of before matching."""
    branch = dict(expect)
    if not caps.get("writes_enabled", True) and "when_writes_disabled" in branch:
        branch = {**branch.pop("when_writes_disabled")}
    elif not caps.get("deletes_enabled", True) and "when_deletes_disabled" in branch:
        branch = {**branch.pop("when_deletes_disabled")}
    branch.pop("when_writes_disabled", None)
    branch.pop("when_deletes_disabled", None)
    return branch


def compare_expectation(
    expect: dict[str, Any],
    actual: HttpSnapshot,
    *,
    caps: dict[str, Any] | None = None,
    before: TreeSnapshot | None = None,
    after: TreeSnapshot | None = None,
) -> list[str]:
    caps = caps or {}
    expect = select_expect(expect, caps)
    failures: list[str] = []

    if "one_of" in expect:
        branches = expect["one_of"]
        branch_errors = []
        for branch in branches:
            errs = compare_expectation(branch, actual, caps=caps, before=before, after=after)
            if not errs:
                return []
            branch_errors.append("; ".join(errs))
        failures.append("one_of: no branch matched: " + " | ".join(branch_errors))
        return failures

    if actual.transport_error:
        failures.append(f"transport error: {actual.transport_error}")
        return failures

    if actual.status is None:
        failures.append("no HTTP status received")
        return failures

    failures.extend(_match_status(expect, actual.status))
    failures.extend(_match_body(expect, actual))
    failures.extend(_match_headers(expect, actual))
    failures.extend(_match_content_type(expect, actual, caps))
    failures.extend(_match_tree(expect, before, after))
    failures.extend(_match_pipeline_header(expect, actual, caps))
    failures.extend(_match_error_body(expect, actual))
    failures.extend(_check_error_cap(actual, caps))

    return failures


def _match_status(expect: dict[str, Any], status: int) -> list[str]:
    failures: list[str] = []
    if "status" in expect and status != expect["status"]:
        failures.append(f"status: expected {expect['status']}, got {status}")
    if "status_any" in expect and status not in expect["status_any"]:
        failures.append(f"status_any: {status} not in {expect['status_any']}")
    if "status_class" in expect:
        cls = expect["status_class"]
        ok = (
            (cls == "success" and 200 <= status < 300)
            or (cls == "non_error" and 200 <= status < 400)
            or (cls == "client_error" and 400 <= status < 500)
            or (cls == "server_error" and 500 <= status < 600)
        )
        if not ok:
            failures.append(f"status_class {cls}: got {status}")
    return failures


def _match_body(expect: dict[str, Any], actual: HttpSnapshot) -> list[str]:
    failures: list[str] = []
    body = actual.body

    if expect.get("body_empty"):
        if body:
            failures.append(f"body_empty: got {len(body)} bytes")
        return failures

    if "body_exact" in expect:
        want = expect["body_exact"].encode("utf-8")
        if body != want:
            failures.append(f"body_exact mismatch ({len(body)} vs {len(want)} bytes)")
    if "body_contains" in expect:
        needle = expect["body_contains"].encode("utf-8")
        if needle not in body:
            failures.append(f"body_contains missing: {expect['body_contains']!r}")
    if "body_not_contains" in expect:
        needle = expect["body_not_contains"].encode("utf-8")
        if needle in body:
            failures.append(f"body_not_contains found: {expect['body_not_contains']!r}")
    if "body_matches" in expect:
        text = body.decode("utf-8", errors="replace")
        if not re.search(expect["body_matches"], text):
            failures.append(f"body_matches failed: /{expect['body_matches']}/")
    if "body_base64" in expect:
        want = base64.b64decode(expect["body_base64"])
        if body != want:
            failures.append("body_base64 mismatch")
    return failures


def _match_headers(expect: dict[str, Any], actual: HttpSnapshot) -> list[str]:
    failures: list[str] = []
    headers = actual.headers

    for name, value in expect.get("header", {}).items():
        key = name.lower()
        got = headers.get(key)
        if isinstance(value, list):
            if got != value:
                failures.append(f"header {name}: expected {value!r}, got {got!r}")
        else:
            if not got or len(got) != 1 or got[0] != value:
                failures.append(f"header {name}: expected {value!r}, got {got!r}")

    for name in expect.get("header_present", []):
        if name.lower() not in headers:
            failures.append(f"header_present missing: {name}")

    for name in expect.get("header_absent", []):
        if name.lower() in headers:
            failures.append(f"header_absent present: {name}")

    for name, pattern in expect.get("header_matches", {}).items():
        key = name.lower()
        vals = headers.get(key, [])
        if not vals or not any(re.search(pattern, v) for v in vals):
            failures.append(f"header_matches {name}: /{pattern}/ not matched")

    return failures


def _match_content_type(
    expect: dict[str, Any], actual: HttpSnapshot, caps: dict[str, Any]
) -> list[str]:
    if "content_type" not in expect:
        return []
    mime = caps.get("mime", {})
    if mime.get("inference") == "none":
        return []
    want = expect["content_type"]
    got = actual.headers.get("content-type", [""])[0].split(";")[0].strip()
    if got != want:
        return [f"content_type: expected {want!r}, got {got!r}"]
    return []


def _match_tree(
    expect: dict[str, Any],
    before: TreeSnapshot | None,
    after: TreeSnapshot | None,
) -> list[str]:
    failures: list[str] = []
    if expect.get("no_mutation"):
        if before is None or after is None:
            failures.append("no_mutation requires before/after snapshots")
        else:
            diff = before.diff(after)
            if diff:
                failures.append("no_mutation violated: " + ", ".join(diff[:5]))
    if "mutation" in expect:
        mut = expect["mutation"]
        if before is None or after is None:
            failures.append("mutation requires before/after snapshots")
        else:
            path = mut["path"]
            action = mut["action"]
            if action == "deleted":
                if path in after.entries:
                    failures.append(f"mutation delete: {path} still exists")
            else:
                entry = after.entries.get(path)
                if not entry or entry.get("type") != "file":
                    failures.append(f"mutation {action}: {path} missing")
                elif "bytes" in mut:
                    want = mut["bytes"].encode("utf-8")
                    if entry.get("bytes") != want:
                        failures.append(f"mutation bytes mismatch for {path}")
                elif "bytes_base64" in mut:
                    want = base64.b64decode(mut["bytes_base64"])
                    if entry.get("bytes") != want:
                        failures.append(f"mutation bytes_base64 mismatch for {path}")
    return failures


def _match_pipeline_header(
    expect: dict[str, Any], actual: HttpSnapshot, caps: dict[str, Any]
) -> list[str]:
    if "pipeline_header" not in expect:
        return []
    if not caps.get("execution_metadata_headers"):
        return []
    want = expect["pipeline_header"]
    got = actual.headers.get("x-webshell-pipeline", [])
    if not got or got[0] != want:
        return [f"pipeline_header: expected {want!r}, got {got!r}"]
    return []


def _match_error_body(expect: dict[str, Any], actual: HttpSnapshot) -> list[str]:
    spec = expect.get("error_body")
    if not spec:
        return []
    failures: list[str] = []
    body_text = actual.body.decode("utf-8", errors="replace")
    try:
        doc = json.loads(body_text)
    except json.JSONDecodeError:
        for needle in spec.get("contains", []):
            if needle not in body_text:
                failures.append(f"error_body contains missing: {needle!r}")
        return failures
    for field in spec.get("field_present", []):
        if field not in doc:
            failures.append(f"error_body field_present missing: {field}")
    for needle in spec.get("contains", []):
        if needle not in body_text:
            failures.append(f"error_body contains missing: {needle!r}")
    return failures


def _check_error_cap(actual: HttpSnapshot, caps: dict[str, Any]) -> list[str]:
    if actual.status is None:
        return []
    msg = check_error_body_cap(caps, actual.status, actual.body)
    return [msg] if msg else []


def vector_runnable(
    vector: dict[str, Any],
    caps: dict[str, Any],
    *,
    materializable: bool,
    materialize_reason: str = "",
    host_case_ok: bool = True,
) -> tuple[bool, str, str]:
    """Return (runnable, skip_kind, reason). skip_kind is '' | 'SKIP' | 'UNTESTED'."""
    if vector.get("forbidden_when"):
        bad, reason = forbidden_when(caps, vector["forbidden_when"])
        if bad:
            return False, "SKIP", reason

    gate = vector.get("requires_capability")
    if gate is not None:
        ok, reason = requires_capability(caps, gate)
        if not ok:
            tier = vector.get("tier", "optional")
            kind = "UNTESTED" if tier == "MUST" else "SKIP"
            return False, kind, reason

    req_interp = vector.get("requires_interpreter")
    if req_interp:
        if req_interp not in caps.get("interpreters", []):
            tier = vector.get("tier", "optional")
            kind = "UNTESTED" if tier == "MUST" else "SKIP"
            return False, kind, f"requires_interpreter {req_interp!r} not declared"

    if vector.get("root") == "case" and not host_case_ok:
        return False, "SKIP", "case-insensitive host filesystem"

    if not materializable:
        tier = vector.get("tier", "optional")
        kind = "UNTESTED" if tier == "MUST" else "SKIP"
        return False, kind, materialize_reason

    return True, "", ""


def compare_head_pair(
    head_expect: dict[str, Any],
    head_actual: HttpSnapshot,
    get_actual: HttpSnapshot,
    *,
    caps: dict[str, Any] | None = None,
) -> list[str]:
    failures: list[str] = []
    if get_actual.status != head_actual.status:
        failures.append(
            f"head_of status: GET {get_actual.status} vs HEAD {head_actual.status}"
        )
    head_branch = select_expect(head_expect, caps or {})
    failures.extend(_match_body({"body_empty": True}, head_actual))
    for name, value in head_branch.get("header", {}).items():
        key = name.lower()
        gvals = get_actual.headers.get(key, [])
        hvals = head_actual.headers.get(key, [])
        if gvals and hvals:
            if isinstance(value, list):
                if hvals != value:
                    failures.append(f"head header {name} mismatch")
            elif hvals != [value] and gvals == [value]:
                failures.append(f"head header {name}: expected {value!r}, got {hvals!r}")
    if "content-length" in {h.lower() for h in head_branch.get("header_present", [])}:
        if "content-length" not in head_actual.headers:
            failures.append("head Content-Length not present")
    return failures
