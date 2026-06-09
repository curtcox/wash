"""wash-conformance CLI entry point."""

from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

from conformance.capabilities import load_manifest, validate_manifest
from conformance.httpclient import self_test
from conformance.report import coverage_report, write_human, write_json, write_junit, write_matrix
from conformance.rootcorpus import validate_roots
from conformance.runner import load_vectors, run, validate_vectors, vector_clause_map
from conformance.spec import spec_label


def _expand_adapters(patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        matches = glob.glob(pattern)
        if not matches:
            paths.append(Path(pattern))
        else:
            paths.extend(Path(m) for m in sorted(matches))
    return paths


def cmd_run(args: argparse.Namespace) -> int:
    adapters = _expand_adapters(args.adapter)
    report = run(
        adapters,
        root=args.root,
        tier=args.tier,
        clause=args.clause,
        per_request_timeout=args.timeout,
        strict=args.strict,
    )
    if args.json:
        write_json(report, args.json)
    if args.junit:
        write_junit(report, args.junit)
    if args.matrix:
        write_matrix(report, args.matrix)
    print(write_human(report))
    return 1 if report.gate_failed(strict=args.strict) else 0


def cmd_validate_roots(args: argparse.Namespace) -> int:
    errors = validate_roots(interpreter=args.interpreter)
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1
    print("validate-roots: OK")
    return 0


def cmd_validate_vectors(args: argparse.Namespace) -> int:
    errors = validate_vectors()
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1
    vectors = load_vectors()
    print(f"validate-vectors: OK ({len(vectors)} vectors)")
    return 0


def cmd_validate_capabilities(args: argparse.Namespace) -> int:
    errors: list[str] = []
    for path in _expand_adapters(args.manifest):
        if not path.is_file():
            errors.append(f"not found: {path}")
            continue
        try:
            if args.load or path.suffix == ".json":
                data = load_manifest(path)
            else:
                from conformance.adapter import load_adapter

                adapter = load_adapter(path)
                cap_path = adapter.repo_root / adapter.capabilities
                data = load_manifest(cap_path)
        except Exception as exc:
            errors.append(f"{path}: {exc}")
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1
    print("validate-capabilities: OK")
    return 0


def cmd_coverage(args: argparse.Namespace) -> int:
    report = coverage_report(vector_clause_map())
    print(f"spec: {report['spec']}")
    print(f"MUST clause coverage: {report['must_coverage_pct']}%")
    missing = report["must_missing_vectors"]
    if missing:
        print("MUST clauses with zero vectors:")
        for cid in missing:
            print(f"  - {cid}")
        return 1 if args.strict else 0
    print("All MUST clauses have ≥1 vector reference.")
    return 0


def cmd_self_test(_: argparse.Namespace) -> int:
    errors = self_test()
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1
    print("httpclient self-test: OK")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wash-conformance", description="wash conformance harness")
    parser.add_argument("--strict", action="store_true", help="Treat SHOULD failures as gate failures")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run conformance vectors against adapter(s)")
    run_p.add_argument("--adapter", action="append", required=True, help="Adapter manifest TOML")
    run_p.add_argument("--root", help="Filter by root name")
    run_p.add_argument("--tier", choices=["MUST", "SHOULD", "optional"])
    run_p.add_argument("--clause", help="Filter by clause id")
    run_p.add_argument("--timeout", type=float, default=10.0, help="Per-request timeout seconds")
    run_p.add_argument("--json", help="Write JSON report path")
    run_p.add_argument("--junit", help="Write JUnit XML path")
    run_p.add_argument("--matrix", help="Write markdown matrix path")
    run_p.set_defaults(func=cmd_run)

    vr = sub.add_parser("validate-roots", help="Validate root corpus invariants")
    vr.add_argument("--interpreter", help="Also validate substituted interpreter form")
    vr.set_defaults(func=cmd_validate_roots)

    vv = sub.add_parser("validate-vectors", help="Validate YAML vectors against schema")
    vv.set_defaults(func=cmd_validate_vectors)

    vc = sub.add_parser("validate-capabilities", help="Validate capability manifest(s)")
    vc.add_argument("manifest", nargs="+", help="Capability JSON or adapter TOML with capabilities path")
    vc.add_argument("--load", action="store_true", help="Treat manifest args as capability JSON paths")
    vc.set_defaults(func=cmd_validate_capabilities)

    cov = sub.add_parser("coverage", help="Report clause coverage from vectors")
    cov.set_defaults(func=cmd_coverage)

    st = sub.add_parser("self-test-http", help="Run HTTP client loopback self-test")
    st.set_defaults(func=cmd_self_test)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
