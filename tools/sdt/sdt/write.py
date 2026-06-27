"""Write helpers for Sequential Directory Trees."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path


class SdtWriteError(Exception):
    """A user-facing SDT write failure."""


@dataclass(frozen=True)
class AddedNode:
    path: Path
    ordinal: str


def next_ordinal(parent: Path) -> str:
    """Return the next numeric child name under ``parent``."""
    if not parent.is_dir():
        raise SdtWriteError(f"not a directory: {parent}")
    highest = -1
    for entry in parent.iterdir():
        if entry.is_dir() and entry.name.isdecimal():
            highest = max(highest, int(entry.name))
    return str(highest + 1)


def add_node(parent: Path, body: bytes, *, author: str | None = None) -> AddedNode:
    """Atomically allocate a child ordinal and write its ``a`` and ``b`` files."""
    if not parent.is_dir():
        raise SdtWriteError(f"not a directory: {parent}")

    for _ in range(1000):
        ordinal = next_ordinal(parent)
        node = parent / ordinal
        try:
            node.mkdir(mode=0o755)
        except FileExistsError:
            continue
        try:
            _write_new(node / "a", body)
            _write_new(node / "b", _provenance(parent, ordinal, author).encode())
        except Exception:
            for child in (node / "b", node / "a"):
                try:
                    child.unlink()
                except FileNotFoundError:
                    pass
            try:
                node.rmdir()
            except OSError:
                pass
            raise
        return AddedNode(path=node, ordinal=ordinal)

    raise SdtWriteError(f"could not allocate a child under {parent}")


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
