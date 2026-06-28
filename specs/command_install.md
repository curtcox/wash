# Command Installation

This document specifies how a *host-OS command* is installed into a wash **root**
so that the runtime can resolve and execute it. It is a convention layered on top
of `runtime.md` §6 (resolution) and §7 (the `env/` capability files); it adds no
new runtime behavior. An implementation of the runtime needs to know nothing
about installation — an installed command is an ordinary command file on an
ordinary search path. This spec exists so that any installer (the reference
`wash install` tool under `tools/install/`, or another) produces byte-compatible
roots.

The clause IDs (`CI-*`) are stable and may be cited by tests and other tools.

## 1. Purpose and Scope

A wash root resolves commands as files found in the directories listed in
`root/env/path` (`runtime.md` §7.1). Authoring those files by hand is tedious and
error-prone. *Installation* is the act of taking a command that already exists on
the host operating system — addressed by name on `PATH` or by an absolute path —
and wiring it into a root so a URL segment can invoke it.

In scope:

- The on-disk artifacts an install produces and their exact format (§4–§7).
- How the bundled **registry** (the catalog vendored from `tools.toml`) informs
  resolution, package suggestions, and metadata (§8).
- Listing and removing installed commands (§9).
- Idempotency and exit behavior (§10).

Out of scope (§12): mutating the host system (running `brew`/`apt`), command
signing or trust, sandboxing, and cross-machine portability of the produced root
— all consistent with the runtime non-goals in `runtime.md` §3.

## 2. Terms

**Host command** — an executable resolvable on the host: a name found on the
process `PATH`, or an absolute filesystem path to an executable file.

**Install root** — the wash root the command is installed into (the `--root`).

**Command directory** — a directory listed in `root/env/path` where command files
live. The default and conventional directory is `root/bin` (§6).

**Wrapper** — the command file an install writes into a command directory. It is a
POSIX `sh` stub that `exec`s the host command (§5).

**Install record** — the single marker comment line inside a wrapper that makes an
installed command self-describing and machine-enumerable (§5.2). No separate
manifest file is used; the wrappers *are* the inventory.

**Registry** — the bundled catalog of known host commands (roles, redundancy
groups, `brew`/`apt` package names, guidance) vendored from `tools.toml` /
`tools.json` (§8).

## 3. Relationship to the Runtime

An install touches at most three runtime capability surfaces, all under `env/`:

| Artifact            | Runtime clause | Role in install |
|---------------------|----------------|-----------------|
| command directory   | §7.1           | holds the wrapper file |
| `root/env/path`     | §7.1           | must list the command directory |
| `root/env/meta/<n>` | §7.3 / `pipeline_parsing.md` §5.6 | optional command metadata |

An installer **must not** require, write, or modify `root/exec` (interpreter
rules, §7.2): the wrapper carries its own `#!/bin/sh` shebang and is marked
executable, so it is directly runnable without an interpreter rule.

> [CI-1] An installed command resolves and executes under an unmodified runtime
> using only the artifacts in the table above.

## 4. The Install Operation

Installing host command *H* under wash name *N* into root *R*, command directory
*D* (default `bin`) proceeds in this order:

1. **Resolve the host command** (§4.1). Failure here is terminal; no artifact is
   written.
2. **Ensure the command directory** *R/D* exists.
3. **Ensure the search path** lists *D*: read `R/env/path`; if *D* is not already
   an entry, append it (§6). Create `R/env/path` if absent.
4. **Write the wrapper** to *R/D/N* and mark it executable (§5).
5. **Write metadata** to `R/env/meta/N` when known or derivable, else skip (§7).

Steps 2–5 should be effectively atomic per artifact: write to a temporary file in
the destination directory and `rename` into place, so a concurrent reader never
observes a half-written wrapper.

### 4.1 Resolving the Host Command

> [CI-2] Resolution order is: (a) an explicit host path supplied by the caller
> (`--from`); otherwise (b) the first match for *N* on the host `PATH`.

> [CI-3] A resolved host path **must** be an existing file with the execute
> permission for the current user. A path that does not exist, is a directory, or
> is not executable is an error and writes nothing.

> [CI-4] When neither (a) nor (b) yields a host command, the installer consults
> the registry (§8). If *N* (or an alias) is a known command, the installer
> **reports** the exact `brew`/`apt` command that would install it and exits
> non-zero **without running any package manager** (`runtime.md` §3 non-goal;
> matches the user-chosen "suggest, don't run" policy). If *N* is unknown, it
> exits non-zero with a not-found error.

The host path recorded in the wrapper (§5) is the *resolved absolute path*, not
the bare name, so the installed command is stable against later `PATH` changes and
auditable by inspection.

## 5. Wrapper Format

> [CI-5] A wrapper is a POSIX-`sh` script of exactly this shape, where
> `<host>` is the resolved absolute host path (§4.1) and `<name>` is *N*:
>
> ```sh
> #!/bin/sh
> # wash-install:1 name=<name> host=<host> origin=<origin> installed=<timestamp>
> exec "<host>" "$@"
> ```

- Line 1 is the shebang; the file is created with mode `0755`.
- Line 2 is the **install record** (§5.2).
- The final line `exec`s the host command, forwarding every argument. Because it
  is `exec`, the wrapper adds no extra process to the pipeline at run time and the
  host command receives the wrapper's stdin/stdout/stderr unchanged. This makes
  the wrapper transparent to the pipeline semantics of `pipeline_parsing.md`: the
  installed command behaves exactly as the host command would.

> [CI-6] The host path and any value containing shell metacharacters **must** be
> double-quoted as shown. `"$@"` (quoted) is required so argument boundaries are
> preserved.

### 5.1 Why a wrapper (informative)

A wrapper rather than a symlink or copy was chosen because it: keeps every byte
inside the root (no escape-policy interaction, `runtime.md` §6.6.4); pins and
documents the absolute host path; survives the host command moving on `PATH`
(reinstall to repoint); and is human-inspectable — the whole definition is three
lines. Copies would bloat the root and break dynamically linked or multi-file
tools; bare `env/path` entries to a host `bin` would expose every command in that
directory rather than the one chosen.

### 5.2 Install Record

> [CI-7] The install record is a single line of the form
> `# wash-install:<v> <key>=<value> ...` immediately following the shebang. `<v>`
> is the record-format version (currently `1`). Defined keys:
>
> | key        | meaning |
> |------------|---------|
> | `name`     | the wash command name *N* |
> | `host`     | resolved absolute host path |
> | `origin`   | how the host command was found: `explicit` (`--from`), `path` (host `PATH`), or `registry` |
> | `installed`| ISO-8601 UTC timestamp of the install |
>
> Values are whitespace-free; the record uses the metadata line grammar of
> `pipeline_parsing.md` §5.5. Unknown keys are ignored by readers.

The presence of a `# wash-install:` record is what marks a command file as
installer-managed. Listing and removal (§9) rely on it; a hand-authored command
file without the record is never enumerated or removed by the installer.

## 6. Search-Path Management

> [CI-8] The command directory *D* must appear as a line in `R/env/path` after an
> install. If `R/env/path` is absent it is created containing *D*. If present and
> *D* is not already listed (matched as the verbatim line, after stripping), *D*
> is appended as a new final line. Existing lines, ordering, comments, and
> entries that point outside the root (`runtime.md` §7.1) are preserved.

The reference runtime applies **no** default search path: with no `env/path`, a
root has zero command directories. An installer therefore must write `env/path`
rather than relying on an implicit `bin`.

## 7. Metadata

Command metadata (`runtime.md` §7.3, fields in `pipeline_parsing.md` §5.6) is
optional; the runtime applies defaults for absent fields. An installer writes
`R/env/meta/N` only when it has a real hint, never speculative values.

> [CI-9] Metadata is written when (a) the caller supplies explicit fields, or (b)
> the bundled metadata-hints overlay (§8.3) has an entry for the command. Sources
> compose with caller-supplied fields taking precedence. When neither applies, no
> metadata file is written and runtime defaults govern.

> [CI-10] A written metadata file uses the grammar of `pipeline_parsing.md` §5.5
> and contains only the recognized fields of §5.6 (`arity input output methods
> mime mutates parse-mode stderr exit`). It carries a leading
> `# wash-install:<v>` comment so it can be recognized and removed with its
> command (§9).

## 8. Registry

The registry is the catalog vendored from `tools.toml` (source of truth) and its
generated `tools.json`. It is **bundled with the installer** and used for three
purposes: resolving a friendly name to a host command, suggesting an install
command when one is missing (§4.1, [CI-4]), and supplying metadata hints (§7).
Arbitrary host commands not in the registry remain installable by name or
`--from`.

### 8.1 Catalog Schema (per entry)

From `tools.toml` (`generate.py` documents the authoritative schema):

| field      | meaning |
|------------|---------|
| `name`     | display/command name, may include alternates, e.g. `ripgrep (rg)` |
| `role`     | what the tool does (primary search axis) |
| `group`    | redundancy cluster — pick at most one per group for a job |
| `avail`    | `posix` (preinstalled) · `pkg` (one install) · `heavy` (large dep/model) |
| `baseline` | part of the curated install-once set |
| `brew`     | Homebrew formula (or a `#`-prefixed note when not via brew) |
| `apt`      | Debian/Ubuntu package (or a `#`-prefixed note) |
| `when`     | disambiguation / when to reach for it |

### 8.2 Name and Alias Resolution

> [CI-11] The registry index maps lookup tokens to entries. Tokens for an entry
> are derived from its `name` (the leading word, plus any parenthesized
> alternates such as `rg` in `ripgrep (rg)` and any `/`-separated alternates such
> as `xxd`, `hexdump`, `od`) together with its `brew` and `apt` package names.
> Lookup is exact on a token first; search (`search <query>`) additionally matches
> substrings of `name`, `role`, and `when`.

Parenthesized text that is a disambiguator rather than a command (e.g.
`yq (mikefarah)`) is treated as a token too; a false token merely never matches a
real host command and is harmless.

### 8.3 Metadata Hints Overlay

Because the catalog schema (§8.1) carries no runtime-metadata fields, derivable
metadata (§7) comes from a small, separately maintained overlay bundled with the
installer: `washinstall/catalog/meta_hints.toml`. Each entry keys a command
basename to a subset of the §5.6 fields. The overlay is intentionally
conservative — it holds only fields that are true for the tool independent of how
it is invoked (e.g. a default output `mime`). It is extensible without changing
this spec.

## 9. Listing and Removal

> [CI-12] `list` enumerates, for a root, every command file across the
> directories in `R/env/path` whose first lines carry a `# wash-install:` record
> (§5.2), reporting at least name, host path, and whether the host path currently
> resolves to an executable.

> [CI-13] `remove N` deletes the installer-managed wrapper for *N* and its
> `env/meta/N` file when that metadata also carries the `# wash-install:` marker.
> A command file lacking the marker is never removed (it was not installer-made);
> removal of such a name is refused. `env/path` is left untouched, since other
> commands may rely on the directory.

## 10. Idempotency and Exit Status

> [CI-14] Re-installing the same name is refused unless `--force` is given; with
> `--force` the wrapper and metadata are overwritten. A refused install changes
> nothing and exits non-zero.

> [CI-15] Exit status is `0` on a completed install/list/remove, non-zero on any
> error (unresolved host command, refused overwrite, removal of an unmanaged
> file). The package-suggestion path ([CI-4]) exits non-zero — installation did
> not occur — while still printing the actionable suggestion.

## 11. Security Considerations

- Installation never runs a host package manager or any host command (§4.1); it
  only writes files into the root.
- A wrapper executes whatever absolute path it records. Inspect the install
  record before trusting a root authored elsewhere.
- The runtime's command search path may point outside the root (`runtime.md`
  §7.1); wrappers keep the *definition* inside the root but the *target* is an
  arbitrary host path. This is intentional and matches the runtime's stance that
  the root is a content root, not a hard execution sandbox (`runtime.md` §3, §5).

## 12. Out of Scope

Mutating the host (installing packages), command signing/trust/quarantine,
sandboxed execution, and guaranteed portability of a produced root to another
machine. These mirror the runtime non-goals (`runtime.md` §3) and may be layered
on later without changing the artifacts defined here.
