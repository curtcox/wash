# wash install

Wire **host-OS commands** into a wash **root** so the runtime can resolve and run
them. The on-disk contract is normative in
[`specs/command_install.md`](../../specs/command_install.md); this is the
reference implementation.

An installed command is just an ordinary command file on an ordinary search path
(`runtime.md` §6–§7) — the runtime needs to know nothing about installation. Each
install writes a tiny, inspectable `sh` **wrapper** that `exec`s the absolute host
path, ensures the command directory is on `root/env/path`, and — when known —
writes command metadata.

## `wash-install add <name>`

```bash
# wire `jq` from the host PATH into the `precedence` root's bin/
python -m washinstall add jq --root ../../harness/roots/precedence

# point at an explicit host path instead of using PATH
python -m washinstall add jq --from /opt/homebrew/bin/jq --root ./myroot

# supply explicit metadata (pipeline_parsing.md §5.6 fields)
python -m washinstall add wc --meta arity=0 --meta mime=text/plain --root ./myroot
```

It writes `root/bin/<name>`:

```sh
#!/bin/sh
# wash-install:1 name=jq host=/opt/homebrew/bin/jq origin=path installed=2026-06-28T17:40:00Z
exec "/opt/homebrew/bin/jq" "$@"
```

ensures `bin` is listed in `root/env/path`, and writes `root/env/meta/jq` when a
metadata hint applies (e.g. `mime application/json` for `jq`).

When the command is **not** on the host, the registry suggests how to get it and
exits non-zero **without running any package manager**:

```
$ python -m washinstall add ripgrep --root ./myroot
error: ripgrep is not installed on the host.
  registry: ripgrep (rg)  [role: line-search, group: line-search]
  install it with:  brew install ripgrep  or  sudo apt-get install ripgrep
  then re-run:      wash install add ripgrep
```

## Other subcommands

| Command                       | What it does |
|-------------------------------|--------------|
| `list --root R`               | list installer-managed commands and whether their host path still resolves |
| `remove <name> --root R`      | remove a wrapper (and its marked metadata); refuses to touch hand-authored files |
| `search <query>`              | search the bundled registry by name/role/guidance |
| `info <name>`                 | show a registry entry and its install hint |

## The registry

The bundled catalog under [`washinstall/catalog/`](washinstall/catalog/) is the
text-processing toolbox: `tools.toml` is the source of truth, regenerate the
derived files (`tools.json`, `README.md`, `Brewfile`, `apt-packages.sh`) with
`python3 catalog/generate.py`. `meta_hints.toml` is the conservative overlay that
supplies derivable wash metadata (§8.3). The installer reads `tools.json`.

## Develop

```bash
cd tools/install && python -m pytest -q     # or: make install-tool-test (from repo root)
```

Stdlib-only; no install required (tests set `pythonpath = ["."]`).
