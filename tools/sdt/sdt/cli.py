"""Command-line interface for the sdt tooling."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sdt.lint import Finding, has_errors, lint_tree


def _format_text(findings: list[Finding]) -> str:
    return "\n".join(
        f"{f.severity:7} {f.code:18} {f.location}: {f.message}" for f in findings
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sdt", description="Sequential Directory Tree tools"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser(
        "check", help="lint name resolution under a root (runtime.md §6.6)"
    )
    check.add_argument("root", help="SDT root directory")
    check.add_argument("--json", action="store_true", help="emit findings as JSON")
    args = parser.parse_args(argv)

    root = Path(args.root)
    if not root.is_dir():
        print(f"sdt: not a directory: {root}", file=sys.stderr)
        return 2

    findings = lint_tree(root)
    if args.json:
        print(json.dumps([f.__dict__ for f in findings], indent=2))
    else:
        if findings:
            print(_format_text(findings))
        errors = sum(1 for f in findings if f.severity == "error")
        warnings = sum(1 for f in findings if f.severity == "warning")
        print(f"\n{errors} error(s), {warnings} warning(s)")
    return 1 if has_errors(findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
