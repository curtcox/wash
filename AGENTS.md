# AGENTS.md

## Project Shape
`wash` is a local HTTP server/specification that maps URL paths to a project root: files, directories, and composable command pipelines. The source-of-truth behavior is in `specs/runtime.md` and `specs/pipeline_parsing.md`.

## Where Code Lives
- `specs/`: normative runtime and parsing specs plus the v1 open-question audit.
- `harness/conformance/`: Python conformance harness and CLI.
- `harness/conformance/vectors/`: declarative YAML test vectors. Each vector should cite stable clause IDs from `harness/conformance/spec.py`.
- `harness/roots/`: canonical fixture root corpus. Treat fixture contents as test data, not app code.
- `harness/scripts/rebuild_corpus.py`: destructive corpus rewrite helper; inspect diffs carefully after running.
- `impls/reference/wash/`: minimal Python reference server. The harness must launch it through `harness/adapters/reference.toml`, not import it.

## Setup
```bash
pip install -e ./harness[dev]
pip install -e ./impls/reference
```

## Canonical Checks
```bash
wash-conformance validate-roots
wash-conformance validate-vectors
wash-conformance validate-capabilities harness/adapters/reference.toml
wash-conformance coverage
cd harness && python -m pytest -q
wash-conformance run --adapter harness/adapters/reference.toml
```

## Fast Loops
```bash
wash-conformance run --adapter harness/adapters/reference.toml --root precedence
wash-conformance run --adapter harness/adapters/reference.toml --tier MUST
wash-conformance run --adapter harness/adapters/reference.toml --clause PP-4-implied-cat
python -m wash.server --root harness/roots/plain-files --port 8080
```

## Gotchas
- Keep `harness` and `impls/reference` as separate packages; `conformance` must not import `wash`.
- Mutation vectors are run against materialized temp copies; do not point ad hoc tests at canonical corpus roots unless they are read-only.
- Some case and symlink fixtures are synthesized at materialization time.
- `harness/roots/_lib/exit*.sh` and `harness/roots/_lib/exit*.py` are generated on demand and intentionally ignored.
- The default local Python may not have harness dependencies until the editable installs above are run.
- Supported Python starts at 3.11, CI currently runs 3.12, and local environments may be newer; avoid syntax or stdlib behavior that would fail on the support floor or CI version.
- No strict commit format is documented for this repo.
