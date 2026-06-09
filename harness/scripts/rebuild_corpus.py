#!/usr/bin/env python3
"""Rebuild harness roots to align with conformance vectors.

WARNING: this script removes and rewrites many directories under harness/roots.
Run it only when intentionally regenerating the canonical fixture corpus, then
inspect the full diff before keeping the result.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent
ROOTS = HARNESS / "roots"
LIB = ROOTS / "_lib"

sys.path.insert(0, str(HARNESS))
from conformance.rootcorpus import ensure_exit_lib  # noqa: E402


def lib_copy(name: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    src = LIB / f"{name}.sh"
    if src.is_file():
        shutil.copy2(src, dest)
        dest.chmod(0o644)
        common = LIB / "_common.sh"
        if common.is_file():
            shutil.copy2(common, dest.parent / "_common.sh")
    else:
        dest.write_text(f"# missing _lib/{name}.sh\n", encoding="utf-8")


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def setup_bin(root: Path, *commands: str) -> None:
    write(root / "env" / "path", "bin\n")
    for cmd in commands:
        lib_copy(cmd, root / "bin" / cmd)
    write(root / "exec", "\n".join(f"{c} sh" for c in commands) + "\n")


def copy_cat_as(root: Path, name: str) -> None:
    lib_copy("cat", root / "bin" / name)


def rebuild_precedence() -> None:
    root = ROOTS / "precedence"
    if root.exists():
        shutil.rmtree(root)
    write(root / "env" / "path", "bin\n")
    write(root / "env" / "meta" / "grep", "arity 1\n")
    write(root / "exec", "wc sh\ngrep sh\n")
    linecount = (LIB / "linecount.sh").read_text(encoding="utf-8")
    write(
        root / "bin" / "wc",
        "# wash-fixture: linecount\n" + linecount.split("\n", 1)[-1],
    )
    lib_copy("grep", root / "bin" / "grep")
    write(root / "wc", "i am a regular file named wc")
    write(root / "grep" / "docs" / "file.txt", "served as a file, not a pipeline")
    write(root / "haystack.json", "alpha\nbravo\ncharlie\n")


def rebuild_commands_mf() -> None:
    root = ROOTS / "commands-mf"
    if root.exists():
        shutil.rmtree(root)
    setup_bin(root, "cat", "identity", "grep", "filter")
    write(root / "env" / "meta" / "filter", "arity 1\n")
    write(root / "data.txt", "alpha\nbravo\ncharlie\n")


def rebuild_body_input() -> None:
    root = ROOTS / "body-input"
    if root.exists():
        shutil.rmtree(root)
    setup_bin(root, "transform", "echoN")
    write(root / "env" / "meta" / "transform", "methods GET POST\n")
    write(root / "env" / "meta" / "echoN", "arity *\nmethods GET POST\n")
    write(root / "data.txt", "alpha\nbravo\ncharlie\n")


def rebuild_commands_meta() -> None:
    root = ROOTS / "commands-meta"
    if root.exists():
        shutil.rmtree(root)
    cmds = [
        "getpost",
        "typed",
        "typed-mid",
        "stderr-discard",
        "stderr-merge",
        "exit-mapped",
        "explain",
        "noisy",
        "identity",
    ]
    setup_bin(root, *cmds)
    for c in ("getpost", "typed", "typed-mid"):
        copy_cat_as(root, c)
    lib_copy("noisy", root / "bin" / "stderr-discard")
    lib_copy("noisy", root / "bin" / "stderr-merge")
    write(root / "data.txt", "line\n")
    write(root / "env" / "meta" / "getpost", "methods GET POST\n")
    write(root / "env" / "meta" / "typed", "mime text/plain\n")
    write(root / "env" / "meta" / "typed-mid", "mime application/json\n")
    write(root / "env" / "meta" / "stderr-discard", "stderr discard\n")
    write(root / "env" / "meta" / "stderr-merge", "stderr merge\n")
    write(root / "env" / "meta" / "exit-mapped", "exit 42=418\n")
    write(root / "env" / "meta" / "explain", "parse-mode raw\n")
    shutil.copy2(LIB / "exit42.sh", root / "bin" / "exit-mapped")
    shutil.copy2(LIB / "_common.sh", root / "bin" / "_common.sh")


def rebuild_meta_malformed() -> None:
    root = ROOTS / "meta-malformed"
    if root.exists():
        shutil.rmtree(root)

    cases = {
        "bad-arity": "arity x\n",
        "bad-exit": "exit 0=not-a-status\n",
        "bad-mime": "mime notamime\n",
        "bad-stderr": "stderr loud\n",
        "mutates-get": "methods GET\nmutates true\n",
        "input-file": "input file\n",
        "input-none": "input none\n",
        "output-file": "output file\n",
        "arity-range-bounded": "arity 1..3\n",
        "arity-range-star": "arity 0..*\n",
    }
    all_cmds = list(cases.keys()) + ["identity", "mid-raw", "noisy", "exit1", "sort"]
    setup_bin(root, *all_cmds)
    for name, meta in cases.items():
        write(root / "env" / "meta" / name, meta)
        copy_cat_as(root, name)

    write(root / "env" / "meta" / "mid-raw", "parse-mode raw\n")
    write(root / "exec", "\n".join(f"{c} sh" for c in all_cmds) + "\n")


def rebuild_methods() -> None:
    root = ROOTS / "methods"
    if root.exists():
        shutil.rmtree(root)
    setup_bin(root, "defaultcmd", "getonly", "identity")
    copy_cat_as(root, "defaultcmd")
    write(root / "data.txt", "alpha\n")
    write(root / "env" / "meta" / "getonly", "methods GET\n")


def rebuild_exit_codes() -> None:
    root = ROOTS / "exit-codes"
    if root.exists():
        shutil.rmtree(root)
    setup_bin(root, "exit1", "exit2", "exit42-mapped", "identity")
    write(root / "env" / "meta" / "exit42-mapped", "exit 42=451\n")
    shutil.copy2(LIB / "exit42.sh", root / "bin" / "exit42-mapped")
    shutil.copy2(LIB / "_common.sh", root / "bin" / "_common.sh")


def rebuild_directories() -> None:
    root = ROOTS / "directories"
    if root.exists():
        shutil.rmtree(root)
    setup_bin(root, "dirprobe", "grep", "wc")
    write(root / "env" / "meta" / "grep", "arity 1\n")
    write(root / "with-index" / ".keep", "")
    write(root / "no-index" / ".keep", "")
    write(root / "docs" / "readme.txt", "wash-fixture: docs readme\n")


def rebuild_exec_rules() -> None:
    root = ROOTS / "exec-rules"
    if root.exists():
        shutil.rmtree(root)
    write(root / "env" / "path", "bin\n")
    lib_copy("echo1", root / "bin" / "echo1")
    lib_copy("echo1", root / "bin" / "globmatch")
    lib_copy("echo1", root / "bin" / "unresolved-cmd")
    write(root / "env" / "meta" / "echo1", "arity 1\n")
    write(root / "env" / "meta" / "globmatch", "arity 1\n")
    write(
        root / "exec",
        "# comment line\n\n"
        "echo1 sh\n"
        "glob* sh\n"
        "unresolved-cmd __wash_missing_interpreter__\n",
    )

    mal = ROOTS / "exec-malformed"
    if mal.exists():
        shutil.rmtree(mal)
    setup_bin(mal, "malformed-exec-cmd")
    write(mal / "env" / "meta" / "malformed-exec-cmd", "arity 0\n")
    write(mal / "exec", "malformed-exec-cmd sh\nmalformed\n")


def rebuild_commands_arity() -> None:
    root = ROOTS / "commands-arity"
    if root.exists():
        shutil.rmtree(root)
    setup_bin(root, "echo1", "echo2", "echoN")
    write(root / "env" / "meta" / "echo1", "arity 1\n")
    write(root / "env" / "meta" / "echo2", "arity 2\n")
    write(root / "env" / "meta" / "echoN", "arity *\n")
    write(root / "data.txt", "alpha\nbravo\ncharlie\n")
    write(root / "alpha.txt", "alpha\n")
    write(root / "beta.txt", "beta\n")
    write(root / "tail", "tail-content\n")


def rebuild_commands_query() -> None:
    root = ROOTS / "commands-query"
    if root.exists():
        shutil.rmtree(root)
    setup_bin(root, "grep", "echo1", "echo2", "echoN", "jq")
    write(root / "env" / "meta" / "grep", "arity 1\n")
    write(root / "env" / "meta" / "echo2", "arity 2\n")
    write(root / "haystack.txt", "alpha\nbravo needle\ncharlie\n")
    write(root / "data.txt", "alpha\nbravo\ncharlie\n")


def rebuild_pipelines() -> None:
    root = ROOTS / "pipelines"
    if root.exists():
        shutil.rmtree(root)
    setup_bin(root, "cat", "jq", "grep", "filter", "count")
    write(root / "env" / "meta" / "grep", "arity 1\n")
    write(root / "env" / "meta" / "filter", "arity 1\n")
    write(root / "oneline.txt", "bravo\n")
    write(root / "data.txt", "alpha\nbravo\ncharlie\n")


def rebuild_stderr() -> None:
    root = ROOTS / "stderr"
    if root.exists():
        shutil.rmtree(root)
    setup_bin(root, "noisy", "count", "filter", "dirprobe")
    lib_copy("noisy", root / "bin" / "&noisy")
    write(root / "exec", "noisy sh\ncount sh\nfilter sh\ndirprobe sh\n&noisy sh\n")
    write(root / "env" / "meta" / "count", "stderr merge\n")
    write(root / "env" / "meta" / "filter", "arity 1\n")
    write(root / "records.txt", "alpha\nbravo needle\n")
    write(root / "data.txt", "alpha\nbravo needle\n")
    write(root / "docs" / "readme.txt", "docs\n")


def rebuild_mutation() -> None:
    root = ROOTS / "mutation"
    if root.exists():
        shutil.rmtree(root)
    setup_bin(root, "sort")
    write(root / "env" / "meta" / "sort", "methods POST\nmutates true\narity 1\n")
    write(root / "plain.txt", "original\n")
    write(root / "input.txt", "beta\nalpha\n")
    write(root / "writable" / "existing.txt", "original\n")
    write(root / "writable" / "todelete.txt", "delete-me\n")


def rebuild_encoding() -> None:
    root = ROOTS / "encoding"
    if root.exists():
        shutil.rmtree(root)
    setup_bin(root, "echo1", "grep", "jq")
    lib_copy("grep", root / "bin" / "&cmd")
    write(root / "exec", "echo1 sh\ngrep sh\njq sh\n&cmd sh\n")
    write(root / "env" / "meta" / "echo1", "arity 1\n")
    write(root / "env" / "meta" / "grep", "arity 1\n")
    write(root / "brackets.txt", "[]\n")
    write(root / "literal?q.txt", "literal question filename\n")
    write(root / "argv" / "needle.txt", "hay\n")
    write(root / "data.txt", "alpha\nbravo\ncharlie\n")
    write(root / "tail", "tail\n")
    write(root / "rest", "rest\n")


def rebuild_plain_files() -> None:
    root = ROOTS / "plain-files"
    if root.exists():
        shutil.rmtree(root)
    write(root / "arbitrary.txt", "arbitrary plain file content")
    write(root / "data.json", '{"sample":true,"name":"data"}')
    write(root / "nested" / "path" / "file.txt", "nested path file content")
    write(root / "literal?q.txt", "literal question filename\n")
    write(root / ".dotfile", "dot\n")
    write(root / ".segment" / "normal.txt", "segment\n")


def rebuild_path_outside() -> None:
    shared = ROOTS.parent / "shared" / "bin"
    shared.mkdir(parents=True, exist_ok=True)
    lib_copy("echo1", shared / "echo1")
    write(shared / "env" / "meta" / "echo1", "arity 1\n")
    root = ROOTS / "path-outside"
    if root.exists():
        shutil.rmtree(root)
    write(root / "env" / "path", "../shared/bin\n")
    write(root / "env" / "meta" / "echo1", "arity 1\n")
    write(root / "local-only.txt", "local\n")
    write(root / "exec", "echo1 sh\n")


def main() -> None:
    ensure_exit_lib()
    rebuild_precedence()
    rebuild_commands_mf()
    rebuild_body_input()
    rebuild_commands_meta()
    rebuild_meta_malformed()
    rebuild_methods()
    rebuild_exit_codes()
    rebuild_directories()
    rebuild_exec_rules()
    rebuild_commands_arity()
    rebuild_commands_query()
    rebuild_pipelines()
    rebuild_stderr()
    rebuild_mutation()
    rebuild_encoding()
    rebuild_plain_files()
    rebuild_path_outside()
    print("Corpus rebuilt.")


if __name__ == "__main__":
    main()
