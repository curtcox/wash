"""Tests for the wash-install tool (specs/command_install.md)."""

import stat
from pathlib import Path

import pytest

from washinstall.cli import main
from washinstall.registry import _name_tokens, load_meta_hints, load_registry
from washinstall.wire import (
    MARKER,
    InstallError,
    install,
    list_installed,
    remove,
    resolve_host,
)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def host_cmd(tmp_path_factory) -> Path:
    """A real, executable host command file to wire in."""
    d = tmp_path_factory.mktemp("hostbin")
    cmd = d / "mytool"
    cmd.write_text("#!/bin/sh\necho hi\n")
    cmd.chmod(0o755)
    return cmd


# ---------------------------------------------------------------- host resolve
def test_resolve_from_explicit_path(host_cmd: Path):
    path, origin = resolve_host("mytool", str(host_cmd))
    assert Path(path) == host_cmd
    assert origin == "explicit"


def test_resolve_missing_path_raises():
    with pytest.raises(InstallError, match="does not exist"):
        resolve_host("x", "/no/such/file")


def test_resolve_non_executable_raises(tmp_path: Path):
    f = tmp_path / "plain"
    f.write_text("data")
    with pytest.raises(InstallError, match="not executable"):
        resolve_host("plain", str(f))


def test_resolve_missing_on_path_raises():
    with pytest.raises(InstallError, match="not found on host PATH"):
        resolve_host("definitely-not-a-real-command-xyz", None)


# --------------------------------------------------------------------- install
def test_install_writes_wrapper_record_and_path(root: Path, host_cmd: Path):
    result = install(root, "mytool", from_path=str(host_cmd))

    wrapper = root / "bin" / "mytool"
    assert wrapper.is_file()
    body = wrapper.read_text()
    assert body.startswith("#!/bin/sh\n")
    assert f"{MARKER}1 name=mytool host={host_cmd} origin=explicit" in body
    assert body.strip().endswith(f'exec "{host_cmd}" "$@"')
    # executable bit set ([CI-5])
    assert wrapper.stat().st_mode & stat.S_IXUSR

    # env/path created and lists bin ([CI-8])
    assert (root / "env" / "path").read_text().splitlines() == ["bin"]
    assert result.path_updated is True
    assert result.origin == "explicit"


def test_install_wrapper_execs_to_host(root: Path, host_cmd: Path):
    install(root, "mytool", from_path=str(host_cmd))
    wrapper = root / "bin" / "mytool"
    # The wrapper actually runs the host command.
    import subprocess

    out = subprocess.run([str(wrapper)], capture_output=True, text=True)
    assert out.stdout.strip() == "hi"


def test_install_does_not_duplicate_path_entry(root: Path, host_cmd: Path):
    install(root, "a", from_path=str(host_cmd))
    r2 = install(root, "b", from_path=str(host_cmd))
    assert r2.path_updated is False
    assert (root / "env" / "path").read_text().splitlines() == ["bin"]


def test_install_preserves_existing_path_file(root: Path, host_cmd: Path):
    (root / "env").mkdir()
    (root / "env" / "path").write_text("vendor/bin\n../shared/bin\n")
    install(root, "mytool", from_path=str(host_cmd))
    assert (root / "env" / "path").read_text().splitlines() == [
        "vendor/bin",
        "../shared/bin",
        "bin",
    ]


def test_install_refuses_overwrite_without_force(root: Path, host_cmd: Path):
    install(root, "mytool", from_path=str(host_cmd))
    with pytest.raises(InstallError, match="already exists"):
        install(root, "mytool", from_path=str(host_cmd))


def test_install_force_overwrites(root: Path, host_cmd: Path):
    install(root, "mytool", from_path=str(host_cmd))
    other = host_cmd.parent / "other"
    other.write_text("#!/bin/sh\necho bye\n")
    other.chmod(0o755)
    install(root, "mytool", from_path=str(other), force=True)
    assert f"host={other}" in (root / "bin" / "mytool").read_text()


def test_install_rejects_bad_name(root: Path, host_cmd: Path):
    with pytest.raises(InstallError, match="invalid command name"):
        install(root, "a/b", from_path=str(host_cmd))


# ---------------------------------------------------------------------- metadata
def test_metadata_from_overrides(root: Path, host_cmd: Path):
    result = install(
        root, "mytool", from_path=str(host_cmd), meta_overrides={"arity": "0"}
    )
    assert result.meta == root / "env" / "meta" / "mytool"
    text = result.meta.read_text()
    assert text.startswith(f"{MARKER}1 name=mytool")
    assert "arity 0" in text


def test_metadata_unknown_field_rejected(root: Path, host_cmd: Path):
    with pytest.raises(InstallError, match="unrecognized metadata field"):
        install(root, "mytool", from_path=str(host_cmd), meta_overrides={"bogus": "1"})


def test_metadata_from_hints(root: Path, host_cmd: Path):
    hints = {"mytool": {"mime": "application/json"}}
    result = install(root, "mytool", from_path=str(host_cmd), hints=hints)
    assert "mime application/json" in result.meta.read_text()


def test_no_meta_disables_hints(root: Path, host_cmd: Path):
    hints = {"mytool": {"mime": "application/json"}}
    result = install(
        root, "mytool", from_path=str(host_cmd), hints=hints, use_hints=False
    )
    assert result.meta is None
    assert not (root / "env" / "meta" / "mytool").exists()


def test_overrides_beat_hints(root: Path, host_cmd: Path):
    hints = {"mytool": {"mime": "application/json"}}
    result = install(
        root,
        "mytool",
        from_path=str(host_cmd),
        hints=hints,
        meta_overrides={"mime": "text/plain"},
    )
    assert "mime text/plain" in result.meta.read_text()


# ----------------------------------------------------------------- list / remove
def test_list_reports_managed_commands(root: Path, host_cmd: Path):
    install(root, "mytool", from_path=str(host_cmd))
    listed = list_installed(root)
    assert [c.name for c in listed] == ["mytool"]
    assert listed[0].host == str(host_cmd)
    assert listed[0].host_ok is True


def test_list_flags_missing_host(root: Path, host_cmd: Path):
    install(root, "mytool", from_path=str(host_cmd))
    host_cmd.unlink()
    listed = list_installed(root)
    assert listed[0].host_ok is False


def test_list_ignores_unmanaged_files(root: Path, host_cmd: Path):
    install(root, "mytool", from_path=str(host_cmd))
    (root / "bin" / "handmade").write_text("#!/bin/sh\necho hi\n")
    assert [c.name for c in list_installed(root)] == ["mytool"]


def test_remove_deletes_wrapper_and_meta(root: Path, host_cmd: Path):
    install(root, "mytool", from_path=str(host_cmd), meta_overrides={"arity": "0"})
    removed = remove(root, "mytool")
    assert not (root / "bin" / "mytool").exists()
    assert not (root / "env" / "meta" / "mytool").exists()
    assert len(removed) == 2


def test_remove_refuses_unmanaged(root: Path):
    (root / "bin").mkdir()
    (root / "bin" / "handmade").write_text("#!/bin/sh\necho hi\n")
    with pytest.raises(InstallError, match="not installer-managed"):
        remove(root, "handmade")


def test_remove_unknown_raises(root: Path):
    with pytest.raises(InstallError):
        remove(root, "nope")


# ------------------------------------------------------------------- registry
def test_name_tokens_parens_and_slashes():
    assert "rg" in _name_tokens("ripgrep (rg)")
    assert "ripgrep" in _name_tokens("ripgrep (rg)")
    assert _name_tokens("xxd / hexdump / od") >= {"xxd", "hexdump", "od"}


def test_registry_lookup_and_suggest():
    reg = load_registry()
    entry = reg.lookup("rg")
    assert entry is not None
    assert "ripgrep" in entry.name
    hint = entry.install_hint()
    assert hint and "ripgrep" in hint


def test_registry_search():
    reg = load_registry()
    hits = reg.search("json")
    assert any("jq" in e.tokens for e in hits)


def test_meta_hints_loaded():
    hints = load_meta_hints()
    assert hints["jq"]["mime"] == "application/json"


# ------------------------------------------------------------------------- CLI
def test_cli_add_and_list(root: Path, host_cmd: Path, capsys):
    rc = main(["add", "mytool", "--from", str(host_cmd), "--root", str(root)])
    assert rc == 0
    assert (root / "bin" / "mytool").is_file()

    rc = main(["list", "--root", str(root)])
    assert rc == 0
    assert "mytool" in capsys.readouterr().out


def test_cli_missing_command_suggests(root: Path, capsys):
    rc = main(["add", "ripgrep", "--root", str(root)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "ripgrep" in err
    assert "install it with" in err


def test_cli_unknown_command_errors(root: Path, capsys):
    rc = main(["add", "totally-unknown-xyz", "--root", str(root)])
    assert rc == 1
    assert "not in the registry" in capsys.readouterr().err
