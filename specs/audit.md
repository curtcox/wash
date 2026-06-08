# Spec Audit: Remaining Issues

Last reviewed: 2026-06-08
Scope: `specs/runtime.md` and `specs/pipeline_parsing.md`.

The ambiguities and inconsistencies found in the 2026-06-08 audit have been
applied to both specs (see the "Resolved Questions" list in
`pipeline_parsing.md` §15 and "Resolved Design Decisions" in `runtime.md` §17).

The items below are the only ones that remain open. Each was resolved in the
specs by **deferring** a fuller treatment to a future version rather than fully
specifying it now, so they are tracked here as the v1 boundary.

| #  | Remaining issue | Current v1 disposition | Spec ref |
|----|-----------------|------------------------|----------|
| R1 | OPTIONS handling and CORS preflight responses are not governed by per-command `methods` metadata. | Implementation-defined in v1; cross-origin disabled by default. A future version should define preflight behaviour and how `methods`/`mutates` interact with `OPTIONS`. | runtime.md §9.5, §13.1 |
| R2 | Non-`stdin` `input` modes (`input file`, `input none`) and `output file`. | Reserved; requests resolving to a command that declares them return 500. Multi-resource commands work via arity + root-relative argv. A future version may define explicit file/none input and file output modes. | pipeline_parsing.md §5.3; runtime.md §10.5, §12.4 |
| R3 | Per-command working-directory override. | Default cwd is the root; no metadata field overrides it in v1. Reserved as a future metadata extension. | runtime.md §12.3 |
| R4 | Range / open-ended arity (`arity 1..3`, `arity 0..*`). | Reserved; malformed in v1 (500). Only fixed `N` and `*` are defined. | pipeline_parsing.md §5.2 |
| R5 | Quoting / escaping for metadata and `exec` values containing whitespace. | Out of scope in v1; tokens are whitespace-separated with no quoting. | pipeline_parsing.md §5.5; runtime.md §7.2 |
| R6 | Conventional `explain`/debug command and its output contract. | Optional in v1; if standardized later, the command name and plain-text/JSON output contract must be defined. | runtime.md §16.8 |
| R7 | Case sensitivity of command names and filesystem lookups on case-insensitive filesystems (e.g. macOS, Windows). | Not addressed; effectively implementation/host-filesystem-defined. A future version may specify a normalization policy. | — (gap) |
| R8 | HEAD for a command with an *explicit* `methods` list that includes GET but omits HEAD. §9.5 sentence 1 ("a command that permits GET also answers HEAD") and sentence 2 ("HEAD is suppressed only by listing methods that include GET but exclude HEAD") contradict each other for `methods GET`: sentence 1 says HEAD is answered, sentence 2 says it is suppressed. | Implementation-defined in v1; the conformance harness does not assert HEAD behavior for explicit-`methods` commands. Only the metadata-absent default (GET permitted ⇒ HEAD answered, body omitted), which §9.5 states unambiguously, is asserted. A future version must resolve which sentence governs an explicit GET-without-HEAD list. | runtime.md §9.5 |

## Notes

- R7 and R8 are genuine gaps in the current spec text — R7 is unaddressed, and R8
  is an internal contradiction in §9.5. The remaining items (R1–R6) are explicit v1
  "reserved / out of scope" boundaries already documented in the specs and repeated
  here for tracking.
- When any of these is taken up, move it out of this file and into the relevant
  spec's resolved-decisions list.
