"""Filesystem resolution, serving, and mutation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import unquote_to_bytes

MIME_DEFAULT = "application/octet-stream"
FALLBACK_MIME_TABLE: dict[str, str] = {
    ".html": "text/html",
    ".htm": "text/html",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".json": "application/json",
    ".css": "text/css",
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".svg": "image/svg+xml",
    ".xml": "application/xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".pdf": "application/pdf",
    ".wasm": "application/wasm",
}
DEFAULT_INDEX_NAMES = ["index.html"]


class EnvConfigError(Exception):
    """A malformed root/env serving-config file (mime, index, listing)."""


class PathSegmentError(Exception):
    pass


class RootEscapeError(Exception):
    pass


class SymlinkEscapeError(Exception):
    pass


class NameEscapeError(Exception):
    """A c-file name resolved to a target outside the root under a reject policy."""


class NameLoopError(Exception):
    """Name/symlink resolution exceeded the shared depth budget (a cycle)."""


@dataclass
class FilesystemResource:
    kind: Literal["file", "directory"]
    path: Path
    rel_path: str
    via_indirection: bool = False


def split_raw_target(raw_target: str) -> list[str]:
    """Split request-target on raw / before percent-decoding."""
    if not raw_target.startswith("/"):
        raw_target = "/" + raw_target
    parts = raw_target.split("/")
    segments: list[str] = []
    for part in parts:
        if part == "" and not segments:
            continue
        if part == "":
            continue
        segments.append(part)
    return segments


def percent_decode_segment(raw: str, *, for_filesystem: bool) -> str:
    try:
        decoded = unquote_to_bytes(raw).decode("utf-8", errors="surrogateescape")
    except Exception as exc:
        raise PathSegmentError(str(exc)) from exc
    if for_filesystem and ("/" in decoded or "\x00" in decoded):
        raise PathSegmentError("decoded / or NUL in filesystem path segment")
    return decoded


def normalize_path_parts(parts: list[str]) -> list[str]:
    stack: list[str] = []
    for part in parts:
        if part in ("", "."):
            continue
        if part == "..":
            if stack:
                stack.pop()
            else:
                stack.append("..")
            continue
        stack.append(part)
    return stack


def _is_under_root(root: Path, path: Path) -> bool:
    root_s = os.path.normpath(str(root.resolve()))
    path_s = os.path.normpath(str(path.resolve()))
    return path_s == root_s or path_s.startswith(root_s + os.sep)


def load_name_table(directory: Path) -> dict[str, list[str]]:
    """Parse a directory's ``c`` naming file (runtime.md §6.6.1).

    Reuses the §5.5 metadata line grammar (comments/blanks ignored, whitespace
    tokens, last-occurrence-wins). Each entry is ``name target...``. An absent,
    empty, or malformed/non-naming file degrades to an empty table and never
    raises, so an ordinary file named ``c`` cannot break a root.
    """
    c_file = directory / "c"
    table: dict[str, list[str]] = {}
    if not c_file.is_file():
        return table
    try:
        lines = _env_config_lines(c_file)
    except OSError:
        return table
    for line in lines:
        tokens = line.split()
        if len(tokens) < 2:
            continue
        table[tokens[0]] = tokens[1:]
    return table


def _scope_for(root: Path, node: Path) -> list[tuple[Path, dict[str, list[str]]]]:
    """Scope chain of (dir, name-table) from root down to node, deepest last."""
    root = root.resolve()
    node = node.resolve()
    chain: list[tuple[Path, dict[str, list[str]]]] = [(root, load_name_table(root))]
    try:
        rel = node.relative_to(root)
    except ValueError:
        return chain
    current = root
    for part in rel.parts:
        current = current / part
        if current.is_dir():
            chain.append((current, load_name_table(current)))
    return chain


def _resolve_walk(
    root: Path,
    base: Path,
    base_scope: list[tuple[Path, dict[str, list[str]]]],
    parts: list[str],
    *,
    escape_policy: str,
    case_sensitive: bool,
    hops: list[int],
) -> Path | None:
    """Walk ``parts`` from ``base``, resolving names against the scope chain.

    A single escape_policy governs symlink and name target escapes alike
    (runtime.md §6.6.4): escapes are rejected unless the policy is ``follow``.
    Returns the resolved path (outside root only under a permitted escape), or
    None when a segment or target is absent. Raises NameLoopError,
    NameEscapeError, or SymlinkEscapeError mid-walk.
    """
    current = base
    scope = list(base_scope)
    i = 0
    while i < len(parts):
        if not current.is_dir():
            return None
        part = parts[i]
        child = _lookup_child(current, part, case_sensitive=case_sensitive)
        if child is not None:
            if child.is_symlink():
                hops[0] += 1
                if hops[0] > hops[1]:
                    raise NameLoopError("resolution depth exceeded")
                target = child.resolve()
                if escape_policy == "reject-escaping" and not _is_under_root(
                    root, target
                ):
                    raise SymlinkEscapeError("symlink escapes root")
                if escape_policy == "unsupported":
                    raise SymlinkEscapeError("symlinks unsupported")
                current = target
            else:
                current = child
            i += 1
            if current.is_dir():
                scope.append((current, load_name_table(current)))
            continue

        # literal miss: resolve the segment as a name, nearest scope first
        resolved_node: Path | None = None
        for level in range(len(scope) - 1, -1, -1):
            defining_dir, table = scope[level]
            if part not in table:
                continue
            for tgt in table[part]:
                hops[0] += 1
                if hops[0] > hops[1]:
                    raise NameLoopError("name resolution depth exceeded")
                if tgt.startswith("/"):
                    t_base = root
                    t_parts = normalize_path_parts(tgt.lstrip("/").split("/"))
                else:
                    t_base = defining_dir
                    t_parts = normalize_path_parts(tgt.split("/"))
                node = _resolve_walk(
                    root,
                    t_base,
                    _scope_for(root, t_base),
                    t_parts,
                    escape_policy=escape_policy,
                    case_sensitive=case_sensitive,
                    hops=hops,
                )
                if node is None:
                    continue  # dangling alternative; try the next target
                if not _is_under_root(root, node.resolve()):
                    if escape_policy != "follow":
                        raise NameEscapeError("name target escapes root")
                resolved_node = node
                break
            break  # nearest matching name decides; do not search outer scopes
        if resolved_node is None:
            return None
        current = resolved_node
        scope = _scope_for(root, current)
        i += 1
    return current


def _walk_under_root(
    root: Path,
    rel_parts: list[str],
    *,
    escape_policy: str = "reject-escaping",
    case_sensitive: bool,
    max_depth: int = 40,
) -> Path | None:
    root = root.resolve()
    parts = normalize_path_parts(rel_parts)
    resolved = _resolve_walk(
        root,
        root,
        _scope_for(root, root),
        parts,
        escape_policy=escape_policy,
        case_sensitive=case_sensitive,
        hops=[0, max_depth],
    )
    if resolved is None:
        return None
    if not _is_under_root(root, resolved.resolve()):
        raise RootEscapeError("path escapes root")
    return resolved


def _lookup_child(directory: Path, name: str, *, case_sensitive: bool) -> Path | None:
    direct = directory / name
    if direct.exists() or direct.is_symlink():
        return direct
    if case_sensitive:
        return None
    for entry in directory.iterdir():
        if entry.name.lower() == name.lower():
            return entry
    return None


def resolve_under_root(
    root: Path,
    rel_parts: list[str],
    *,
    escape_policy: str = "reject-escaping",
    case_sensitive: bool = True,
) -> Path | None:
    if not rel_parts:
        return root.resolve() if root.is_dir() else None
    try:
        return _walk_under_root(
            root,
            rel_parts,
            escape_policy=escape_policy,
            case_sensitive=case_sensitive,
        )
    except (RootEscapeError, SymlinkEscapeError, PathSegmentError):
        return None


def try_exact_filesystem(
    root: Path,
    raw_segments: list[str],
    *,
    escape_policy: str = "reject-escaping",
    case_sensitive: bool = True,
) -> FilesystemResource | None:
    if not raw_segments:
        if root.is_dir():
            return FilesystemResource("directory", root.resolve(), "")
        return None

    fs_segments = list(raw_segments)
    last = fs_segments[-1]
    if "?" in last:
        name_part, query_rest = last.split("?", 1)
        if "/" not in query_rest:
            fs_segments[-1] = name_part
            if fs_segments[-1] == "":
                return None

    decoded_parts: list[str] = []
    for raw in fs_segments:
        try:
            decoded_parts.append(percent_decode_segment(raw, for_filesystem=True))
        except PathSegmentError:
            return None

    try:
        resolved = _walk_under_root(
            root,
            decoded_parts,
            escape_policy=escape_policy,
            case_sensitive=case_sensitive,
        )
    except (RootEscapeError, SymlinkEscapeError):
        return None

    if resolved is None or not resolved.exists():
        return None

    rel = resolved.resolve().relative_to(root.resolve()).as_posix()
    requested = "/".join(normalize_path_parts(decoded_parts))
    via = rel != requested
    if resolved.is_dir():
        return FilesystemResource("directory", resolved, rel, via_indirection=via)
    if resolved.is_file() or resolved.is_symlink():
        return FilesystemResource("file", resolved, rel, via_indirection=via)
    return None


def _env_config_lines(path: Path) -> list[str]:
    lines: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
    return lines


def load_mime_config(root: Path) -> tuple[dict[str, str], str | None]:
    """Parse root/env/mime per runtime.md §7.4: (suffix map, declared default)."""
    mime_file = root / "env" / "mime"
    mapping: dict[str, str] = {}
    default: str | None = None
    if not mime_file.is_file():
        return mapping, default
    for line in _env_config_lines(mime_file):
        tokens = line.split()
        if len(tokens) != 2:
            raise EnvConfigError(f"malformed env/mime line: {line!r}")
        key, media_type = tokens
        if "/" not in media_type:
            raise EnvConfigError(f"malformed env/mime media type: {media_type!r}")
        if key == "default":
            default = media_type
        elif key.startswith(".") and len(key) > 1:
            mapping[key.lower()] = media_type
        else:
            raise EnvConfigError(f"malformed env/mime suffix: {key!r}")
    return mapping, default


def load_index_names(root: Path) -> list[str]:
    """Parse root/env/index per runtime.md §7.5; absent -> ["index.html"]."""
    index_file = root / "env" / "index"
    if not index_file.is_file():
        return list(DEFAULT_INDEX_NAMES)
    names: list[str] = []
    for line in _env_config_lines(index_file):
        if "/" in line or "\\" in line or "\x00" in line or line in {".", ".."}:
            raise EnvConfigError(f"malformed env/index entry: {line!r}")
        names.append(line)
    return names


def listing_enabled(root: Path) -> bool:
    """Parse root/env/listing per runtime.md §7.6; absent -> enabled."""
    listing_file = root / "env" / "listing"
    if not listing_file.is_file():
        return True
    lines = _env_config_lines(listing_file)
    if len(lines) != 1 or lines[0] not in {"on", "off"}:
        raise EnvConfigError("malformed env/listing: expected single on/off token")
    return lines[0] == "on"


def infer_mime(path: Path, root: Path | None = None) -> str:
    """Resolve Content-Type per runtime.md §6.1 resolution order."""
    ext = path.suffix.lower()
    if root is not None:
        mapping, default = load_mime_config(root)
        if ext in mapping:
            return mapping[ext]
        if default is not None:
            return default
    return FALLBACK_MIME_TABLE.get(ext, MIME_DEFAULT)


def infer_mime_from_bytes(data: bytes, declared: str | None = None) -> str:
    if declared:
        return declared
    if not data:
        return "text/plain"
    try:
        data.decode("utf-8")
        return "text/plain"
    except UnicodeDecodeError:
        return MIME_DEFAULT


def read_file_bytes(path: Path) -> bytes:
    return path.read_bytes()


def directory_listing(path: Path) -> bytes:
    lines: list[str] = []
    for entry in sorted(path.iterdir(), key=lambda p: p.name):
        suffix = "/" if entry.is_dir() else ""
        lines.append(f"{entry.name}{suffix}")
    body = "\n".join(lines)
    if lines:
        body += "\n"
    return body.encode("utf-8")


def find_index_file(path: Path, index_names: list[str]) -> Path | None:
    for name in index_names:
        candidate = path / name
        if candidate.is_file():
            return candidate
    return None


def put_file(
    root: Path,
    rel_parts: list[str],
    body: bytes,
    *,
    create_parents: bool = True,
    escape_policy: str = "reject-escaping",
) -> Path:
    root = root.resolve()
    normalized = normalize_path_parts(rel_parts)
    if not normalized:
        raise RootEscapeError("cannot PUT root directory")

    current = root
    for part in normalized[:-1]:
        current = current / part
        if current.exists() and current.is_symlink():
            resolved = current.resolve()
            if escape_policy == "reject-escaping" and not _is_under_root(
                root, resolved
            ):
                raise SymlinkEscapeError("symlink escapes root")
        if not _is_under_root(root, current):
            raise RootEscapeError("path escapes root")

    target = current / normalized[-1]
    if target.exists() and target.is_symlink():
        resolved = target.resolve()
        if escape_policy == "reject-escaping" and not _is_under_root(root, resolved):
            raise SymlinkEscapeError("symlink escapes root")
    if not _is_under_root(root, target):
        raise RootEscapeError("path escapes root")

    if create_parents:
        target.parent.mkdir(parents=True, exist_ok=True)
    elif not target.parent.exists():
        raise FileNotFoundError("parent directory does not exist")

    target.write_bytes(body)
    return target


def delete_file(
    root: Path,
    rel_parts: list[str],
    *,
    escape_policy: str = "reject-escaping",
) -> None:
    resolved = resolve_under_root(root, rel_parts, escape_policy=escape_policy)
    if resolved is None or not resolved.is_file():
        raise FileNotFoundError("file not found")
    resolved.unlink()


def literal_path_parts_from_raw(raw_segments: list[str]) -> list[str]:
    return [percent_decode_segment(raw, for_filesystem=True) for raw in raw_segments]


def implied_cat_bytes(
    root: Path,
    raw_segments: list[str],
    *,
    escape_policy: str = "reject-escaping",
    case_sensitive: bool = True,
) -> bytes:
    if not raw_segments:
        return b""
    fs_parts = [
        percent_decode_segment(raw, for_filesystem=True) for raw in raw_segments
    ]
    resolved = resolve_under_root(
        root,
        fs_parts,
        escape_policy=escape_policy,
        case_sensitive=case_sensitive,
    )
    if resolved is None:
        raise FileNotFoundError("input suffix not found")
    if resolved.is_dir():
        raise IsADirectoryError("input suffix is a directory")
    return resolved.read_bytes()
