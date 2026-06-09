# wash / Web Shell

A local HTTP server that maps URLs to a project root directory — files, directories,
and composable command pipelines.

## Specifications

- [`specs/runtime.md`](specs/runtime.md) — core runtime contract
- [`specs/pipeline_parsing.md`](specs/pipeline_parsing.md) — URL pipeline parsing addendum
- [`specs/audit.md`](specs/audit.md) — v1 open-question tracker

## Conformance harness

The [`harness/`](harness/) package is a language-neutral evaluation harness (see
[`harness/DESIGN.md`](harness/DESIGN.md)). It launches implementations over HTTP
against a versioned root-directory corpus and declarative YAML vectors.

```bash
# Install harness + reference implementation
pip install -e ./harness[dev]
pip install -e ./impls/reference

# Validate the corpus and run conformance
wash-conformance validate-roots
wash-conformance validate-vectors
wash-conformance run --adapter harness/adapters/reference.toml
```

## Reference implementation

[`impls/reference/`](impls/reference/) is a minimal Python wash server launched only
through the harness adapter manifest — not imported by the harness.

```bash
pip install -e ./impls/reference
python -m wash.server --root /path/to/root --port 8080
```
