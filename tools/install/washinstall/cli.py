"""Command-line interface for `wash install` (specs/command_install.md).

Subcommands:
  add <name>     wire a host command into a root (default action)
  list           list installer-managed commands in a root
  remove <name>  remove an installer-managed command
  search <query> search the bundled registry
  info <name>    show a registry entry
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from washinstall import __version__
from washinstall.registry import Registry, load_meta_hints, load_registry
from washinstall.wire import (
    DEFAULT_BIN_DIR,
    InstallError,
    install,
    list_installed,
    remove,
)


def _parse_meta(pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise InstallError(f"--meta expects FIELD=VALUE, got: {pair!r}")
        key, value = pair.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def _cmd_add(args: argparse.Namespace, registry: Registry) -> int:
    root = Path(args.root)
    if not root.is_dir():
        print(f"error: root is not a directory: {root}", file=sys.stderr)
        return 2

    overrides = _parse_meta(args.meta or [])
    hints = load_meta_hints()
    try:
        result = install(
            root,
            args.name,
            from_path=args.from_path,
            bin_dir=args.bin_dir,
            meta_overrides=overrides,
            hints=hints,
            use_hints=not args.no_meta,
            force=args.force,
        )
    except InstallError as exc:
        # When the host command is simply missing, offer a registry suggestion
        # without running any package manager ([CI-4]).
        if "not found on host PATH" in str(exc) and args.from_path is None:
            return _suggest(args.name, registry)
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"installed {result.name} -> {result.host}  (origin: {result.origin})")
    print(f"  wrapper: {result.wrapper}")
    if result.meta is not None:
        print(f"  metadata: {result.meta}")
    if result.path_updated:
        print(f"  added {args.bin_dir!r} to {root / 'env' / 'path'}")
    return 0


def _suggest(name: str, registry: Registry) -> int:
    entry = registry.lookup(name)
    if entry is None:
        print(
            f"error: command not found on host PATH and not in the registry: {name}\n"
            f"  hint: install it on the host, then `wash install add {name}`,\n"
            f"        or point at a path with `wash install add {name} --from /path/to/{name}`.",
            file=sys.stderr,
        )
        return 1
    hint = entry.install_hint()
    print(
        f"error: {name} is not installed on the host.\n"
        f"  registry: {entry.name}  [role: {entry.role}, group: {entry.group}]",
        file=sys.stderr,
    )
    if hint:
        print(f"  install it with:  {hint}", file=sys.stderr)
    print(f"  then re-run:      wash install add {name}", file=sys.stderr)
    return 1


def _cmd_list(args: argparse.Namespace, registry: Registry) -> int:
    root = Path(args.root)
    if not root.is_dir():
        print(f"error: root is not a directory: {root}", file=sys.stderr)
        return 2
    commands = list_installed(root)
    if not commands:
        print("(no installer-managed commands)")
        return 0
    width = max(len(c.name) for c in commands)
    for c in commands:
        status = "ok" if c.host_ok else "MISSING"
        print(f"{c.name:<{width}}  {status:<7}  {c.host}")
    return 0


def _cmd_remove(args: argparse.Namespace, registry: Registry) -> int:
    root = Path(args.root)
    try:
        removed = remove(root, args.name, bin_dir=args.bin_dir)
    except InstallError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for p in removed:
        print(f"removed {p}")
    return 0


def _cmd_search(args: argparse.Namespace, registry: Registry) -> int:
    hits = registry.search(args.query)
    if not hits:
        print(f"(no registry entries matching {args.query!r})")
        return 1
    for e in hits:
        hint = e.install_hint() or "—"
        print(f"{e.name}  [role: {e.role}, group: {e.group}, avail: {e.avail}]")
        print(f"    {e.when}")
        print(f"    install: {hint}")
    return 0


def _cmd_info(args: argparse.Namespace, registry: Registry) -> int:
    entry = registry.lookup(args.name)
    if entry is None:
        print(f"(no registry entry for {args.name!r})", file=sys.stderr)
        return 1
    print(f"name:    {entry.name}")
    print(f"role:    {entry.role}")
    print(f"group:   {entry.group}")
    print(f"avail:   {entry.avail}")
    print(f"install: {entry.install_hint() or '—'}")
    print(f"when:    {entry.when}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="wash-install",
        description="Install host-OS commands into a wash root.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="wire a host command into a root")
    add.add_argument("name", help="wash command name to install")
    add.add_argument("--root", default=".", help="target wash root (default: .)")
    add.add_argument(
        "--from",
        dest="from_path",
        help="explicit host path to the command (overrides PATH lookup)",
    )
    add.add_argument(
        "--bin-dir",
        default=DEFAULT_BIN_DIR,
        help=f"command directory under the root (default: {DEFAULT_BIN_DIR})",
    )
    add.add_argument(
        "--meta",
        action="append",
        metavar="FIELD=VALUE",
        help="explicit command metadata field (repeatable)",
    )
    add.add_argument(
        "--no-meta",
        action="store_true",
        help="do not write metadata from the hints overlay",
    )
    add.add_argument(
        "--force", action="store_true", help="overwrite an existing command"
    )
    add.set_defaults(func=_cmd_add)

    lst = sub.add_parser("list", help="list installer-managed commands in a root")
    lst.add_argument("--root", default=".", help="target wash root (default: .)")
    lst.set_defaults(func=_cmd_list)

    rm = sub.add_parser("remove", help="remove an installer-managed command")
    rm.add_argument("name", help="wash command name to remove")
    rm.add_argument("--root", default=".", help="target wash root (default: .)")
    rm.add_argument("--bin-dir", default=DEFAULT_BIN_DIR, help="command directory")
    rm.set_defaults(func=_cmd_remove)

    sch = sub.add_parser("search", help="search the bundled registry")
    sch.add_argument("query", help="substring to match in name/role/when")
    sch.set_defaults(func=_cmd_search)

    info = sub.add_parser("info", help="show a registry entry")
    info.add_argument("name", help="command name to look up")
    info.set_defaults(func=_cmd_info)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    registry = load_registry()
    try:
        return args.func(args, registry)
    except InstallError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
