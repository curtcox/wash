# AGENTS.md

## Project Shape
`wash` is a local HTTP server/specification that maps URL paths to a project root: files, directories, and composable command pipelines. The source-of-truth behavior is in `specs/runtime.md` and `specs/pipeline_parsing.md`.

Domain terms (corpus, root, vector, clause, tier, adapter, capability, materialize) are defined in the glossary in `harness/AGENTS.md`.

## Where Code Lives
- `specs/`: normative runtime and parsing specs plus the v1 open-question audit.
- `harness/conformance/`: Python conformance harness and CLI.
- `harness/conformance/vectors/`: declarative YAML test vectors. Each vector should cite stable clause IDs from `harness/conformance/spec.py`.
- `harness/roots/`: canonical fixture root corpus. Treat fixture contents as test data, not app code.
- `harness/shared/`: fixtures shared across roots — e.g. command dirs that live *outside* a served root (used by the `path-outside` vectors). Materialized as a sibling bundle so `../shared/bin` entries resolve. Test data, not app code.
- `harness/scripts/rebuild_corpus.py`: destructive corpus rewrite helper; inspect diffs carefully after running.
- `impls/`: one subdirectory per implementation. `impls/reference/` is the Python reference server (see `impls/reference/AGENTS.md`); additional language impls (bash, deno, go, groovy, java, lua, perl, ruby, rust, swift, …) are planned and slot in alongside it. Every impl is launched through its own `harness/adapters/*.toml`, never imported by the harness.

## Setup
```bash
pip install -e ./harness[dev]
pip install -e ./impls/reference
```

## Common Commands (prefer these)
Run from the repo root. Targets live in `Makefile`.

| Task                 | Command            |
|----------------------|--------------------|
| Install (editable)   | `make install`     |
| Validate corpus      | `make validate`    |
| Unit/self-tests      | `make unit`        |
| Lint + format check  | `make lint`        |
| Auto-format + fix    | `make format`      |
| Type-check           | `make typecheck`   |
| Conformance run      | `make conformance` |
| Everything (CI gate) | `make test`        |

`make test` is what CI enforces (`.github/workflows/conformance.yml`, Python 3.12):
validate + harness self-tests + `make lint` + `make typecheck` + conformance. Run
it before pushing. For tighter loops, see "Fast Loops" below.

## Change Propagation
Behavior is defined in four places that must stay in sync:
`specs/*.md` (normative) → clause IDs in `harness/conformance/spec.py` →
vectors in `harness/conformance/vectors/*.yaml` → each implementation under
`impls/`. Change one corner, update the others or conformance fails. When an
implementation and the spec disagree, resolve it case by case; the long-term
goal is zero differences across all implementations.

## Fast Loops
```bash
wash-conformance run --adapter harness/adapters/reference.toml --root precedence
wash-conformance run --adapter harness/adapters/reference.toml --tier MUST
wash-conformance run --adapter harness/adapters/reference.toml --clause PP-4-implied-cat
python -m wash.server --root harness/roots/plain-files --port 8080  # blocks until Ctrl-C
```

The last command (and `make smoke-reference`) starts a server in the foreground and
holds the port until interrupted — run it in a background shell if you need to issue
requests against it from the same session.

## Gotchas
- Keep `harness` and `impls/reference` as separate packages; `conformance` must not import `wash`.
- Mutation vectors are run against materialized temp copies; do not point ad hoc tests at canonical corpus roots unless they are read-only.
- Some case and symlink fixtures are synthesized at materialization time.
- `harness/roots/_lib/exit*.sh` and `harness/roots/_lib/exit*.py` are generated on demand and intentionally ignored.
- The default local Python may not have harness dependencies until the editable installs above are run.
- Supported Python starts at 3.11, CI currently runs 3.12, and local environments may be newer; avoid syntax or stdlib behavior that would fail on the support floor or CI version.
- No strict commit format is enforced. Default to a concise imperative subject line (e.g. "Add path-outside vector"); body optional.
