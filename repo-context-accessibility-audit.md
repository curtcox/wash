# Repo Context Accessibility Audit (Second Pass)

Audited 2026-06-09. Scope: root docs, top-level layout, harness tooling,
conformance vectors, reference implementation, CI, and local agent-facing config.
Every claim below was checked against the file on disk; paths and line numbers
are cited so they can be re-verified.

## Context: this is a second pass

A first accessibility pass already landed (commits `e3c59a3`, `864269a`,
`8d34ba2`). I re-verified its claims rather than trusting them, and they hold:

- Root [`AGENTS.md`](AGENTS.md), [`CLAUDE.md`](CLAUDE.md) (imports `@AGENTS.md`),
  [`harness/AGENTS.md`](harness/AGENTS.md), and
  [`harness/roots/AGENTS.md`](harness/roots/AGENTS.md) all exist and orient well.
- [`Makefile`](Makefile) wraps install/validate/conformance/coverage/smoke.
- [`.editorconfig`](.editorconfig), [`harness/roots/_lib/README.md`](harness/roots/_lib/README.md),
  and the rebuild-script warning (`harness/scripts/rebuild_corpus.py:1`) are present.
- The import-boundary self-test exists (`harness/tests/test_self.py:15`).
- The package boundary (`conformance` must not `import wash`) is stated in both
  [`AGENTS.md`](AGENTS.md) and [`harness/AGENTS.md:7`](harness/AGENTS.md).

So this pass focuses on **what the first pass missed or left open**. The headline
finding: the safety rail the first pass was proudest of — the import-boundary
self-test — never actually runs. Several recommendations below are small but
fix genuine gaps; the repo is otherwise in good shape for its size and stage.

## What still works well (don't "improve" these away)

- The spec is the source of truth and already defines runtime domain terms in a
  greppable section (`specs/runtime.md:132`, "## 5. Terminology").
- Clause IDs are stable and carry their source section inline
  (`harness/conformance/spec.py:25` onward, each `Clause(... "runtime §6.2" ...)`).
- The three-tier `AGENTS.md` layout (root → harness → roots) is exactly the
  scoped-doc pattern this audit recommends; resist adding more.
- `.gitignore` is unusually well-commented, including a macOS case-insensitive-FS
  trap for `env/` fixtures (`.gitignore:11`) and the generated `exit*` family
  (`.gitignore` "wash conformance harness" block).

---

## Prioritized recommendations

### 1. Wire `harness/tests/` into CI and the Makefile
- **Effort: S · Payoff: High**
- Gap: the import-boundary guard (`harness/tests/test_self.py`) and the
  pytest-wrapped validators it imports are **never executed automatically**.
  [`Makefile:16`](Makefile) defines `test: validate conformance` (no pytest), and
  [`.github/workflows/conformance.yml`](.github/workflows/conformance.yml) runs
  only `validate-*`/`coverage`/`run` — `grep pytest Makefile .github` returns
  nothing. The first pass added this safety rail (its recommendation #15) but
  left it inert, so a regression that makes `conformance` import `wash` would
  pass CI.
- First step: add a `unit` Make target and a CI step (draft below).

### 2. Add a harness glossary
- **Effort: S · Payoff: Med**
- Gap: `specs/runtime.md:132` defines *runtime* terms, but the harness vocabulary
  an agent must understand to edit it — **vector, clause, tier, adapter,
  capability, materialize, synthesized root, corpus** — is scattered across
  `harness/PLAN.md` prose with no single greppable definition list. These words
  appear in nearly every harness file and vector.
- First step: add a `## Glossary` section to [`harness/AGENTS.md`](harness/AGENTS.md)
  (draft below).

### 3. Add `impls/AGENTS.md` for adding a new implementation
- **Effort: S · Payoff: Med**
- Gap: the entire point of the project is multiple implementations conforming to
  the spec, but `impls/` contains only `reference/` and has no note on how to add
  a second implementation or wire its adapter. An agent asked to "add a Go
  implementation" would have to reverse-engineer the pattern from
  `harness/adapters/reference.toml` and `impls/reference/pyproject.toml`.
- First step: add [`impls/AGENTS.md`](impls/AGENTS.md) (draft below).

### 4. Add lint / format / type-check tooling and Make targets
- **Effort: M · Payoff: Med**
- Gap: no Ruff/Black/mypy config exists, and there are no `make lint`/`make
  format`/`make typecheck` targets — yet `.gitignore` already lists
  `.ruff_cache/` and `.mypy_cache/`, signaling the intended stack. Without
  enforced style, agents will reformat inconsistently and re-litigate choices.
- First step: confirm Ruff + mypy with the maintainer (the `.gitignore` hint),
  then add config to `harness/pyproject.toml` / `impls/reference/pyproject.toml`
  and `lint`/`format`/`typecheck` Make targets. Prefer enforcing in a linter over
  prose in `AGENTS.md`, per audit rules.

### 5. Document the Python version landscape as a gotcha
- **Effort: S · Payoff: Low/Med**
- Gap: three Python versions are in play and nothing says so: both packages
  declare `requires-python = ">=3.11"`, CI pins `3.12`
  (`.github/workflows/conformance.yml:15`), and the checked-in local venv is
  **3.14** (`.venv/lib/python3.14/`). An agent that hits a 3.14-only syntax or
  stdlib behavior will pass locally and break CI.
- First step: one bullet under `## Gotchas` in [`AGENTS.md`](AGENTS.md) stating
  the support floor (3.11), the CI version (3.12), and that local may be newer.
  Optionally add a CI version matrix (testing change, lower priority for context).

### 6. Decide whether `harness/PLAN.md` should be renamed to `DESIGN.md`
- **Effort: S · Payoff: Low**
- Gap: contents were corrected (`harness/PLAN.md:9` now says "implemented
  draft"), but the filename still reads as forward-looking planning. Carryover
  from pass 1; needs a maintainer decision before acting.
- First step: if maintainers agree, `git mv harness/PLAN.md harness/DESIGN.md`
  and update references in `README.md:14`, `AGENTS.md`, and `harness/AGENTS.md`.

### 7. Record PR / commit / release conventions (or confirm there are none)
- **Effort: S · Payoff: Low**
- Gap: [`AGENTS.md`](AGENTS.md) says no strict commit format is documented; PR
  title, branch naming, and release conventions are still unknown. Cannot be
  closed from the repo alone — see maintainer questions.
- First step: add one short section to `AGENTS.md` once the convention (if any)
  is provided.

---

## Do these first (top 5 — strict subset of the above)

These maximize payoff-per-effort: four are **S** effort, and #1 fixes a safety
rail that currently does nothing.

1. **Wire `harness/tests/` into CI and the Makefile** (S · High)
2. **Add a harness glossary** (S · Med)
3. **Add `impls/AGENTS.md`** (S · Med)
4. **Add lint / format / type-check tooling** (M · Med)
5. **Document the Python version landscape** (S · Low/Med)

### Draft content for the top 3

#### Top 1 — Make target + CI step

Add to [`Makefile`](Makefile) (and include `unit` in the `test` aggregate so the
documented "run the tests" command actually runs them):

```makefile
.PHONY: install validate test unit conformance coverage smoke-reference

unit:
	cd harness && python -m pytest -q

test: validate unit conformance
```

Add a step to the `validate` job in
[`.github/workflows/conformance.yml`](.github/workflows/conformance.yml) (the
`[dev]` extra already installs pytest, so no new install is needed):

```yaml
      - name: Harness self-tests
        run: cd harness && python -m pytest -q
```

#### Top 2 — Glossary section for `harness/AGENTS.md`

```markdown
## Glossary
- **Corpus**: the set of canonical fixture roots under `harness/roots/`.
- **Root**: one top-level directory in the corpus; the filesystem a wash server
  is pointed at for a group of vectors.
- **Vector**: a declarative YAML test case in `harness/conformance/vectors/`
  (request + expected response), validated against `harness/vector.schema.json`.
- **Clause**: a stable spec-requirement ID (e.g. `RT-6.2-precedence`) registered
  in `harness/conformance/spec.py`; each clause names its source spec section.
- **Tier**: a clause's strength — `MUST`, `SHOULD`, or `optional`.
- **Adapter**: a TOML launch manifest (e.g. `harness/adapters/reference.toml`)
  telling the harness how to start an implementation over HTTP.
- **Capability**: an implementation-declared feature flag
  (`*.capabilities.json`); vectors gate on these where the spec is
  implementation-defined.
- **Materialize**: copy/synthesize a root into a temp dir at run time — used for
  mutation vectors and for case/symlink fixtures that depend on host FS support.
- **Synthesized root**: a root produced at materialization time by
  `harness/conformance/rootcorpus.py` rather than stored verbatim on disk.
```

#### Top 3 — `impls/AGENTS.md`

```markdown
# AGENTS.md

## Scope
Each subdirectory is one independent `wash` implementation. `reference/` is the
minimal Python server. Implementations are black boxes to the harness: it
launches them over HTTP via an adapter manifest and never imports their code.

## Adding an implementation
1. Create `impls/<name>/` containing a server that speaks the `wash` HTTP
   contract in `specs/runtime.md` and `specs/pipeline_parsing.md`.
2. Declare its capabilities in `impls/<name>/wash.capabilities.json` (validated
   against `harness/capabilities.schema.json`).
3. Add `harness/adapters/<name>.toml` with an argv `start` command; paths are
   relative to the repo root.
4. Run `wash-conformance validate-capabilities harness/adapters/<name>.toml`
   then `wash-conformance run --adapter harness/adapters/<name>.toml`.

## Boundary
Implementations must not import or be imported by the harness. The harness
treats yours exactly as it treats a third-party server.
```

---

## Do not do

- **Don't add more per-directory READMEs/AGENTS.** The root + `harness/` +
  `harness/roots/` trio (plus a thin `impls/AGENTS.md`) is sufficient. A
  `specs/AGENTS.md` would duplicate `specs/runtime.md:132` terminology.
- **Don't copy spec text into agent docs.** Link to `specs/runtime.md` and
  `specs/pipeline_parsing.md`; the glossary above should point at them, not
  restate them.
- **Don't add an MCP server or custom plugin.** The repeated workflows are plain
  shell wrapped by the `Makefile`; that's the right altitude here.
- **Don't write style policy as prose.** If Ruff/mypy are adopted, enforce them
  in config + CI rather than describing rules in `AGENTS.md`.
- **Don't commit `.claude/`.** It's gitignored (`.gitignore` "Local tool
  configuration"); `settings.local.json` is per-developer permissions and should
  stay local.
- **Don't make agents run `harness/scripts/rebuild_corpus.py` routinely.** It is
  destructive; keep corpus edits manual unless regeneration is the explicit task.

## Questions for a maintainer

- Lint/type stack: confirm **Ruff + mypy** (implied by `.gitignore`), or another
  choice? Which directories should be in scope?
- Should `harness/PLAN.md` be renamed to `harness/DESIGN.md`?
- Are there PR title, commit message, branch naming, or release conventions to
  record in `AGENTS.md`?
- Should CI test a Python version **matrix** (3.11–3.14) given the `>=3.11`
  floor, or is 3.12 the only supported runtime?
- Should agents ever invoke `rebuild_corpus.py`, or must all root-fixture changes
  stay manual?
- Is `repo-context-accessibility-audit.md` meant to live at the repo root
  long-term, or move under `specs/`/`docs/` to keep the root lean?
```
