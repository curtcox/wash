# Repo Context Accessibility Audit

Audited on 2026-06-09. Scope: root docs, top-level layout, harness tooling,
conformance vectors, reference implementation, CI, and local agent-facing config.

## Current State

The first accessibility pass has been applied. The repository now has short
agent-facing entry points, Makefile wrappers for canonical workflows, scoped
harness guidance, visible corpus-fixture warnings, and baseline editor settings.

## What Works Well

- The human-facing README concisely explains the project and gives install and
  conformance commands (`README.md`).
- The specs define core domain terms in the source of truth and track v1 open
  questions (`specs/runtime.md`, `specs/audit.md`).
- The harness has stable schemas and clause IDs for agent navigation
  (`harness/vector.schema.json`, `harness/conformance/spec.py`).
- CI encodes the canonical validation and conformance sequence
  (`.github/workflows/conformance.yml`).
- Root orientation is now explicit in `AGENTS.md`, including setup commands,
  canonical checks, fast loops, edit boundaries, and gotchas.
- `Makefile` now wraps install, validation, full conformance, coverage, and the
  reference-server smoke loop.
- Claude-facing orientation now exists via `CLAUDE.md`, which imports
  `AGENTS.md` and calls out command/package-boundary preferences.
- Harness-scoped rules now live in `harness/AGENTS.md`, including vector
  authoring, root corpus, rebuild-script, and adapter invariants.
- Fixture-root rules now live close to the corpus in `harness/roots/AGENTS.md`.
- Shared fixture-command generation is labeled in `harness/roots/_lib/README.md`.
- `harness/scripts/rebuild_corpus.py` now has a top-of-file warning that it
  removes and rewrites canonical fixture roots.
- `.editorconfig` now records UTF-8, LF, final-newline, and trailing-whitespace
  defaults, with binary-ish asset overrides.
- `harness/PLAN.md` now says it is an implemented-draft architecture/design
  contract, not a planning document claiming no harness exists.
- The documented harness/reference import boundary now has a self-test in
  `harness/tests/test_self.py`.
- The `empty` corpus root is now represented as a virtual materialized root, and
  vector validation now rejects references to unknown roots.

## Completed Recommendations

1. **Add root `AGENTS.md` with build/test commands**  
   Status: done. `AGENTS.md` includes project shape, code map, setup, canonical
   checks, fast loops, gotchas, package-boundary rules, generated fixture notes,
   and the current lack of a strict commit format.

2. **Add a `Makefile` with canonical task names**  
   Status: done. `Makefile` provides `install`, `validate`, `conformance`,
   `test`, `coverage`, and `smoke-reference`.

3. **Update stale `harness/PLAN.md` planning language**  
   Status: done. The opening now describes the file as durable architecture and
   contract rationale for the implemented draft harness.

4. **Add `harness/AGENTS.md` for vectors, roots, and adapters**  
   Status: done. It includes vector authoring, root corpus, corpus rebuild, and
   adapter invariants.

5. **Label the corpus rebuild script and generated fixture family**  
   Status: done. The rebuild script warning and `_lib/README.md` are present.

6. **Add minimal `CLAUDE.md` that imports `AGENTS.md`**  
   Status: done.

7. **Document the harness/reference package boundary in a greppable place**  
   Status: done. The invariant appears in both root and harness agent docs.

8. **Record dependency bootstrap before test commands**  
   Status: done. `AGENTS.md` puts editable installs before checks, and
   `Makefile install` mirrors them.

9. **Document fast conformance filters**  
   Status: done. Root, tier, and clause examples are in `AGENTS.md`.

10. **Add a vector authoring checklist**  
    Status: done in `harness/AGENTS.md`.

11. **Name corpus roots as test fixtures, not sample apps**  
    Status: done in `harness/AGENTS.md` and `harness/roots/AGENTS.md`.

12. **Add `.editorconfig` for low-level file style**  
    Status: done.

13. **Document platform-sensitive fixture behavior**  
    Status: done in `harness/AGENTS.md` and `harness/roots/AGENTS.md`.

14. **Record commit and PR conventions if maintainers have them**  
    Status: partially done. `AGENTS.md` records that no strict commit format is
    currently documented. PR conventions remain unknown.

15. **Consider an automated import-boundary check**  
    Status: done. `harness/tests/test_self.py` scans `harness/conformance/` with
    Python AST and fails if it imports `wash`.

16. **Ensure canonical validations catch vector/root mismatches**  
    Status: done. `harness/conformance/rootcorpus.py` exposes `empty` as a
    virtual root, and `harness/conformance/runner.py` validates vector root
    references against known roots.

## Remaining Recommendations

1. **Add minimal formatter/linter commands once preferred tools are chosen**  
   Effort: M. Payoff: Med.  
   Gap: no Ruff, Black, or mypy config is present yet, and no formatter/linter is
   listed in `Makefile`. Avoid inventing style policy without maintainer
   preference.  
   First step: choose Ruff-only, Black+Ruff, or another stack; then add
   dependency/config and `make lint`/`make format`.

2. **Decide whether `harness/PLAN.md` should be renamed**  
   Effort: S. Payoff: Low/Med.  
   Gap: the contents are now corrected, but the filename still implies future
   planning rather than implemented design.  
   First step: if maintainers agree, rename to `harness/DESIGN.md` and update
   references.

3. **Record PR/release conventions if they exist**  
   Effort: S. Payoff: Low.  
   Gap: no PR template, release process, issue tracker, project board, or strict
   title format is documented.  
   First step: add one short section to `AGENTS.md` only after maintainers provide
   the convention.

## Do Not Do

- Do not create per-directory READMEs everywhere. Root `AGENTS.md`,
  `harness/AGENTS.md`, and `harness/roots/AGENTS.md` are enough for this repo.
- Do not duplicate the full specs into agent docs. Link to `specs/runtime.md`
  and `specs/pipeline_parsing.md`; they already define the domain well.
- Do not add a heavy MCP server or custom agent plugin yet. The repeated
  workflows are simple shell commands and fit the current `Makefile`.
- Do not document formatter/linter policy in prose before choosing/enforcing a
  tool.
- Do not turn `harness/PLAN.md` into the main onboarding doc; it should remain
  architecture/rationale unless it is renamed to `DESIGN.md`.

## Questions For A Maintainer

- Which formatter/linter should become canonical: Ruff-only, Black+Ruff, or
  something else?
- Should `harness/PLAN.md` remain under that name or become `harness/DESIGN.md`?
- Is there an intended PR title, commit message, issue, or release convention?
- Should agents ever run `harness/scripts/rebuild_corpus.py`, or should root
  fixture changes stay manual unless explicitly requested?
