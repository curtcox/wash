"""Collect everything the wash developer site needs into build/data.json.

Run from the repo root. This shells out to the same toolchain commands CI uses
(so the site never diverges from CI), runs the conformance harness once across
all adapters, derives language versions / external packages from each impl's
manifest, and computes simple code metrics. A failing toolchain step is recorded
(status ``fail`` with a log tail) rather than aborting the build — the site is a
report, not a gate.
"""

from __future__ import annotations

import json
import subprocess
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from conformance.report import coverage_report
from conformance.runner import vector_clause_map
from conformance.spec import CLAUSE_REGISTRY, SPEC_VERSION, spec_label

REPO = Path(__file__).resolve().parents[2]
BUILD = Path(__file__).resolve().parent / "build"
LOG_TAIL_LINES = 40
SOURCE_EXT = {
    ".py",
    ".go",
    ".dart",
    ".rs",
    ".rb",
    ".lua",
    ".pl",
    ".java",
    ".groovy",
    ".swift",
    ".sh",
    ".ts",
    ".js",
}


@dataclass
class Step:
    """One reported toolchain check, made of one or more commands run in order.

    All commands must succeed for the step to pass. ``cmds=None`` marks the step
    not-applicable (e.g. no compile step for an interpreted impl).
    """

    key: str  # compilation | linting | testing | static_analysis
    label: str
    cmds: list[list[str]] | None
    cwd: Path


def run_step(step: Step) -> dict[str, Any]:
    if step.cmds is None:
        return {
            "status": "n/a",
            "label": step.label,
            "cmd": "",
            "exit": None,
            "seconds": 0.0,
            "log_tail": "",
        }
    start = time.monotonic()
    logs: list[str] = []
    exit_code = 0
    for cmd in step.cmds:
        proc = subprocess.run(cmd, cwd=step.cwd, capture_output=True, text=True)
        logs.append(f"$ {' '.join(cmd)}")
        combined = (proc.stdout or "") + (proc.stderr or "")
        if combined.strip():
            logs.append(combined.rstrip())
        if proc.returncode != 0:
            exit_code = proc.returncode
            break
    seconds = round(time.monotonic() - start, 2)
    tail = "\n".join("\n".join(logs).splitlines()[-LOG_TAIL_LINES:])
    return {
        "status": "pass" if exit_code == 0 else "fail",
        "label": step.label,
        "cmd": " && ".join(" ".join(c) for c in step.cmds),
        "exit": exit_code,
        "seconds": seconds,
        "log_tail": tail,
    }


def tool_version(cmd: list[str]) -> str:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        out = (proc.stdout or proc.stderr or "").strip().splitlines()
        return out[0] if out else ""
    except FileNotFoundError:
        return "not found"


# ----- per-impl manifest derivation -------------------------------------------------


def reference_meta() -> dict[str, Any]:
    data = tomllib.loads((REPO / "impls/reference/pyproject.toml").read_text())
    proj = data.get("project", {})
    deps = proj.get("dependencies", [])
    return {
        "declared_version": proj.get("requires-python", ""),
        "toolchain_version": tool_version(["python3", "--version"]),
        "packages": deps,
        "dev_packages": [],
    }


def go_meta() -> dict[str, Any]:
    text = (REPO / "impls/go/go.mod").read_text()
    declared = ""
    requires: list[str] = []
    in_block = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("go "):
            declared = s.split(None, 1)[1]
        elif s.startswith("require ("):
            in_block = True
        elif in_block and s == ")":
            in_block = False
        elif in_block and s and not s.startswith("//"):
            requires.append(s)
        elif s.startswith("require ") and "(" not in s:
            requires.append(s[len("require ") :])
    return {
        "declared_version": declared,
        "toolchain_version": tool_version(["go", "version"]),
        "packages": requires,
        "dev_packages": [],
    }


def dart_meta() -> dict[str, Any]:
    text = (REPO / "impls/dart/pubspec.yaml").read_text()
    declared = ""
    deps: list[str] = []
    dev: list[str] = []
    section: str | None = None
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        key = line.strip().rstrip(":")
        if indent == 0:
            section = key.split(":")[0]
            if key.startswith("environment"):
                section = "environment"
            elif key.startswith("dependencies"):
                section = "dependencies"
            elif key.startswith("dev_dependencies"):
                section = "dev_dependencies"
            else:
                section = None
            continue
        name = line.strip().split(":")[0].strip()
        val = line.split(":", 1)[1].strip() if ":" in line else ""
        if section == "environment" and name == "sdk":
            declared = val.strip('"')
        elif section == "dependencies":
            deps.append(f"{name} {val}".strip())
        elif section == "dev_dependencies":
            dev.append(f"{name} {val}".strip())
    return {
        "declared_version": declared,
        "toolchain_version": tool_version(["dart", "--version"]),
        "packages": deps,
        "dev_packages": dev,
    }


# ----- per-impl step definitions ----------------------------------------------------

REF = REPO / "impls/reference"
GO = REPO / "impls/go"
DART = REPO / "impls/dart"

IMPLS: dict[str, dict[str, Any]] = {
    "reference": {
        "language": "Python",
        "dir": REF,
        "capabilities": REPO / "impls/reference/wash.capabilities.json",
        "meta": reference_meta,
        "steps": [
            Step("compilation", "interpreted — no compile step", None, REPO),
            Step(
                "linting",
                "ruff check + ruff format --check",
                [["ruff", "check", "wash"], ["ruff", "format", "--check", "wash"]],
                REF,
            ),
            Step(
                "testing",
                "pytest (harness self-tests)",
                [["python", "-m", "pytest", "-q"]],
                REPO / "harness",
            ),
            Step("static_analysis", "mypy", [["mypy", "wash"]], REF),
        ],
    },
    "go": {
        "language": "Go",
        "dir": GO,
        "capabilities": REPO / "impls/go/wash.capabilities.json",
        "meta": go_meta,
        "steps": [
            Step("compilation", "go build ./...", [["go", "build", "./..."]], GO),
            Step(
                "linting",
                "gofmt -l + go vet",
                [["sh", "-c", 'test -z "$(gofmt -l .)"'], ["go", "vet", "./..."]],
                GO,
            ),
            Step("testing", "go test ./...", [["go", "test", "./..."]], GO),
            Step("static_analysis", "go vet ./...", [["go", "vet", "./..."]], GO),
        ],
    },
    "dart": {
        "language": "Dart",
        "dir": DART,
        "capabilities": REPO / "impls/dart/wash.capabilities.json",
        "meta": dart_meta,
        "steps": [
            Step(
                "compilation",
                "dart compile exe",
                [
                    ["dart", "pub", "get"],
                    [
                        "dart",
                        "compile",
                        "exe",
                        "bin/wash_server.dart",
                        "-o",
                        "bin/wash-server",
                    ],
                ],
                DART,
            ),
            Step(
                "linting",
                "dart format --set-exit-if-changed",
                [["dart", "format", "--output=none", "--set-exit-if-changed", "."]],
                DART,
            ),
            Step("testing", "dart test", [["dart", "test"]], DART),
            Step("static_analysis", "dart analyze", [["dart", "analyze"]], DART),
        ],
    },
}


# ----- code metrics -----------------------------------------------------------------


def last_changed(path: Path) -> str:
    proc = subprocess.run(
        ["git", "log", "-1", "--format=%cI", "--", str(path.relative_to(REPO))],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


def code_metrics(impl_dir: Path) -> dict[str, Any]:
    files = 0
    total_lines = 0
    largest = {"path": "", "lines": 0}
    for p in sorted(impl_dir.rglob("*")):
        if not p.is_file() or p.suffix not in SOURCE_EXT:
            continue
        parts = set(p.relative_to(impl_dir).parts)
        if parts & {"bin", ".dart_tool", "build", ".git"}:
            continue
        try:
            lines = sum(1 for _ in p.open("rb"))
        except OSError:
            continue
        files += 1
        total_lines += lines
        if lines > largest["lines"]:
            largest = {"path": str(p.relative_to(REPO)), "lines": lines}
    return {
        "files": files,
        "lines_of_code": total_lines,
        "largest_file": largest,
        "last_changed": last_changed(impl_dir),
    }


# ----- conformance ------------------------------------------------------------------


def run_conformance() -> dict[str, Any]:
    out = BUILD / "conformance.json"
    subprocess.run(
        [
            "wash-conformance",
            "run",
            "--adapter",
            "harness/adapters/reference.toml",
            "--adapter",
            "harness/adapters/go.toml",
            "--adapter",
            "harness/adapters/dart.toml",
            "--json",
            str(out),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    return json.loads(out.read_text())


def summarize_conformance(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-impl tier counts and the list of failing vectors."""
    impls: dict[str, dict[str, Any]] = {}
    for rec in records:
        impl = rec["impl"]
        d = impls.setdefault(
            impl,
            {"MUST": [0, 0], "SHOULD": [0, 0], "optional": [0, 0], "failures": []},
        )
        tier = rec["tier"]
        if tier in d:
            d[tier][1] += 1
            if rec["outcome"] in {"PASS", "SKIP", "WARN", "TIMEOUT"}:
                d[tier][0] += 1
        if rec["outcome"] in {"FAIL", "LAUNCH_FAILURE", "PROCESS_DIED", "UNTESTED"}:
            d["failures"].append(
                {
                    "vector": rec["vector_id"],
                    "clauses": rec["clauses"],
                    "outcome": rec["outcome"],
                    "reason": rec.get("reason", ""),
                }
            )
    return impls


def clause_matrix(
    records: list[dict[str, Any]], impls: list[str]
) -> dict[str, dict[str, str]]:
    """clause id -> impl -> cell symbol, mirroring report.write_matrix semantics."""
    matrix: dict[str, dict[str, str]] = {}
    for cid in CLAUSE_REGISTRY:
        row: dict[str, str] = {}
        for impl in impls:
            recs = [r for r in records if r["impl"] == impl and cid in r["clauses"]]
            row[impl] = _cell(recs)
        matrix[cid] = row
    return matrix


def _cell(recs: list[dict[str, Any]]) -> str:
    if not recs:
        return "–"
    outcomes = {r["outcome"] for r in recs}
    if "FAIL" in outcomes or "LAUNCH_FAILURE" in outcomes or "PROCESS_DIED" in outcomes:
        return "✗"
    if "UNTESTED" in outcomes:
        return "U"
    if "WARN" in outcomes:
        return "~"
    if outcomes <= {"SKIP"}:
        return "–"
    return "✓"


# ----- main -------------------------------------------------------------------------


def main() -> None:
    BUILD.mkdir(parents=True, exist_ok=True)
    impl_names = list(IMPLS)

    # Run toolchain steps first: the compilation steps produce the Go/Dart server
    # binaries the conformance adapters launch.
    steps_by_impl: dict[str, dict[str, Any]] = {}
    for name, cfg in IMPLS.items():
        steps_by_impl[name] = {s.key: run_step(s) for s in cfg["steps"]}

    conf = run_conformance()
    records = conf["records"]
    conf_summary = summarize_conformance(records)

    impls_out: dict[str, Any] = {}
    for name, cfg in IMPLS.items():
        impls_out[name] = {
            "language": cfg["language"],
            "meta": cfg["meta"](),
            "capabilities": json.loads(Path(cfg["capabilities"]).read_text()),
            "steps": steps_by_impl[name],
            "metrics": code_metrics(cfg["dir"]),
            "conformance": conf_summary.get(name, {}),
        }

    cov = coverage_report(vector_clause_map())
    data = {
        "spec_label": spec_label(),
        "spec_version": SPEC_VERSION,
        "generated_at": conf.get("finished_at", ""),
        "commit": _git("rev-parse", "HEAD"),
        "commit_short": _git("rev-parse", "--short", "HEAD"),
        "repo_url": _repo_url(),
        "impls": impls_out,
        "matrix": clause_matrix(records, impl_names),
        "coverage": cov,
        "clauses": {
            cid: {"source": c.source, "tier": c.tier, "requirement": c.requirement}
            for cid, c in CLAUSE_REGISTRY.items()
        },
    }
    (BUILD / "data.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"wrote {BUILD / 'data.json'}")


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True
    ).stdout.strip()


def _repo_url() -> str:
    """Best-effort https URL for the repo, for linking unpublished repo paths."""
    remote = _git("remote", "get-url", "origin")
    if remote.startswith("git@github.com:"):
        remote = "https://github.com/" + remote[len("git@github.com:") :]
    if remote.endswith(".git"):
        remote = remote[: -len(".git")]
    return remote


if __name__ == "__main__":
    main()
