# Repo Context Accessibility Audit

Recommended changes to make this repo easier for AI coding agents to understand,
navigate, and safely modify. Every claim was checked against the file on disk;
paths and line numbers are cited so they can be re-verified.

## Prioritized recommendations

### 1. Wire `harness/tests/` into CI and the Makefile — Done
- **Effort: S · Payoff: High**
- Previous gap: the import-boundary guard (`harness/tests/test_self.py`) and the
  pytest-wrapped validators it imports were not executed automatically.
- Implemented: added an overridable `PYTHON ?= python3` setting and `unit`
  target to [`Makefile`](../Makefile), included `unit` in `test`, and added a
  "Harness self-tests" CI step in
  [`.github/workflows/conformance.yml`](../.github/workflows/conformance.yml).

### 2. Add a harness glossary — Done
- **Effort: S · Payoff: Med**
- Previous gap: `specs/runtime.md` defines *runtime* terms, but the harness
  vocabulary an agent must understand to edit it — **vector, clause, tier,
  adapter, capability, materialize, synthesized root, corpus** — was scattered
  across the harness design prose with no single greppable definition list.
- Implemented: added a `## Glossary` section to
  [`harness/AGENTS.md`](../harness/AGENTS.md).

### 3. Add `impls/AGENTS.md` for adding a new implementation — Done
- **Effort: S · Payoff: Med**
- Previous gap: the project supports multiple implementations conforming to the
  spec, but `impls/` had no note on how to add a second implementation or wire
  its adapter.
- Implemented: added [`impls/AGENTS.md`](../impls/AGENTS.md).

### 4. Add lint / format / type-check tooling and Make targets — Done
- **Effort: M · Payoff: Med**
- Previous gap: no Ruff/mypy config existed, and there were no `make lint`/`make
  format`/`make typecheck` targets.
- Implemented: added Ruff + mypy dev dependencies/config in
  [`harness/pyproject.toml`](../harness/pyproject.toml) and
  [`impls/reference/pyproject.toml`](../impls/reference/pyproject.toml), added
  `lint`, `format`, and `typecheck` targets to [`Makefile`](../Makefile), and
  wired lint/typecheck into
  [`.github/workflows/conformance.yml`](../.github/workflows/conformance.yml).

### 5. Document the Python version landscape as a gotcha — Done
- **Effort: S · Payoff: Low/Med**
- Previous gap: multiple Python versions are in play: both packages declare
  `requires-python = ">=3.11"`, CI pins `3.12`, and local environments may be
  newer.
- Implemented: added a `## Gotchas` bullet in [`AGENTS.md`](../AGENTS.md)
  stating the support floor (3.11), the CI version (3.12), and that local
  environments may be newer. The optional CI version matrix remains a separate
  maintainer decision.

### 6. Rename `harness/PLAN.md` to `harness/DESIGN.md` — Done
- **Effort: S · Payoff: Low**
- Previous gap: the filename read as forward-looking planning, but the document
  described an implemented draft recording design contracts.
- Implemented: renamed the document to
  [`harness/DESIGN.md`](../harness/DESIGN.md) and updated references in
  [`README.md`](../README.md) and [`harness/pyproject.toml`](../harness/pyproject.toml).

### 7. Record PR / commit / release conventions (or confirm there are none)
- **Effort: S · Payoff: Low**
- Gap: [`AGENTS.md`](../AGENTS.md) says no strict commit format is documented; PR
  title, branch naming, and release conventions are still unknown. Cannot be
  closed from the repo alone — see maintainer questions.
- First step: add one short section to `AGENTS.md` once the convention (if any)
  is provided.

---

## Do these first (top 5 — strict subset of the above)

These maximize payoff-per-effort: four are **S** effort, and #1 fixes a safety
rail that currently does nothing.

1. **Wire `harness/tests/` into CI and the Makefile** (S · High) — Done
2. **Add a harness glossary** (S · Med) — Done
3. **Add `impls/AGENTS.md`** (S · Med) — Done
4. **Add lint / format / type-check tooling** (M · Med) — Done
5. **Document the Python version landscape** (S · Low/Med) — Done

### Completed changes

- Added an overridable Makefile Python setting, the `unit` Make target, included
  it in `test`, and wired the same pytest self-tests into CI.
- Added the harness glossary in `harness/AGENTS.md`.
- Added `impls/AGENTS.md` for new implementation authors.
- Added Ruff + mypy config, Make targets, and CI steps.
- Renamed `harness/PLAN.md` to `harness/DESIGN.md` and updated references.
- Documented the Python support floor and CI version in the root gotchas.

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

- Are there PR title, commit message, branch naming, or release conventions to
  record in `AGENTS.md`?
- Should CI test a Python version **matrix** (3.11–3.14) given the `>=3.11`
  floor, or is 3.12 the only supported runtime?
- Should agents ever invoke `rebuild_corpus.py`, or must all root-fixture changes
  stay manual?
