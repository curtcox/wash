"""Wiring host commands into a wash root (specs/command_install.md §4–§9).

This module never runs a host command or package manager — it only writes files
into the root.
"""

from __future__ import annotations

import os
import shutil
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# Install-record / marker grammar (§5.2).
MARKER = "# wash-install:"
RECORD_VERSION = 1

# Recognized command-metadata fields (pipeline_parsing.md §5.6 / runtime.md §7.3).
META_FIELDS = frozenset(
    "arity input output methods mime mutates parse-mode stderr exit".split()
)

DEFAULT_BIN_DIR = "bin"


class InstallError(Exception):
    """A user-facing failure; the CLI prints the message and exits non-zero."""


@dataclass
class InstallResult:
    name: str
    host: str
    origin: str
    wrapper: Path
    meta: Path | None
    path_updated: bool


# ----------------------------------------------------------------- host resolve
def resolve_host(name: str, from_path: str | None) -> tuple[str, str]:
    """Resolve the host command to an absolute path and an origin tag ([CI-2/3])."""
    if from_path is not None:
        candidate = Path(from_path).expanduser()
        origin = "explicit"
        if not candidate.is_absolute():
            candidate = candidate.resolve()
        if not candidate.exists():
            raise InstallError(f"host path does not exist: {candidate}")
        if candidate.is_dir():
            raise InstallError(f"host path is a directory, not a command: {candidate}")
        if not os.access(candidate, os.X_OK):
            raise InstallError(f"host path is not executable: {candidate}")
        return str(candidate), origin

    found = shutil.which(name)
    if found is None:
        raise _not_found(name)
    return str(Path(found).resolve()), "path"


def _not_found(name: str) -> InstallError:
    return InstallError(f"command not found on host PATH: {name}")


# ------------------------------------------------------------------ atomic write
def _atomic_write(target: Path, text: str, *, executable: bool = False) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.parent / f".{target.name}.wash-install.tmp"
    tmp.write_text(text, encoding="utf-8")
    if executable:
        mode = tmp.stat().st_mode
        tmp.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    os.replace(tmp, target)


def _record_line(name: str, host: str, origin: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        f"{MARKER}{RECORD_VERSION} name={name} host={host} "
        f"origin={origin} installed={ts}"
    )


# ----------------------------------------------------------------- env/path mgmt
def _command_dirs(root: Path) -> list[str]:
    """The raw (verbatim) non-comment entries of root/env/path."""
    path_file = root / "env" / "path"
    if not path_file.is_file():
        return []
    out = []
    for line in path_file.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            out.append(s)
    return out


def ensure_path_entry(root: Path, bin_dir: str) -> bool:
    """Append bin_dir to root/env/path if absent (§6 [CI-8]). Returns True if changed."""
    path_file = root / "env" / "path"
    if bin_dir in _command_dirs(root):
        return False
    if path_file.is_file():
        existing = path_file.read_text(encoding="utf-8")
        if existing and not existing.endswith("\n"):
            existing += "\n"
        _atomic_write(path_file, existing + bin_dir + "\n")
    else:
        _atomic_write(path_file, bin_dir + "\n")
    return True


# ----------------------------------------------------------------------- install
def install(
    root: Path,
    name: str,
    *,
    from_path: str | None = None,
    bin_dir: str = DEFAULT_BIN_DIR,
    meta_overrides: dict[str, str] | None = None,
    hints: dict[str, dict[str, str]] | None = None,
    use_hints: bool = True,
    force: bool = False,
) -> InstallResult:
    if "/" in name or name in (".", ".."):
        raise InstallError(f"invalid command name: {name!r}")

    host, origin = resolve_host(name, from_path)

    wrapper = root / bin_dir / name
    if wrapper.exists() and not force:
        raise InstallError(
            f"{wrapper} already exists; pass --force to overwrite ([CI-14])"
        )

    path_updated = ensure_path_entry(root, bin_dir)

    body = f'#!/bin/sh\n{_record_line(name, host, origin)}\nexec "{host}" "$@"\n'
    _atomic_write(wrapper, body, executable=True)

    meta_path = _write_meta(root, name, meta_overrides or {}, hints or {}, use_hints)

    return InstallResult(
        name=name,
        host=host,
        origin=origin,
        wrapper=wrapper,
        meta=meta_path,
        path_updated=path_updated,
    )


def _write_meta(
    root: Path,
    name: str,
    overrides: dict[str, str],
    hints: dict[str, dict[str, str]],
    use_hints: bool,
) -> Path | None:
    """Compose and write env/meta/<name> when known/derivable (§7 [CI-9/10])."""
    fields: dict[str, str] = {}
    if use_hints:
        fields.update(hints.get(name, {}))
    fields.update(overrides)  # caller-supplied fields take precedence ([CI-9]).
    if not fields:
        return None

    unknown = sorted(set(fields) - META_FIELDS)
    if unknown:
        raise InstallError(
            f"unrecognized metadata field(s): {', '.join(unknown)} "
            f"(valid: {', '.join(sorted(META_FIELDS))})"
        )

    meta_path = root / "env" / "meta" / name
    lines = [f"{MARKER}{RECORD_VERSION} name={name}"]
    for key in sorted(fields):
        lines.append(f"{key} {fields[key]}")
    _atomic_write(meta_path, "\n".join(lines) + "\n")
    return meta_path


# -------------------------------------------------------------------- list/remove
@dataclass
class InstalledCommand:
    name: str
    host: str
    origin: str
    wrapper: Path
    host_ok: bool


def _parse_record(text: str) -> dict[str, str] | None:
    """Find and parse a marker record in the first few lines of a file (§5.2)."""
    for line in text.splitlines()[:5]:
        s = line.strip()
        if s.startswith(MARKER):
            fields: dict[str, str] = {}
            for tok in s[len(MARKER) :].split():
                if "=" in tok:
                    k, v = tok.split("=", 1)
                    fields[k] = v
            return fields
    return None


def list_installed(root: Path) -> list[InstalledCommand]:
    """Enumerate installer-managed commands across env/path dirs (§9 [CI-12])."""
    found: list[InstalledCommand] = []
    seen: set[str] = set()
    for entry in _command_dirs(root):
        d = Path(entry)
        d = d.resolve() if d.is_absolute() else (root / d)
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if not f.is_file():
                continue
            try:
                head = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rec = _parse_record(head)
            if rec is None or rec.get("name") != f.name:
                continue
            if f.name in seen:
                continue
            seen.add(f.name)
            host = rec.get("host", "")
            found.append(
                InstalledCommand(
                    name=f.name,
                    host=host,
                    origin=rec.get("origin", ""),
                    wrapper=f,
                    host_ok=bool(host) and os.access(host, os.X_OK),
                )
            )
    return found


def remove(root: Path, name: str, bin_dir: str = DEFAULT_BIN_DIR) -> list[Path]:
    """Remove an installer-managed wrapper and its marked metadata (§9 [CI-13])."""
    wrapper = root / bin_dir / name
    if not wrapper.is_file():
        # Fall back to scanning every command dir for the managed wrapper.
        match = next((c for c in list_installed(root) if c.name == name), None)
        if match is None:
            raise InstallError(f"no installer-managed command named {name!r}")
        wrapper = match.wrapper
    else:
        rec = _parse_record(wrapper.read_text(encoding="utf-8", errors="replace"))
        if rec is None:
            raise InstallError(
                f"{wrapper} is not installer-managed (no {MARKER!r} record); "
                f"refusing to remove ([CI-13])"
            )

    removed = [wrapper]
    wrapper.unlink()

    meta_path = root / "env" / "meta" / name
    if meta_path.is_file():
        rec = _parse_record(meta_path.read_text(encoding="utf-8", errors="replace"))
        if rec is not None:
            meta_path.unlink()
            removed.append(meta_path)
    return removed
