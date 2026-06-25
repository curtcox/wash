# Change Propagation: SDT Name Resolution + Escape-Policy Consolidation

Status tracker for propagating two coupled changes across implementations, per
the Change Propagation discipline in `AGENTS.md` (specs → clauses → vectors →
each impl).

## What changed

1. **Name resolution (`runtime.md` §6.6).** Any directory may carry a `c` naming
   file mapping names to target paths; a name with no literal child resolves
   through the scope chain and stands in for a path segment in a URL, for every
   HTTP method. New normative behavior — a change to core path resolution, not a
   layer on top of it.
2. **Escape-policy consolidation.** The former `symlink_policy` capability is
   renamed to **`escape_policy`** (same values: `reject-escaping | follow |
   unsupported`) and now governs **both** symlink *and* name-target escapes. Two
   new declarative capability keys were added: `name_resolution` (boolean) and
   `name_resolution_max_depth` (integer).

The reference implementation (`impls/reference/`) and the `sdt` linter
(`tools/sdt/`) are complete. The Go and Dart implementations are **not yet
propagated**.

## Why the Go/Dart gates will now fail

The `harness/conformance/vectors/names.yaml` MUST vectors gate on
`requires_capability: { path: name_resolution, equals: true }`. A MUST vector
whose capability gate is unmet is recorded as **UNTESTED**, and a MUST UNTESTED
**fails the conformance gate** (`harness/conformance/report.py` `gate_failed`).
There is no honest shortcut: you cannot dodge a MUST vector by leaving a
capability undeclared. The only conformant path is to **implement §6.6 and
declare `name_resolution: true`** (plus `name_resolution_max_depth`).

The escape-policy rename itself is declaration-only for Go/Dart: their
`wash.capabilities.json` key was renamed `symlink_policy` → `escape_policy`
(value unchanged), and the symlink vectors now gate on `escape_policy`. Their
existing symlink behavior already satisfies those gates, so no symlink behavior
change is required — only the new name-resolution behavior is.

## Per-implementation status

| Implementation | escape_policy rename | §6.6 name resolution | `name_resolution` declared | Conformance |
|----------------|----------------------|----------------------|----------------------------|-------------|
| `reference` (Python) | done | done | `true` | 136/136 MUST pass |
| `go`           | done (declaration) | **TODO** | `false`/absent | will fail names MUST until implemented |
| `dart`         | done (declaration) | **TODO** | `false`/absent | will fail names MUST until implemented |

## Implementation checklist (Go, Dart, future impls)

Behavior to add (clause IDs in `harness/conformance/spec.py`, vectors in
`names.yaml`):

- [ ] **Scope-chain walk** — on a literal-child miss, consult the `c` files from
  root down to the current node, nearest (deepest) first. `RT-6.6-resolve-scope`.
- [ ] **Literal child shadows name** — a name colliding with a real entry
  (incl. `a`/`b`/`c`) is inert. `RT-6.6-literal-precedence`.
- [ ] **Nearest-wins shadowing** across scopes. `RT-6.6-nearest-wins`.
- [ ] **Jump + rebuild scope from the target** — a resolved name behaves as if
  the URL had been the target path. `RT-6.6-jump-scope`.
- [ ] **Chaining** — a target may itself be/contain a name; resolve to a
  fixpoint. `RT-6.6-chain`.
- [ ] **Shared depth budget** across name *and* symlink hops; overflow / cycle →
  **508**. `RT-6.6-loop-bound`.
- [ ] **Dangling** target (absent, or all alternatives dangling) → **404**.
  `RT-6.6-dangling`.
- [ ] **Escape policy** — a name/symlink target outside root is governed by
  `escape_policy`; default `reject-escaping` → **403**. `RT-6.6-escape-policy`.
- [ ] **Graceful `c`** — absent/empty/malformed `c` is ignored, never 500.
  `RT-6.6-c-graceful`.
- [ ] **All methods** — GET/HEAD/POST/DELETE resolve names; PUT overwrites a
  resolved existing target, else creates literally (names address existing
  resources; creation is literal). `RT-6.6-all-methods`.
- [ ] **Provenance header** (optional) — `X-WebShell-Resolved-Path` on responses
  served through name/symlink hops. `RT-6.6-provenance`.
- [ ] Declare `name_resolution: true` and `name_resolution_max_depth` in
  `wash.capabilities.json`.

### Fixtures & tooling

- The `names` corpus root (`harness/roots/names/`) is the shared fixture; its
  out-of-root escape target is synthesized at materialization time
  (`harness/conformance/rootcorpus.py`), never checked in.
- Run `python -m sdt check <root>` (or `make sdt-test`) — the static linter that
  detects cycles/dangling and inventories escapes, the offline companion to the
  runtime behavior above.

### Verify

```bash
wash-conformance run --adapter harness/adapters/<impl>.toml --root names
wash-conformance run --adapter harness/adapters/<impl>.toml --root symlinks
```

Both roots are now governed by the single `escape_policy` axis.
