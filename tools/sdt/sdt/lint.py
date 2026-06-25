"""Static linter for SDT name resolution (runtime.md §6.6).

The runtime resolves names per request under a bounded depth budget; the linter
does the exhaustive whole-tree analysis the runtime cannot afford: it detects
every cycle and dangling target across the combined name+symlink graph, and
inventories every target that leaves the root. Cycles and dangling targets are
hard errors; escapes and malformed `c` lines are reported, not failed (matching
the policy in runtime.md §6.6.3/§6.6.4).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

MAX_DEPTH = 40

ERROR = "error"
WARNING = "warning"
INFO = "info"


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    location: str
    message: str


# A resolution result is a (kind, detail) pair where kind is one of
# "ok" | "dangling" | "escape" | "cycle".
_Result = tuple[str, str]


def _under(root: Path, path: Path) -> bool:
    root_s = os.path.normpath(str(root))
    path_s = os.path.normpath(str(path))
    return path_s == root_s or path_s.startswith(root_s + os.sep)


def _rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix() or "."
    except ValueError:
        return str(path)


def _load_c(directory: Path) -> tuple[dict[str, list[str]], list[Finding]]:
    findings: list[Finding] = []
    c_file = directory / "c"
    table: dict[str, list[str]] = {}
    if not c_file.is_file():
        return table, findings
    try:
        text = c_file.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return table, [Finding(WARNING, "c-unreadable", str(c_file), str(exc))]
    for lineno, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        tokens = stripped.split()
        if len(tokens) < 2:
            findings.append(
                Finding(
                    WARNING,
                    "c-malformed-line",
                    f"{c_file}:{lineno}",
                    f"naming entry needs a name and at least one target: {raw!r}",
                )
            )
            continue
        name = tokens[0]
        if name in table:
            findings.append(
                Finding(
                    INFO,
                    "c-duplicate-name",
                    f"{c_file}:{lineno}",
                    f"duplicate name {name!r}; last definition wins",
                )
            )
        table[name] = tokens[1:]
    return table, findings


def _scope_chain(
    root: Path, node: Path, tables: dict[Path, dict[str, list[str]]]
) -> list[tuple[Path, dict[str, list[str]]]]:
    chain: list[tuple[Path, dict[str, list[str]]]] = [(root, tables.get(root, {}))]
    try:
        rel = node.resolve().relative_to(root)
    except ValueError:
        return chain
    current = root
    for part in rel.parts:
        current = (current / part).resolve()
        if current.is_dir():
            chain.append((current, tables.get(current, {})))
    return chain


def _target_base_parts(
    root: Path, defining_dir: Path, target: str
) -> tuple[Path, list[str]]:
    if target.startswith("/"):
        return root, [p for p in target.lstrip("/").split("/") if p]
    return defining_dir, [p for p in target.split("/") if p and p != "."]


def _resolve(
    root: Path,
    base: Path,
    parts: list[str],
    tables: dict[Path, dict[str, list[str]]],
    visiting: frozenset[tuple[str, tuple[str, ...]]],
    depth: int,
) -> _Result:
    current = base
    i = 0
    while i < len(parts):
        if depth > MAX_DEPTH:
            return ("cycle", "maximum resolution depth exceeded")
        if not current.is_dir():
            return ("dangling", f"{_rel(root, current)} is not a directory")
        part = parts[i]
        child = current / part
        if child.is_symlink():
            try:
                resolved = child.resolve()
            except OSError:
                return ("dangling", f"broken symlink {_rel(root, child)}")
            if not _under(root, resolved):
                return ("escape", str(resolved))
            current = resolved
            i += 1
            continue
        if child.exists():
            current = child.resolve()
            i += 1
            continue

        chain = _scope_chain(root, current, tables)
        matched: tuple[Path, list[str]] | None = None
        for defining_dir, table in reversed(chain):
            if part in table:
                matched = (defining_dir, table[part])
                break
        if matched is None:
            return ("dangling", f"unknown name {part!r} under {_rel(root, current)}")

        defining_dir, targets = matched
        resolved_node: Path | None = None
        last_fail: _Result | None = None
        for target in targets:
            t_base, t_parts = _target_base_parts(root, defining_dir, target)
            dest = t_base.joinpath(*t_parts).resolve() if t_parts else t_base.resolve()
            if not _under(root, dest):
                return ("escape", str(dest))
            state = (str(t_base.resolve()), tuple(t_parts))
            if state in visiting:
                return ("cycle", f"{part} -> {target}")
            sub = _resolve(root, t_base, t_parts, tables, visiting | {state}, depth + 1)
            if sub[0] == "dangling":
                last_fail = sub
                continue
            if sub[0] in ("escape", "cycle"):
                return sub
            resolved_node = Path(sub[1])
            break
        if resolved_node is None:
            return last_fail or ("dangling", f"name {part!r} has no resolvable target")
        current = resolved_node
        i += 1
    return ("ok", str(current))


def lint_tree(root: Path) -> list[Finding]:
    """Lint every name entry reachable under ``root``."""
    root = root.resolve()
    findings: list[Finding] = []
    tables: dict[Path, dict[str, list[str]]] = {}

    for dirpath, _dirnames, filenames in os.walk(root):
        directory = Path(dirpath).resolve()
        if "c" in filenames:
            table, file_findings = _load_c(directory)
            tables[directory] = table
            findings.extend(file_findings)
        else:
            tables[directory] = {}

    for directory, table in sorted(tables.items()):
        for name in sorted(table):
            seed = frozenset({(str(directory), (name,))})
            kind, detail = _resolve(root, directory, [name], tables, seed, 0)
            location = f"{_rel(root, directory)}:{name}"
            if kind == "dangling":
                findings.append(Finding(ERROR, "dangling-target", location, detail))
            elif kind == "cycle":
                findings.append(Finding(ERROR, "name-cycle", location, detail))
            elif kind == "escape":
                findings.append(
                    Finding(
                        WARNING,
                        "escape-target",
                        location,
                        f"resolves outside the root to {detail}",
                    )
                )

    return findings


def has_errors(findings: list[Finding]) -> bool:
    return any(f.severity == ERROR for f in findings)
