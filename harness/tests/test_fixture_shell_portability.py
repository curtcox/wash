"""Cross-shell portability self-test for the shell command fixtures.

The fixture corpus under ``harness/roots/*/bin`` and ``harness/roots/_lib`` is
invoked through each implementation's ``/bin/sh``. That shell is **bash** on
macOS but **dash** on Ubuntu CI, so a bash-only construct in a fixture (e.g.
the ANSI-C quote ``$'\\001'``) silently no-ops under dash and produces an empty
response body. Such a fixture passes conformance on macOS yet fails on Ubuntu,
and nothing in the suite previously exercised the corpus under more than one
shell -- so the divergence was invisible locally.

This test runs every shell fixture under every available ``sh`` implementation
(at minimum bash and dash) and asserts byte-identical results. It checks
*cross-shell agreement*, not correctness against a golden, so it needs no
per-fixture expected output and stays robust as fixtures evolve. Any fixture
that behaves differently across shells -- this ``$'\\001'`` case or any future
bashism (``local``, ``[[ ]]``, ``echo -e``, ``${x^^}``, arrays, ...) -- fails
the moment the shells disagree, in whichever environment the test runs.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest


@dataclass(frozen=True)
class ShellResult:
    """Observable result of running a fixture under one shell."""

    returncode: int
    stdout: bytes
    stderr: bytes
    files: dict[str, bytes]


HARNESS_ROOT = Path(__file__).resolve().parent.parent
ROOTS = HARNESS_ROOT / "roots"
SHARED = HARNESS_ROOT / "shared"

# Raw newline-delimited input. Fixtures internally tag records with the SOH
# separator, so a non-empty record stream is what exercises the record-matching
# ``case`` arms where bashisms hide. "alpha" doubles as a matching needle for
# grep-style fixtures that take a search argument.
FIXTURE_STDIN = b"alpha\nbeta\ngamma\n"
FIXTURE_ARGV = ["alpha"]

# Subprocess wall-clock guard so a misbehaving fixture cannot hang the suite.
RUN_TIMEOUT_SEC = 15


def _discover_shells() -> dict[str, list[str]]:
    """Return available ``sh`` implementations as name -> command prefix.

    Probes for distinct POSIX-sh implementations on PATH. bash and dash are the
    two that matter for the macOS/Ubuntu split; busybox is included
    best-effort. The keys are stable so xdist sharding and failure messages are
    deterministic.
    """
    shells: dict[str, list[str]] = {}
    for name in ("bash", "dash", "posh"):
        path = shutil.which(name)
        if path:
            shells[name] = [path]
    busybox = shutil.which("busybox")
    if busybox:
        shells["busybox-sh"] = [busybox, "sh"]
    return shells


def _has_shebang_sh(path: Path) -> bool:
    """True if the file declares an ``sh`` shebang within its first two lines.

    Most fixtures put ``#!/bin/sh`` on line 1, but a few (e.g.
    ``shared/bin/outside``) carry a ``# wash-fixture:`` marker first.
    """
    try:
        with path.open("rb") as handle:
            head = handle.read(256)
    except OSError:
        return False
    for line in head.splitlines()[:2]:
        text = line.decode("utf-8", errors="replace").strip()
        if text.startswith("#!") and text.endswith("sh"):
            return True
    return False


def _discover_fixtures() -> list[Path]:
    """Collect shell command fixtures to exercise.

    Includes every ``sh``-shebanged file under the served roots' ``bin``
    directories and the shared ``bin``, plus the named ``_lib/*.sh`` helpers.
    Excludes the sourced ``_common.sh`` (a library, not a program) and the
    generated, trivial ``exit<N>.sh`` stubs.
    """
    candidates: list[Path] = []

    bin_globs = [
        *ROOTS.glob("*/bin/**/*"),
        *(SHARED.glob("bin/**/*") if SHARED.exists() else []),
    ]
    for path in bin_globs:
        if not path.is_file():
            continue
        if path.name == "_common.sh":
            continue
        if _has_shebang_sh(path):
            candidates.append(path)

    lib = ROOTS / "_lib"
    for path in sorted(lib.glob("*.sh")):
        if path.name == "_common.sh":
            continue
        # exit<N>.sh are generated on demand and are trivial printf+exit stubs.
        stem = path.stem
        if stem.startswith("exit") and stem[len("exit") :].isdigit():
            continue
        if _has_shebang_sh(path):
            candidates.append(path)

    # De-dup while preserving order; stable relative-path ids for parametrize.
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in candidates:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    return sorted(unique, key=lambda p: p.relative_to(HARNESS_ROOT).as_posix())


SHELLS = _discover_shells()
FIXTURES = _discover_fixtures()


def _run(shell_cmd: list[str], fixture: Path, workdir: Path) -> ShellResult:
    """Run *fixture* under *shell_cmd* in an isolated *workdir*.

    ``argv[0]`` is the fixture's absolute path so ``dirname "$0"`` resolves the
    adjacent ``_common.sh`` regardless of cwd, while the cwd is a throwaway
    directory. That keeps the canonical corpus read-only and captures any files
    a fixture writes (e.g. ``sort``'s output-file argument) so file-output
    divergences are compared too, not just stdout/stderr.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(  # noqa: S603 - inputs are repo fixtures, not user data
        [*shell_cmd, str(fixture.resolve()), *FIXTURE_ARGV],
        cwd=workdir,
        input=FIXTURE_STDIN,
        capture_output=True,
        timeout=RUN_TIMEOUT_SEC,
    )
    written = {
        path.relative_to(workdir).as_posix(): path.read_bytes()
        for path in sorted(workdir.rglob("*"))
        if path.is_file()
    }
    return ShellResult(proc.returncode, proc.stdout, proc.stderr, written)


def _fmt(label: str, result: ShellResult) -> str:
    return (
        f"  {label}: rc={result.returncode}\n"
        f"    stdout={result.stdout!r}\n"
        f"    stderr={result.stderr!r}\n"
        f"    files_written={result.files!r}"
    )


@pytest.mark.skipif(
    len(SHELLS) < 2,
    reason=(
        "need >=2 sh implementations to compare; found "
        f"{sorted(SHELLS) or 'none'}. Install dash (Ubuntu has it by default; "
        "`brew install dash` on macOS) so the cross-shell check can run."
    ),
)
@pytest.mark.skipif(not FIXTURES, reason="no shell fixtures discovered")
@pytest.mark.parametrize(
    "fixture",
    FIXTURES,
    ids=[p.relative_to(HARNESS_ROOT).as_posix() for p in FIXTURES],
)
def test_fixture_behaves_identically_across_shells(
    fixture: Path, tmp_path: Path
) -> None:
    shell_names = sorted(SHELLS)
    reference_name = shell_names[0]
    ref = _run(SHELLS[reference_name], fixture, tmp_path / reference_name)

    for name in shell_names[1:]:
        result = _run(SHELLS[name], fixture, tmp_path / name)
        if result != ref:
            rel = fixture.relative_to(HARNESS_ROOT).as_posix()
            pytest.fail(
                f"Shell divergence in fixture {rel!r}: "
                f"{reference_name} != {name} "
                "(likely a non-POSIX bashism that no-ops under dash).\n"
                f"{_fmt(reference_name, ref)}\n"
                f"{_fmt(name, result)}",
                pytrace=False,
            )
