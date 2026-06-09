"""Orchestration — impl × root × vector execution model."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from conformance.adapter import LaunchError, LaunchedServer, load_adapter, launch, shutdown
from conformance.capabilities import load_manifest
from conformance.compare import (
    compare_expectation,
    compare_head_pair,
    vector_runnable,
)
from conformance.httpclient import send
from conformance.report import HttpSnapshot, Outcome, RunReport, TestRecord, finalize_report, new_report
from conformance.capabilities import harness_dir
from conformance.rootcorpus import (
    MaterializedRoot,
    can_materialize_for_caps,
    cleanup,
    host_case_sensitive,
    materialize,
)
from conformance.spec import CLAUSE_REGISTRY, spec_label


def vectors_dir() -> Path:
    return harness_dir() / "conformance" / "vectors"


def load_vector_schema() -> dict[str, Any]:
    return json.loads((harness_dir() / "vector.schema.json").read_text(encoding="utf-8"))


def load_vectors(
    *,
    root: str | None = None,
    tier: str | None = None,
    clause: str | None = None,
) -> list[dict[str, Any]]:
    base = vectors_dir()
    vectors: list[dict[str, Any]] = []
    if not base.is_dir():
        return vectors
    schema = load_vector_schema()
    for path in sorted(base.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            continue
        for item in data:
            if not isinstance(item, dict):
                continue
            try:
                jsonschema.validate(item, schema)
            except jsonschema.ValidationError as exc:
                raise ValueError(f"{path}: {item.get('id')}: {exc.message}") from exc
            if root and item.get("root") != root:
                continue
            if tier and item.get("tier") != tier:
                continue
            if clause and clause not in item.get("clauses", []):
                continue
            item["_source"] = str(path)
            vectors.append(item)
    _validate_vector_refs(vectors)
    return vectors


def _validate_vector_refs(vectors: list[dict[str, Any]]) -> None:
    ids = {v["id"] for v in vectors}
    for v in vectors:
        for cid in v.get("clauses", []):
            if cid not in CLAUSE_REGISTRY:
                raise ValueError(f"vector {v['id']}: unknown clause {cid!r}")
        head_of = v.get("expect", {}).get("head_of")
        if head_of and head_of not in ids:
            raise ValueError(f"vector {v['id']}: head_of references missing {head_of!r}")


def validate_vectors() -> list[str]:
    errors: list[str] = []
    try:
        load_vectors()
    except Exception as exc:
        errors.append(str(exc))
    return errors


def isolation_groups(vectors: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group vectors: mutation/no_mutation vectors get isolated groups."""
    readonly: list[dict[str, Any]] = []
    groups: list[list[dict[str, Any]]] = []
    for v in vectors:
        expect = v.get("expect", {})
        if expect.get("no_mutation") or expect.get("mutation") or v["request"]["method"] in {
            "PUT",
            "DELETE",
            "POST",
        }:
            groups.append([v])
        else:
            readonly.append(v)
    if readonly:
        groups.insert(0, readonly)
    return groups


def run(
    adapter_paths: list[str | Path],
    *,
    root: str | None = None,
    tier: str | None = None,
    clause: str | None = None,
    per_request_timeout: float = 10.0,
    strict: bool = False,
) -> RunReport:
    report = new_report()
    report.spec = spec_label()
    vectors = load_vectors(root=root, tier=tier, clause=clause)
    vectors_by_id = {v["id"]: v for v in vectors}

    for adapter_path in adapter_paths:
        adapter = load_adapter(adapter_path)
        cap_path = adapter.repo_root / adapter.capabilities
        caps = load_manifest(cap_path) if adapter.capabilities else {}
        report.impl_caps[adapter.name] = caps

        roots_needed = sorted({v["root"] for v in vectors})
        for root_name in roots_needed:
            root_vectors = [v for v in vectors if v["root"] == root_name]
            mat_ok, mat_reason = can_materialize_for_caps(root_name, caps)
            case_ok = host_case_sensitive()

            for group in isolation_groups(root_vectors):
                materialized: MaterializedRoot | None = None
                server: LaunchedServer | None = None
                try:
                    materialized = materialize(root_name, caps=caps)
                    server = launch(adapter, root=str(materialized.path), caps=caps)
                except LaunchError as exc:
                    for v in group:
                        report.records.append(
                            _launch_failure_record(adapter.name, v, str(exc), exc.child_output)
                        )
                    if materialized:
                        cleanup(materialized)
                    continue
                except Exception as exc:
                    for v in group:
                        report.records.append(
                            _launch_failure_record(adapter.name, v, str(exc), "")
                        )
                    if materialized:
                        cleanup(materialized)
                    continue

                for vector in group:
                    if server and not server.is_alive():
                        report.records.append(
                            _process_died_record(adapter.name, vector, server.captured_output())
                        )
                        continue

                    runnable, skip_kind, reason = vector_runnable(
                        vector,
                        caps,
                        materializable=mat_ok,
                        materialize_reason=mat_reason,
                        host_case_ok=case_ok,
                    )
                    if not runnable:
                        outcome = Outcome.UNTESTED if skip_kind == "UNTESTED" else Outcome.SKIP
                        report.records.append(
                            TestRecord(
                                impl=adapter.name,
                                root=root_name,
                                vector_id=vector["id"],
                                clauses=vector.get("clauses", []),
                                tier=vector.get("tier", "optional"),
                                outcome=outcome,
                                reason=reason,
                                request_method=vector["request"]["method"],
                                request_target=vector["request"]["target"],
                            )
                        )
                        continue

                    before = materialized.snapshot_if_needed(vector) if materialized else None
                    timeout = float(vector.get("per_request_timeout", per_request_timeout))
                    actual = send(server.base_url, vector["request"], timeout=timeout)

                    if actual.transport_error and server and not server.is_alive():
                        report.records.append(
                            _process_died_record(
                                adapter.name, vector, server.captured_output(), actual
                            )
                        )
                        continue

                    after = materialized.snapshot_if_needed(vector) if materialized else None
                    outcome, diff = _score_vector(
                        vector, actual, caps, before, after, vectors_by_id, server, timeout
                    )
                    report.records.append(
                        TestRecord(
                            impl=adapter.name,
                            root=root_name,
                            vector_id=vector["id"],
                            clauses=vector.get("clauses", []),
                            tier=vector.get("tier", "optional"),
                            outcome=outcome,
                            reason=diff if outcome != Outcome.PASS else "",
                            diff=diff,
                            request_method=vector["request"]["method"],
                            request_target=vector["request"]["target"],
                            actual=actual,
                            timing_ms=actual.elapsed_ms,
                            tree_diff=_tree_diff_text(before, after),
                        )
                    )

                if server:
                    shutdown(server)
                if materialized:
                    cleanup(materialized)

    return finalize_report(report)


def _score_vector(
    vector: dict[str, Any],
    actual: HttpSnapshot,
    caps: dict[str, Any],
    before,
    after,
    vectors_by_id: dict[str, dict[str, Any]],
    server: LaunchedServer | None,
    timeout: float,
) -> tuple[Outcome, str]:
    if actual.transport_error == "timeout":
        means = vector.get("timeout_means", "fail")
        if means == "timeout":
            return Outcome.TIMEOUT, "request exceeded deadline"
        tier = vector.get("tier", "MUST")
        if tier == "SHOULD":
            return Outcome.WARN, "timeout on SHOULD vector"
        return Outcome.FAIL, "timeout — spec requires completion"

    expect = vector.get("expect", {})
    head_of = expect.get("head_of")
    failures = compare_expectation(expect, actual, caps=caps, before=before, after=after)

    if head_of and head_of in vectors_by_id:
        get_vec = vectors_by_id[head_of]
        get_actual = send(server.base_url, get_vec["request"], timeout=timeout) if server else actual
        failures.extend(
            compare_head_pair(expect, actual, get_actual, caps=caps)
        )

    if failures:
        tier = vector.get("tier", "MUST")
        if tier == "SHOULD":
            return Outcome.WARN, "; ".join(failures)
        if tier == "optional":
            return Outcome.FAIL, "; ".join(failures)
        return Outcome.FAIL, "; ".join(failures)
    return Outcome.PASS, ""


def _tree_diff_text(before, after) -> str:
    if before is None or after is None:
        return ""
    diff = before.diff(after)
    return ", ".join(diff[:10])


def _launch_failure_record(impl: str, vector: dict[str, Any], reason: str, child: str) -> TestRecord:
    return TestRecord(
        impl=impl,
        root=vector.get("root", ""),
        vector_id=vector["id"],
        clauses=vector.get("clauses", []),
        tier=vector.get("tier", "optional"),
        outcome=Outcome.LAUNCH_FAILURE,
        reason=reason,
        child_output=child,
        request_method=vector["request"]["method"],
        request_target=vector["request"]["target"],
    )


def _process_died_record(
    impl: str, vector: dict[str, Any], child: str, actual: HttpSnapshot | None = None
) -> TestRecord:
    reason = "server process exited"
    if actual and actual.transport_error:
        reason += f": {actual.transport_error}"
    return TestRecord(
        impl=impl,
        root=vector.get("root", ""),
        vector_id=vector["id"],
        clauses=vector.get("clauses", []),
        tier=vector.get("tier", "optional"),
        outcome=Outcome.PROCESS_DIED,
        reason=reason,
        child_output=child,
        request_method=vector["request"]["method"],
        request_target=vector["request"]["target"],
        actual=actual,
    )


def vector_clause_map() -> dict[str, list[str]]:
    return {v["id"]: v.get("clauses", []) for v in load_vectors()}
