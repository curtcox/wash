"""Result model and JSON/JUnit/human reporters."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from conformance.spec import CLAUSE_REGISTRY, spec_label


class Outcome(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    WARN = "WARN"
    UNTESTED = "UNTESTED"
    TIMEOUT = "TIMEOUT"
    LAUNCH_FAILURE = "LAUNCH_FAILURE"
    PROCESS_DIED = "PROCESS_DIED"


@dataclass
class HttpSnapshot:
    status: int | None = None
    headers: dict[str, list[str]] = field(default_factory=dict)
    body: bytes = b""
    body_text: str | None = None
    transport_error: str | None = None
    elapsed_ms: float | None = None


@dataclass
class TestRecord:
    impl: str
    root: str
    vector_id: str
    clauses: list[str]
    tier: str
    outcome: Outcome
    reason: str = ""
    request_method: str = ""
    request_target: str = ""
    expected_summary: str = ""
    actual: HttpSnapshot | None = None
    diff: str = ""
    child_output: str = ""
    timing_ms: float | None = None
    tree_diff: str = ""


@dataclass
class RunReport:
    spec: str
    started_at: str
    finished_at: str
    records: list[TestRecord] = field(default_factory=list)
    impl_caps: dict[str, dict[str, Any]] = field(default_factory=dict)

    def summary_counts(self, impl: str | None = None) -> dict[str, int]:
        counts: dict[str, int] = {o.value: 0 for o in Outcome}
        for rec in self.records:
            if impl and rec.impl != impl:
                continue
            counts[rec.outcome.value] += 1
        return counts

    def gate_failed(self, *, strict: bool = False) -> bool:
        for rec in self.records:
            if rec.outcome in {Outcome.LAUNCH_FAILURE, Outcome.PROCESS_DIED}:
                return True
            if rec.tier == "MUST" and rec.outcome == Outcome.FAIL:
                return True
            if rec.tier == "MUST" and rec.outcome == Outcome.UNTESTED:
                return True
            if (
                strict
                and rec.tier == "SHOULD"
                and rec.outcome in {Outcome.FAIL, Outcome.WARN}
            ):
                return True
        return False


def new_report() -> RunReport:
    now = datetime.now(timezone.utc).isoformat()
    return RunReport(spec=spec_label(), started_at=now, finished_at=now)


def finalize_report(report: RunReport) -> RunReport:
    report.finished_at = datetime.now(timezone.utc).isoformat()
    return report


def record_to_dict(rec: TestRecord) -> dict[str, Any]:
    d = asdict(rec)
    d["outcome"] = rec.outcome.value
    if rec.actual:
        d["actual"] = {
            "status": rec.actual.status,
            "headers": rec.actual.headers,
            "body_base64": _b64(rec.actual.body) if rec.actual.body else "",
            "transport_error": rec.actual.transport_error,
            "elapsed_ms": rec.actual.elapsed_ms,
        }
    return d


def write_json(report: RunReport, path: str | Path) -> None:
    path = Path(path)
    payload = {
        "spec": report.spec,
        "started_at": report.started_at,
        "finished_at": report.finished_at,
        "impl_caps": report.impl_caps,
        "records": [record_to_dict(r) for r in report.records],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_junit(report: RunReport, path: str | Path) -> None:
    path = Path(path)
    suites: dict[str, ET.Element] = {}
    for rec in report.records:
        suite_name = rec.impl
        if suite_name not in suites:
            suites[suite_name] = ET.Element("testsuite", name=suite_name)
        case_name = f"{rec.impl}/{','.join(rec.clauses)}/{rec.vector_id}"
        case = ET.SubElement(
            suites[suite_name],
            "testcase",
            classname=rec.root,
            name=case_name,
            time=str((rec.timing_ms or 0) / 1000.0),
        )
        if rec.outcome == Outcome.PASS:
            continue
        if rec.outcome == Outcome.SKIP:
            ET.SubElement(case, "skipped", message=rec.reason)
        elif rec.outcome == Outcome.UNTESTED:
            ET.SubElement(case, "skipped", message=f"UNTESTED: {rec.reason}")
        elif rec.outcome in {Outcome.LAUNCH_FAILURE, Outcome.PROCESS_DIED}:
            err = ET.SubElement(case, "error", message=rec.outcome.value)
            err.text = rec.reason + (
                "\n" + rec.child_output if rec.child_output else ""
            )
        elif rec.outcome == Outcome.TIMEOUT:
            ET.SubElement(case, "error", message="TIMEOUT", type=rec.reason)
        elif rec.outcome == Outcome.WARN:
            fail = ET.SubElement(case, "failure", message="WARN", type="SHOULD")
            fail.text = rec.diff or rec.reason
        else:
            fail = ET.SubElement(case, "failure", message=rec.outcome.value)
            fail.text = rec.diff or rec.reason

    root = ET.Element("testsuites")
    for suite in suites.values():
        root.append(suite)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="unicode", xml_declaration=True)


def write_human(report: RunReport, *, max_failures: int = 20) -> str:
    lines: list[str] = []
    lines.append(f"wash conformance — {report.spec}")
    lines.append(f"started: {report.started_at}")
    lines.append("")

    impls = sorted({r.impl for r in report.records})
    for impl in impls:
        counts = report.summary_counts(impl)
        lines.append(f"=== {impl} ===")
        for tier in ("MUST", "SHOULD", "optional"):
            tier_recs = [r for r in report.records if r.impl == impl and r.tier == tier]
            if not tier_recs:
                continue
            passed = sum(1 for r in tier_recs if r.outcome == Outcome.PASS)
            lines.append(f"  {tier}: {passed}/{len(tier_recs)} pass")
        for outcome in Outcome:
            if counts[outcome.value]:
                lines.append(f"  {outcome.value}: {counts[outcome.value]}")
        lines.append("")

        failures = [
            r
            for r in report.records
            if r.impl == impl
            and r.outcome
            in {
                Outcome.FAIL,
                Outcome.WARN,
                Outcome.LAUNCH_FAILURE,
                Outcome.PROCESS_DIED,
            }
        ][:max_failures]
        for rec in failures:
            clause_txt = ", ".join(rec.clauses)
            lines.append(f"  [{rec.outcome.value}] {rec.vector_id} ({clause_txt})")
            lines.append(f"    {rec.request_method} {rec.request_target}")
            if rec.reason:
                lines.append(f"    reason: {rec.reason}")
            if rec.diff:
                lines.append(f"    diff: {rec.diff}")
            if rec.tree_diff:
                lines.append(f"    tree: {rec.tree_diff}")
        lines.append("")

    return "\n".join(lines)


def write_matrix(report: RunReport, path: str | Path) -> None:
    """Markdown conformance matrix: implementations × clauses."""
    path = Path(path)
    impls = sorted({r.impl for r in report.records})
    clauses = sorted({c for r in report.records for c in r.clauses})

    def cell(impl: str, clause: str) -> str:
        recs = [r for r in report.records if r.impl == impl and clause in r.clauses]
        if not recs:
            return "–"
        if any(r.outcome == Outcome.FAIL for r in recs):
            return "✗"
        if any(r.outcome == Outcome.UNTESTED for r in recs):
            return "U"
        if all(
            r.outcome in {Outcome.PASS, Outcome.SKIP, Outcome.WARN, Outcome.TIMEOUT}
            for r in recs
        ):
            if any(r.outcome == Outcome.WARN for r in recs):
                return "~"
            if any(r.outcome == Outcome.SKIP for r in recs):
                return "–"
            return "✓"
        return "?"

    header = "| clause | " + " | ".join(impls) + " |"
    sep = "|---|" + "|".join(["---"] * len(impls)) + "|"
    rows = [header, sep]
    for clause in clauses:
        meta = CLAUSE_REGISTRY.get(clause)
        label = meta.source if meta else clause
        rows.append(
            f"| {clause} ({label}) | "
            + " | ".join(cell(i, clause) for i in impls)
            + " |"
        )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def coverage_report(vector_clauses: dict[str, list[str]]) -> dict[str, Any]:
    """Cross-reference clause registry with vector clause references."""
    covered: dict[str, int] = {cid: 0 for cid in CLAUSE_REGISTRY}
    for clauses in vector_clauses.values():
        for cid in clauses:
            if cid in covered:
                covered[cid] += 1

    must_missing = [
        cid
        for cid, clause in CLAUSE_REGISTRY.items()
        if clause.tier == "MUST" and covered[cid] == 0
    ]
    return {
        "spec": spec_label(),
        "covered": covered,
        "must_missing_vectors": must_missing,
        "must_coverage_pct": round(
            100.0
            * sum(
                1
                for c in CLAUSE_REGISTRY.values()
                if c.tier == "MUST" and covered[c.id] > 0
            )
            / max(1, sum(1 for c in CLAUSE_REGISTRY.values() if c.tier == "MUST")),
            1,
        ),
    }


def _b64(data: bytes) -> str:
    import base64

    return base64.b64encode(data).decode("ascii")
