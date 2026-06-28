"""Self-contained SDT helpers for the drop-in UI bundle."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    location: str
    message: str


@dataclass(frozen=True)
class AddedNode:
    path: Path
    ordinal: str


class SdtWriteError(Exception):
    pass


def lint_tree(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    tables: dict[Path, dict[str, list[str]]] = {}
    root = root.resolve()

    for directory in _walk_dirs(root):
        table, table_findings = _load_c(root, directory)
        tables[directory] = table
        findings.extend(table_findings)

    for directory, table in tables.items():
        for name in table:
            kind, detail = _resolve(root, directory, [name], tables, set())
            location = f"{_rel(root, directory)}:{name}"
            if kind == "dangling":
                findings.append(Finding("error", "dangling-target", location, detail))
            elif kind == "cycle":
                findings.append(Finding("error", "name-cycle", location, detail))
            elif kind == "escape":
                findings.append(
                    Finding(
                        "warning",
                        "escape-target",
                        location,
                        f"resolves outside the root to {detail}",
                    )
                )
    return findings


def add_node(parent: Path, body: bytes, *, author: str | None = None) -> AddedNode:
    if not parent.is_dir():
        raise SdtWriteError(f"not a directory: {parent}")
    for _ in range(1000):
        ordinal = _next_ordinal(parent)
        node = parent / ordinal
        try:
            node.mkdir(mode=0o755)
        except FileExistsError:
            continue
        _write_new(node / "a", body)
        _write_new(node / "b", _provenance(parent, ordinal, author).encode())
        return AddedNode(node, ordinal)
    raise SdtWriteError(f"could not allocate a child under {parent}")


def _walk_dirs(root: Path) -> list[Path]:
    return [Path(dirpath).resolve() for dirpath, _, _ in os.walk(root)]


def _load_c(root: Path, directory: Path) -> tuple[dict[str, list[str]], list[Finding]]:
    c_file = directory / "c"
    table: dict[str, list[str]] = {}
    findings: list[Finding] = []
    if not c_file.is_file():
        return table, findings
    for lineno, raw in enumerate(
        c_file.read_text(encoding="utf-8", errors="replace").splitlines(),
        1,
    ):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) < 2:
            findings.append(
                Finding(
                    "warning",
                    "c-malformed-line",
                    f"{c_file}:{lineno}",
                    f"naming entry needs a name and at least one target: {raw!r}",
                )
            )
            continue
        if parts[0] in table:
            findings.append(
                Finding(
                    "info",
                    "c-duplicate-name",
                    f"{c_file}:{lineno}",
                    f"duplicate name {parts[0]!r}; last definition wins",
                )
            )
        table[parts[0]] = parts[1:]
    return table, findings


def _resolve(
    root: Path,
    base: Path,
    parts: list[str],
    tables: dict[Path, dict[str, list[str]]],
    seen: set[tuple[Path, str]],
) -> tuple[str, str]:
    current = base
    for part in parts:
        child = current / part
        if child.exists():
            resolved = child.resolve()
            if not _under(root, resolved):
                return ("escape", str(resolved))
            current = resolved
            continue
        target = _nearest_name(root, current, part, tables)
        if target is None:
            return ("dangling", f"unknown name {part!r} under {_rel(root, current)}")
        defining_dir, target_text = target
        state = (defining_dir, part)
        if state in seen:
            return ("cycle", f"{part} -> {target_text}")
        base_dir = root if target_text.startswith("/") else defining_dir
        target_parts = [p for p in target_text.strip("/").split("/") if p]
        kind, detail = _resolve(root, base_dir, target_parts, tables, seen | {state})
        if kind != "ok":
            return (kind, detail)
        current = Path(detail)
    return ("ok", str(current))


def _nearest_name(
    root: Path,
    current: Path,
    name: str,
    tables: dict[Path, dict[str, list[str]]],
) -> tuple[Path, str] | None:
    chain = [root, *current.resolve().relative_to(root).parents]
    dirs = []
    cursor = root
    dirs.append(cursor)
    try:
        for part in current.resolve().relative_to(root).parts:
            cursor = cursor / part
            dirs.append(cursor.resolve())
    except ValueError:
        dirs = chain
    for directory in reversed(dirs):
        targets = tables.get(directory, {}).get(name)
        if targets:
            return directory, targets[-1]
    return None


def _next_ordinal(parent: Path) -> str:
    ordinals = [
        int(p.name) for p in parent.iterdir() if p.is_dir() and p.name.isdecimal()
    ]
    return str(max(ordinals) + 1 if ordinals else 0)


def _write_new(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "wb") as f:
        f.write(data)


def _provenance(parent: Path, ordinal: str, author: str | None) -> str:
    payload = {
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "parent": str(parent),
        "ordinal": ordinal,
    }
    if author:
        payload["author"] = author
    return json.dumps(payload, sort_keys=True) + "\n"


def _under(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix() or "."
    except ValueError:
        return str(path)
