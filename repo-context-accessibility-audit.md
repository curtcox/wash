# Repo Context Accessibility Audit

Audited on 2026-06-09. Scope: root docs, top-level layout, harness tooling, conformance vectors, reference implementation, CI, and local agent-facing config.

## What Already Works

- The human-facing README concisely explains the project and gives install/conformance commands (`README.md:1-37`).
- The specs define core domain terms directly in the source of truth (`specs/runtime.md:60-159`) and track v1 open questions (`specs/audit.md:1-32`).
- The harness has stable schemas and clause IDs, which is excellent for agent navigation (`harness/vector.schema.json:1-35`, `harness/conformance/spec.py:1-35`).
- CI already encodes the canonical validation and conformance sequence (`.github/workflows/conformance.yml:16-23`, `.github/workflows/conformance.yml:33-38`).

## Do These First

1. Add a root `AGENTS.md` with commands, map, and gotchas.
2. Add a `Makefile` that wraps the canonical install/validate/test loops.
3. Update or retire stale `harness/PLAN.md` planning language.
4. Add `harness/AGENTS.md` for vector/corpus authoring rules.
5. Label the corpus rebuild script and generated fixture family.

## Prioritized Recommendations

1. **Add `AGENTS.md` with build/test commands**  
   Effort: S. Payoff: High.  
   Gap: there is no root `AGENTS.md` or `CLAUDE.md`; the root docs found are `README.md`, `.gitignore`, and project files. The README has install/run commands (`README.md:18-27`) but not edit boundaries, gotchas, or fast loops.  
   First step: create `AGENTS.md` at repo root with the draft below.

   ````markdown
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
   - `harness/roots/_lib/exit*.sh` and `exit*.py` are generated on demand and intentionally ignored.
   - The default local Python may not have harness dependencies until the editable installs above are run.
   ````

2. **Add a `Makefile` with canonical task names**  
   Effort: S. Payoff: High.  
   Gap: commands are repeated between README and CI (`README.md:18-27`, `.github/workflows/conformance.yml:16-23`, `.github/workflows/conformance.yml:33-38`), but there is no `Makefile`, `justfile`, or package-level aggregate script in the root file scan.  
   First step: add this root `Makefile`.

   ```makefile
   .PHONY: install validate test conformance coverage smoke-reference

   install:
   	pip install -e ./harness[dev]
   	pip install -e ./impls/reference

   validate:
   	wash-conformance validate-roots
   	wash-conformance validate-vectors
   	wash-conformance validate-capabilities harness/adapters/reference.toml
   	wash-conformance coverage

   conformance:
   	wash-conformance run --adapter harness/adapters/reference.toml

   test: validate conformance

   coverage:
   	wash-conformance coverage

   smoke-reference:
   	python -m wash.server --root harness/roots/plain-files --port 8080
   ```

3. **Update or retire stale `harness/PLAN.md` planning language**  
   Effort: S. Payoff: High.  
   Gap: `harness/PLAN.md` still says “Status: planning” and “No harness code is written yet” (`harness/PLAN.md:8-10`), but the harness package exists and CI installs/runs it (`harness/pyproject.toml:21-25`, `.github/workflows/conformance.yml:16-23`). This is a high-risk stale doc because it looks authoritative.  
   First step: change the opening to:

   ```markdown
   Status: implemented draft. This document began as the architecture plan and now records design contracts for the Python conformance harness in `harness/conformance/`, the root corpus in `harness/roots/`, and adapter manifests in `harness/adapters/`.

   For day-to-day agent orientation, start with `../AGENTS.md` and `AGENTS.md` in this directory. Keep this file focused on durable architecture and contract rationale; do not use it as the canonical command list.
   ```

4. **Add `harness/AGENTS.md` for vectors, roots, and adapters**  
   Effort: S. Payoff: High.  
   Gap: top-level `harness/` contains schemas, code, fixtures, adapters, and scripts; only `PLAN.md` exists under `harness/` (`harness/PLAN.md:44-64`), and it is long plus stale. Agents need a short scoped map.  
   First step: create `harness/AGENTS.md` covering vector schema, root materialization, destructive script, and adapter invariants.

5. **Label the corpus rebuild script and generated fixture family**  
   Effort: S. Payoff: High.  
   Gap: `harness/scripts/rebuild_corpus.py` removes and rewrites many roots with `shutil.rmtree` (`harness/scripts/rebuild_corpus.py:47-65`, `harness/scripts/rebuild_corpus.py:302-321`). `_lib/exit*.sh` and `_lib/exit*.py` are generated on demand (`harness/conformance/rootcorpus.py:130-153`) and ignored (`.gitignore:53-58`), but that is not visible near the script or `_lib` directory.  
   First step: add a top-of-file warning to `rebuild_corpus.py` and a small `harness/roots/_lib/README.md`.

6. **Add a minimal `CLAUDE.md` that imports `AGENTS.md`**  
   Effort: S. Payoff: Med.  
   Gap: `.claude/settings.local.json` exists but is ignored local config (`.gitignore:50-51`, `.claude/settings.local.json:1-10`); there is no shared Claude-facing entry point.  
   First step: add `CLAUDE.md` with `@AGENTS.md` plus any Claude-specific command preference notes.

7. **Document the harness/reference package boundary in a greppable place**  
   Effort: S. Payoff: High.  
   Gap: the invariant exists deep in `PLAN.md` (`harness/PLAN.md:72-79`) and the adapter launches the reference via TOML (`harness/adapters/reference.toml:1-9`), but agents modifying imports need to see “never import `wash` from `conformance`” early.  
   First step: put this in root `AGENTS.md` and `harness/AGENTS.md`; optionally add a small import-boundary check later.

8. **Record the dependency bootstrap before test commands**  
   Effort: S. Payoff: High.  
   Gap: `harness` requires `pytest`, `pyyaml`, and `jsonschema` (`harness/pyproject.toml:11-19`), while the reference package has no deps (`impls/reference/pyproject.toml:5-10`). In this checkout, `python3 -m pytest harness/tests` failed before install because `pytest` was missing.  
   First step: in `AGENTS.md`, make `pip install -e ./harness[dev]` and `pip install -e ./impls/reference` the first setup block.

9. **Document fast conformance filters**  
   Effort: S. Payoff: High.  
   Gap: the CLI supports root/tier/clause filters and reports (`harness/conformance/cli.py:124-133`), but README only shows the full run (`README.md:23-27`).  
   First step: add the filtered examples from the draft `AGENTS.md`.

10. **Add a vector authoring checklist**  
   Effort: S. Payoff: Med.  
   Gap: vectors are schema-validated and must cite clauses (`harness/vector.schema.json:7-35`), and sample vectors show the pattern (`harness/conformance/vectors/precedence.yaml:1-9`), but there is no short “when adding a vector, also update root fixtures/capability gates” checklist.  
   First step: put a 6-line checklist in `harness/AGENTS.md`.

11. **Name corpus roots as test fixtures, not sample apps**  
   Effort: S. Payoff: Med.  
   Gap: root corpus directories contain executable scripts and data; only three root READMEs explain synthesis (`harness/roots/synthesized/README.txt:1`, `harness/roots/symlinks/README.txt:1`, `harness/roots/case/README.txt:1`).  
   First step: add `harness/roots/AGENTS.md` saying each directory is a canonical fixture root and should be changed with matching vector diffs.

12. **Add `.editorconfig` for low-level file style**  
   Effort: S. Payoff: Med.  
   Gap: there is no root `.editorconfig`; Python package configs only define pytest options (`harness/pyproject.toml:31-39`), and fixture files include many extensionless shell/data files where trailing whitespace/newline rules matter.  
   First step: add UTF-8, LF, final-newline, trim-trailing-whitespace defaults, with overrides for binary/base64 fixture files if needed.

13. **Add minimal formatter/linter commands once the preferred tools are chosen**  
   Effort: M. Payoff: Med.  
   Gap: no ruff/black/mypy config is present; `.gitignore` only ignores caches (`.gitignore:29-32`). Avoid documenting style by prose if tooling can enforce it.  
   First step: ask maintainers whether to use Ruff format/lint or Black+Ruff, then add config and `make lint`/`make format`.

14. **Document platform-sensitive fixture behavior**  
   Effort: S. Payoff: Med.  
   Gap: symlink and case fixtures are synthesized based on capabilities and host filesystem (`harness/conformance/rootcorpus.py:203-215`), and spec audit R7 calls out case sensitivity as an unresolved gap (`specs/audit.md:22-29`).  
   First step: add a “Platform notes” subsection in `harness/AGENTS.md`.

15. **Record commit and PR conventions if maintainers have them**  
   Effort: S. Payoff: Low.  
   Gap: recent commits are plain imperative-ish subjects, not a strict conventional-commit format; no PR template or active hooks are present beyond samples in `.git/hooks`.  
   First step: add one sentence to `AGENTS.md` only if maintainers want a convention; otherwise say “No strict commit format.”

## Do Not Do

- Do not create per-directory READMEs everywhere. Root `AGENTS.md`, `harness/AGENTS.md`, and maybe `harness/roots/AGENTS.md` are enough for this repo.
- Do not duplicate the full specs into agent docs. Link to `specs/runtime.md` and `specs/pipeline_parsing.md`; they already define the domain well.
- Do not add a heavy MCP server or custom agent plugin yet. The repeated workflows are simple shell commands and fit a `Makefile`.
- Do not document style rules in prose before choosing/enforcing a formatter or linter.
- Do not turn `harness/PLAN.md` into the main onboarding doc; it is too long and should remain architecture/rationale.

## Questions For A Maintainer

- Should `harness/PLAN.md` remain a living architecture doc, be renamed to `DESIGN.md`, or move under `docs/archive/`?
- Which formatter/linter should become canonical: Ruff-only, Black+Ruff, or something else?
- Is there an intended commit message or PR title format?
- Are there known flaky/slow vectors beyond the timeout behavior documented in `harness/PLAN.md`?
- Should agents ever run `harness/scripts/rebuild_corpus.py`, or should root fixture changes be manual unless explicitly requested?
- Is there an issue tracker, project board, release process, or deployment/dashboard URL that should be linked from `AGENTS.md`?
