# sdt

Implementation-agnostic tooling for **Sequential Directory Trees** (SDT).

Today it provides the name-resolution linter — the static, whole-tree counterpart
to the per-request runtime name resolution defined in `specs/runtime.md` §6.6.

## `sdt check <root>`

Walks every `c` naming file under a root and reports:

| Finding | Severity | Meaning |
|---------|----------|---------|
| `name-cycle` | error | a name resolves through itself (combined name+symlink graph) |
| `dangling-target` | error | a name's only targets resolve to nothing |
| `escape-target` | warning | a target resolves outside the root (inventory, not a failure) |
| `c-malformed-line` | warning | a `c` line is not `name target...` |
| `c-duplicate-name` | info | a name is defined twice in one file (last wins) |

Exit status is non-zero when any **error** is present; escapes and malformed
lines are reported but do not fail, matching the policy in §6.6.3/§6.6.4.

```bash
python -m sdt check ../../harness/roots/names      # human-readable
python -m sdt check <root> --json                   # machine-readable
```

## Develop

```bash
cd tools/sdt && python -m pytest -q     # or: make sdt-test  (from repo root)
```

Stdlib-only; no install required (tests set `pythonpath = ["."]`).
