"""Root-directory corpus materialization, validation, and tree diff."""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from conformance.capabilities import harness_dir

MISSING_INTERPRETER = "__wash_missing_interpreter__"
_LIB_COMMANDS = {
    "cat",
    "identity",
    "grep",
    "jq",
    "filter",
    "count",
    "dirprobe",
    "linecount",
    "echo1",
    "echo2",
    "echoN",
    "noisy",
    "transform",
    "sort",
    "explain",
}
_EXIT_FAMILY = {f"exit{i}" for i in range(256)}
_LIB_COMMANDS |= _EXIT_FAMILY

BUNDLE_ROOTS = frozenset({"path-outside"})
VIRTUAL_ROOTS = frozenset({"empty"})


@dataclass
class MaterializedRoot:
    name: str
    path: Path
    bundle_root: Path | None = None
    _snapshot: dict[str, Any] | None = field(default=None, repr=False)

    @property
    def diff_root(self) -> Path:
        return self.bundle_root or self.path

    def snapshot_if_needed(self, vector: dict[str, Any]) -> "TreeSnapshot | None":
        expect = vector.get("expect", {})
        if expect.get("no_mutation") or expect.get("mutation"):
            return TreeSnapshot.capture(self.diff_root)
        return None


@dataclass
class TreeSnapshot:
    entries: dict[str, dict[str, Any]]

    @classmethod
    def capture(cls, root: Path) -> "TreeSnapshot":
        entries: dict[str, dict[str, Any]] = {}
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames.sort()
            rel_dir = Path(dirpath).relative_to(root)
            for name in sorted(dirnames + filenames):
                p = Path(dirpath) / name
                rel = str(rel_dir / name) if str(rel_dir) != "." else name
                try:
                    st = p.lstat()
                except OSError:
                    continue
                kind = (
                    "symlink"
                    if stat.S_ISLNK(st.st_mode)
                    else ("dir" if stat.S_ISDIR(st.st_mode) else "file")
                )
                info: dict[str, Any] = {"type": kind}
                if kind == "file":
                    info["bytes"] = p.read_bytes()
                    info["mode"] = st.st_mode & 0o777
                elif kind == "symlink":
                    info["target"] = os.readlink(p)
                entries[rel] = info
        return cls(entries=entries)

    def diff(self, other: "TreeSnapshot") -> list[str]:
        changes: list[str] = []
        all_keys = sorted(set(self.entries) | set(other.entries))
        for key in all_keys:
            a = self.entries.get(key)
            b = other.entries.get(key)
            if a is None:
                changes.append(f"+ {key}")
            elif b is None:
                changes.append(f"- {key}")
            elif a != b:
                changes.append(f"~ {key}")
        return changes


_case_sensitive_cache: bool | None = None


def host_case_sensitive() -> bool:
    global _case_sensitive_cache
    if _case_sensitive_cache is not None:
        return _case_sensitive_cache
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        (p / "A").write_text("upper", encoding="utf-8")
        try:
            (p / "a").write_text("lower", encoding="utf-8")
            _case_sensitive_cache = (p / "A").read_text(
                encoding="utf-8"
            ) == "upper" and (p / "a").read_text(encoding="utf-8") == "lower"
        except OSError:
            _case_sensitive_cache = False
    return _case_sensitive_cache


def roots_dir() -> Path:
    return harness_dir() / "roots"


def lib_dir() -> Path:
    return roots_dir() / "_lib"


def ensure_exit_lib() -> None:
    """Create trivial exit0..exit255 .sh/.py variants when absent (not checked in)."""
    lib = lib_dir()
    lib.mkdir(parents=True, exist_ok=True)
    for code in range(256):
        sh = lib / f"exit{code}.sh"
        if not sh.is_file():
            sh.write_text(
                f"#!/bin/sh\nprintf 'exit:{code}\\n'\nexit {code}\n",
                encoding="utf-8",
            )
            sh.chmod(0o755)
        py = lib / f"exit{code}.py"
        if not py.is_file():
            py.write_text(
                "import sys\n\n"
                "def main() -> None:\n"
                f"    sys.stdout.write('exit:{code}\\n')\n"
                f"    raise SystemExit({code})\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n",
                encoding="utf-8",
            )
            py.chmod(0o644)


def list_roots() -> list[str]:
    base = roots_dir()
    virtual = set(VIRTUAL_ROOTS)
    if not base.is_dir():
        return sorted(virtual)
    return sorted(
        virtual
        | {p.name for p in base.iterdir() if p.is_dir() and not p.name.startswith("_")}
    )


def materialize(
    root_name: str,
    *,
    caps: dict[str, Any] | None = None,
    interpreter: str | None = None,
    interpreters: list[str] | None = None,
    synthesize_symlinks: bool = True,
    synthesize_case: bool = True,
) -> MaterializedRoot:
    ensure_exit_lib()
    src = roots_dir() / root_name
    if root_name not in VIRTUAL_ROOTS and not src.is_dir():
        raise FileNotFoundError(f"unknown root: {root_name}")

    tmp = Path(tempfile.mkdtemp(prefix=f"wash-root-{root_name}-"))
    bundle_root: Path | None = None

    if root_name in VIRTUAL_ROOTS:
        material_path = tmp
    elif root_name in BUNDLE_ROOTS:
        bundle_root = tmp
        served = tmp / "root"
        served.mkdir()
        _copy_tree(src, served)
        shared_src = roots_dir().parent / "shared"
        if shared_src.is_dir():
            _copy_tree(shared_src, tmp / "shared")
        material_path = served
    else:
        material_path = tmp
        _copy_tree(src, material_path)

    chosen = _choose_interpreter(interpreters, interpreter)
    if chosen and chosen != "sh":
        _substitute_interpreter(material_path, chosen)

    if synthesize_symlinks and caps and caps.get("symlink_policy") != "unsupported":
        if root_name == "symlinks":
            _synthesize_symlinks(material_path)

    if root_name == "names":
        _synthesize_names_escape(material_path)

    if (
        synthesize_case
        and caps
        and caps.get("case_sensitive_lookup")
        and host_case_sensitive()
        and root_name == "case"
    ):
        _synthesize_case_files(material_path)

    return MaterializedRoot(
        name=root_name,
        path=material_path,
        bundle_root=bundle_root,
    )


def cleanup(materialized: MaterializedRoot) -> None:
    root = materialized.bundle_root or materialized.path
    shutil.rmtree(root, ignore_errors=True)


def _copy_tree(src: Path, dst: Path) -> None:
    shutil.copytree(src, dst, dirs_exist_ok=True, symlinks=True)


def _choose_interpreter(
    interpreters: list[str] | None, override: str | None
) -> str | None:
    if override:
        return override
    if interpreters is None:
        return "sh"
    if "sh" in interpreters:
        return "sh"
    for name in interpreters:
        if _lib_has_interpreter(name):
            return name
    return None


def _lib_has_interpreter(name: str) -> bool:
    lib = lib_dir()
    if not lib.is_dir():
        return name == "sh"
    for cmd in _LIB_COMMANDS:
        if (lib / f"{cmd}.{'py' if name == 'python3' else 'sh'}").is_file():
            return True
    return False


def _substitute_interpreter(root: Path, interpreter: str) -> None:
    ext = ".py" if interpreter == "python3" else f".{interpreter}"
    lib = lib_dir()
    exec_path = root / "exec"
    for path in root.rglob("*"):
        if (
            path.is_file()
            and path.name not in {"exec", "path"}
            and not path.name.startswith(".")
        ):
            if path.parent.name == "meta":
                continue
            if path.parts[-2:] == ("env", "path"):
                continue
            cmd_name = path.name
            lib_variant = lib / f"{cmd_name}{ext}"
            if lib_variant.is_file() and path.stat().st_size > 0:
                shutil.copy2(lib_variant, path)

    if exec_path.is_file():
        lines = exec_path.read_text(encoding="utf-8").splitlines()
        new_lines = []
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                new_lines.append(line)
                continue
            parts = line.split()
            if (
                len(parts) >= 2
                and parts[-1] == "sh"
                and parts[-1] != MISSING_INTERPRETER
            ):
                parts[-1] = interpreter
                new_lines.append(" ".join(parts))
            else:
                new_lines.append(line)
        exec_path.write_text(
            "\n".join(new_lines) + ("\n" if new_lines else ""), encoding="utf-8"
        )


def _synthesize_symlinks(root: Path) -> None:
    target = root / "plain-target.txt"
    if not target.is_file():
        target.write_text("symlink-target\n", encoding="utf-8")
    outside = root.parent / "wash-outside-secret.txt"
    outside.write_text("outside-bytes", encoding="utf-8")
    link_ok = root / "link-ok"
    link_file = root / "link-to-file"
    escape = root / "link-escape"
    try:
        if not link_ok.exists():
            link_ok.symlink_to("plain-target.txt", target_is_directory=False)
        if not link_file.exists():
            link_file.symlink_to("plain-target.txt", target_is_directory=False)
        if not escape.exists():
            escape.symlink_to(outside)
    except OSError:
        pass


def _synthesize_names_escape(root: Path) -> None:
    """Write the out-of-root target for the names root's escape entry (not checked in)."""
    outside = root.parent / "wash-outside-secret.txt"
    try:
        outside.write_text("outside-bytes", encoding="utf-8")
    except OSError:
        pass


def _synthesize_case_files(root: Path) -> None:
    (root / "Readme").write_text("CASE-UPPER\n", encoding="utf-8")
    (root / "readme").write_text("case-lower\n", encoding="utf-8")


def validate_roots(*, interpreter: str | None = None) -> list[str]:
    ensure_exit_lib()
    errors: list[str] = []
    base = roots_dir()
    if not base.is_dir():
        errors.append(f"roots directory missing: {base}")
        return errors

    for root_name in list_roots():
        root_path = base / root_name
        if root_name not in VIRTUAL_ROOTS:
            errors.extend(_validate_root_tree(root_path, root_name))

        if interpreter:
            try:
                mat = materialize(
                    root_name,
                    interpreter=interpreter,
                )
                errors.extend(
                    _validate_root_tree(mat.path, f"{root_name}@{interpreter}")
                )
                cleanup(mat)
            except Exception as exc:
                errors.append(f"{root_name} materialize({interpreter}): {exc}")

    errors.extend(_validate_no_checked_in_symlinks(base))
    errors.extend(_validate_no_checked_in_case_collisions(base))
    errors.extend(_validate_lib_inventory())
    return errors


def _validate_root_tree(root: Path, label: str) -> list[str]:
    errors: list[str] = []
    exec_path = root / "exec"
    path_file = root / "env" / "path"
    if exec_path.is_file():
        for i, line in enumerate(exec_path.read_text(encoding="utf-8").splitlines(), 1):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            parts = s.split()
            if len(parts) < 2 and not label.startswith("exec-malformed"):
                errors.append(f"{label}: exec line {i}: malformed rule")
    if path_file.is_file():
        for i, line in enumerate(path_file.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip() and line.strip().startswith("#"):
                continue
    return errors


def _validate_no_checked_in_symlinks(base: Path) -> list[str]:
    errors: list[str] = []
    for path in base.rglob("*"):
        if path.is_symlink():
            errors.append(f"checked-in symlink forbidden: {path.relative_to(base)}")
    return errors


def _validate_no_checked_in_case_collisions(base: Path) -> list[str]:
    errors: list[str] = []
    seen: dict[str, str] = {}
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        key = str(path.relative_to(base)).lower()
        if key in seen and seen[key] != str(path.relative_to(base)):
            errors.append(
                f"case collision in corpus: {seen[key]} vs {path.relative_to(base)}"
            )
        seen[key] = str(path.relative_to(base))
    return errors


def _validate_lib_inventory() -> list[str]:
    errors: list[str] = []
    lib = lib_dir()
    if not lib.is_dir():
        return errors
    for cmd in sorted(_LIB_COMMANDS):
        sh = lib / f"{cmd}.sh"
        py = lib / f"{cmd}.py"
        if not sh.is_file() and not py.is_file():
            # exitN family may be generated — only warn for core commands
            if cmd in {"cat", "grep", "linecount", "echo1", "transform"}:
                errors.append(f"_lib missing canonical command: {cmd}")
    return errors


def can_materialize_for_interpreters(
    root_name: str, interpreters: list[str]
) -> tuple[bool, str]:
    if "sh" in interpreters:
        return True, "sh available"
    for name in interpreters:
        if _lib_has_interpreter(name):
            return True, f"{name} available"
    return False, f"no corpus interpreter variant for declared {interpreters!r}"


def root_commands(root_name: str) -> set[str]:
    if root_name in VIRTUAL_ROOTS:
        return set()
    root = roots_dir() / root_name
    cmds: set[str] = set()
    if not root.is_dir():
        return cmds
    for path in root.rglob("*"):
        if path.is_file() and "env/meta" in str(path):
            cmds.add(path.parent.name)
        elif path.is_file() and path.parent.name in {"bin", ""}:
            if path.name not in {"path", "exec"} and "env" not in path.parts:
                cmds.add(path.name)
    return cmds
