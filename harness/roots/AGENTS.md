# AGENTS.md

## Fixture Roots
Each top-level directory under `harness/roots/` is a canonical fixture root used by conformance vectors. Treat these files as test data, not sample apps.

When changing a fixture root, update or add the matching vector in `harness/conformance/vectors/` and keep clause coverage in sync with `harness/conformance/spec.py`.

Mutation tests run against materialized temp copies. Do not run ad hoc destructive requests against these canonical roots unless the change itself is the fixture edit you intend to keep.

Some fixtures, especially case and symlink roots, are synthesized or adjusted by `harness/conformance/rootcorpus.py` to match host capabilities.
