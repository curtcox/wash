"""Command-line interface for the sdt tooling."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sdt.lint import Finding, has_errors, lint_tree
from sdt.write import SdtWriteError, add_node, next_ordinal


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
    name = sub.add_parser("name", help="print the next child ordinal for a node")
    name.add_argument("parent", help="parent SDT directory")
    add = sub.add_parser("add", help="atomically append a child node")
    add.add_argument("parent", help="parent SDT directory")
    add.add_argument(
        "--body-file",
        help="read the node body from this file instead of stdin",
    )
    add.add_argument("--author", help="optional author stored in b provenance")
    add.add_argument("--json", action="store_true", help="emit created node as JSON")
    args = parser.parse_args(argv)

    if args.command == "name":
        parent = Path(args.parent)
        try:
            print(next_ordinal(parent))
        except SdtWriteError as exc:
            print(f"sdt: {exc}", file=sys.stderr)
            return 2
        return 0

    if args.command == "add":
        parent = Path(args.parent)
        try:
            body = (
                Path(args.body_file).read_bytes()
                if args.body_file is not None
                else sys.stdin.buffer.read()
            )
            created = add_node(parent, body, author=args.author)
        except (OSError, SdtWriteError) as exc:
            print(f"sdt: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(
                json.dumps(
                    {"path": str(created.path), "ordinal": created.ordinal},
                    indent=2,
                )
            )
        else:
            print(created.path)
        return 0

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
