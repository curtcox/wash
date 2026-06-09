# AGENTS.md

## Scope
Each subdirectory is one independent `wash` implementation. `reference/` is the minimal Python server. Implementations are black boxes to the harness: it launches them over HTTP via an adapter manifest and never imports their code.

## Adding an implementation
1. Create `impls/<name>/` containing a server that speaks the `wash` HTTP contract in `specs/runtime.md` and `specs/pipeline_parsing.md`.
2. Declare its capabilities in `impls/<name>/wash.capabilities.json` (validated against `harness/capabilities.schema.json`).
3. Add `harness/adapters/<name>.toml` with an argv `start` command; paths are relative to the repo root.
4. Run `wash-conformance validate-capabilities harness/adapters/<name>.toml`, then `wash-conformance run --adapter harness/adapters/<name>.toml`.

## Boundary
Implementations must not import or be imported by the harness. The harness treats yours exactly as it treats a third-party server.
