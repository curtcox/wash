# AGENTS.md

## Scope
This directory contains the Python conformance harness, schemas, adapter manifests, scripts, and canonical fixture roots. For repo-level setup and common commands, start with `../AGENTS.md`.

## Package Boundary
Keep the harness independent from every implementation. Code under `harness/conformance/` must not `import wash`; launch the reference implementation through `harness/adapters/reference.toml` the same way a third-party implementation is launched.

## Vector Authoring Checklist
- Put declarative tests under `harness/conformance/vectors/`.
- Validate each vector against `harness/vector.schema.json`.
- Cite stable clause IDs from `harness/conformance/spec.py`.
- Use existing fixture roots when possible; if a root changes, include the matching vector diff.
- Gate behavior with capability requirements when the spec makes it implementation-defined.
- Keep mutation vectors self-contained; the harness materializes temp copies for them.

## Root Corpus
`harness/roots/` is fixture data, not sample application code. Each top-level root is a canonical served filesystem for vectors, and changes should be reviewed as test-behavior changes.

Some roots are synthesized or adjusted by `harness/conformance/rootcorpus.py` during materialization. Case-sensitive and symlink behavior can depend on host filesystem capabilities, so vectors that rely on those features should use the existing capability and synthesis paths.

## Corpus Rebuild Script
`harness/scripts/rebuild_corpus.py` removes and rewrites many fixture roots. Run it only when intentionally regenerating the corpus, then inspect the full diff before keeping the result.

`harness/roots/_lib/exit*.sh` and `harness/roots/_lib/exit*.py` are generated on demand by the harness and intentionally ignored by git.

## Adapter Invariants
- Adapter manifests are declarative launch contracts; keep start commands as argv arrays.
- Paths in adapter manifests are relative to the repository root unless documented otherwise.
- Default adapter launches must not toggle behavior that conformance vectors assert as defaults.
