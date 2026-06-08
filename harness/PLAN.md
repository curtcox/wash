# wash Conformance Harness — Plan

> A language-neutral evaluation harness for `wash` (Web Shell) implementations.
> It launches any implementation against a corpus of root directories, drives it
> over HTTP, and reports how faithfully it implements `specs/runtime.md` and
> `specs/pipeline_parsing.md` — including where it falls short.

Status: planning. Scope of this document: architecture, contracts, the
root-directory corpus, the test taxonomy, and reporting. No harness code is
written yet.

---

## 1. Goals

1. **Language-neutral.** Test any implementation written in any language. The
   only coupling point is HTTP plus a thin launch contract.
2. **Spec-driven.** Every test traces to a numbered clause in `runtime.md` or
   `pipeline_parsing.md`. The suite is the executable form of the spec.
3. **Shortcoming detection.** Surface not just pass/fail but *where* and *why* an
   implementation diverges, with the offending clause cited.
4. **Many root directories.** The filesystem is the source of truth, so behavior
   is a function of root layout. The harness ships a corpus of purpose-built
   roots, and each test names the root it runs against.
5. **Honest about ambiguity.** The specs deliberately leave many areas
   implementation-defined (MIME inference, directory listings, synthesized
   resources, OPTIONS/CORS, symlink policy, case sensitivity). The harness
   separates normative conformance from implementation-defined behavior and never
   fails an implementation for a choice the spec permits.

### Non-goals

- Not a benchmark for speed/throughput (a latency smoke check is optional, §10).
- Not a security scanner (it does assert the spec's security *contract*, e.g. GET
  must not mutate, CORS off by default).
- Does not test future/reserved features (range arity, `input file`, cwd
  override) except to confirm they are rejected as the spec requires.

---

## 2. High-level architecture

```
harness/
  PLAN.md                  # this document
  pyproject.toml           # Python package + pytest entry points
  conformance/             # the harness itself (Python)
    runner.py              # orchestrates: pick impl × root, launch, run, collect
    adapter.py             # launch-command adapter contract + lifecycle
    httpclient.py          # raw request-target client (does NOT normalize URLs)
    rootcorpus.py          # materializes/validates root directories
    capabilities.py        # parse + apply an implementation's capability manifest
    spec.py                # clause registry (id -> spec section, tier)
    report.py              # JSON + JUnit + human-readable reporters
    vectors/               # declarative test vectors (YAML), grouped by topic
  roots/                   # the root-directory corpus (see §6)
  adapters/                # example adapter manifests for reference impls
  capabilities.schema.json # JSON Schema for the capability manifest
  vector.schema.json       # JSON Schema for a declarative test vector
```

The harness is **Python + pytest**. pytest gives us parametrization
(impl × root × vector), fixtures for server lifecycle, rich failure output, and
JUnit XML for free. The *test content*, however, lives in language-agnostic YAML
vectors (§7) so the corpus is reusable by a future non-Python runner.

Execution model per run:

```
for impl in implementations:
    caps = load_capability_manifest(impl)
    for root in roots_required_by_selected_vectors:
        for vector_group in isolation_groups(vectors_for(root)):
            materialized = materialize(root, vector_group)
            server = adapter.launch(impl, root=materialized.path, port=free_port())
            wait_until_ready(server)
            for vector in vector_group:
                if should_skip(vector, caps):
                    record SKIP(reason=skip_reason(vector, caps))
                else:
                    before = materialized.snapshot_if_needed(vector)
                    actual = httpclient.send(server.base_url, vector.request,
                                             timeout=per_request_timeout)
                    after = materialized.snapshot_if_needed(vector)
                    record compare(vector.expect, actual, caps, before, after)
            adapter.shutdown(server)
emit reports
```

`isolation_groups` keeps read-only vectors together when safe, but gives every
mutation vector and every `no_mutation` assertion a pristine materialized root
unless the vector explicitly declares an ordered scenario. This prevents one
PUT/DELETE/POST test from contaminating later assertions.

A fresh server is launched per isolation group, not per root: because mutation
groups each need a pristine materialized tree, the harness relaunches the
implementation for every group and allocates one free loopback port per launch.
Read-only groups that share a materialized tree therefore also share a single
launch. Port allocation and temp-root cleanup are per launch, which is what makes
parallel execution (`pytest -n`) safe.

---

## 3. The launch-command adapter contract

An implementation participates by providing an **adapter manifest** — a small
declarative file the harness reads to learn how to start and stop the server.
No code coupling; the harness only runs processes and speaks HTTP.

`adapters/<name>.toml`:

```toml
name        = "reference-python"
# Command to start a server. Placeholders are substituted by the harness.
#   {root} = absolute path to a materialized root directory
#   {port} = TCP port the server MUST bind on localhost
start       = "python -m wash.server --root {root} --port {port}"
# Optional explicit shutdown; default is SIGTERM to the process group.
stop        = "SIGTERM"
# How the harness decides the server is up (see §3.1).
ready       = { type = "http", path = "/", expect_status_any = [200, 404] }
ready_timeout_sec = 10
# Working directory for the start command (default: repo root).
cwd         = "impls/reference-python"
# Environment overrides for the child process. These must NOT change behavior the
# harness probes for as a default (e.g. do not disable CORS here — the
# cross-origin-default test in §13.1 relies on a plain, default launch).
env         = {}
# Path to this implementation's capability manifest (§4).
capabilities = "impls/reference-python/wash.capabilities.json"
```

The start command launches the implementation in its *default* configuration.
The harness asserts spec defaults (cross-origin disabled, `mutates false`, GET
only) against this default launch, so the adapter must not pre-toggle any of
them through `env` or start arguments.

### 3.1 Lifecycle requirements the harness enforces

- **Binding.** The implementation MUST bind the given `{port}` on a loopback
  address. The harness picks a free port per launch (one launch per isolation
  group, §2) to allow parallelism.
- **Root isolation.** Each launch gets a *fresh copy* of the root directory in a
  temp dir (§6.4), because PUT/DELETE/POST tests mutate the tree. The harness
  never runs mutation tests against the canonical corpus.
- **Readiness.** The harness polls `ready` until success or timeout. An
  implementation that never becomes ready is reported as a launch failure, not a
  spec failure (so a broken adapter is distinguishable from a broken runtime).
- **One root per instance.** Per `runtime.md` §4.2/§12.1, a server maps exactly
  one root. The harness relaunches for each root rather than reconfiguring.
- **Teardown.** SIGTERM, then SIGKILL after a grace period. Port must be released
  before the next launch on it.
- **Per-request deadline.** Every request is sent with a timeout
  (`per_request_timeout`, default 10s, overridable per vector for slow
  pipelines). A request that does not complete in time is recorded as a distinct
  `TIMEOUT` outcome — separate from a spec failure and from a launch failure — so
  a command that hangs (e.g. blocking on stdin) cannot stall the run or be
  misreported as non-conformance.

---

## 4. Capability manifest (tiered conformance)

The specs mark many behaviors implementation-defined. Rather than guess, each
implementation declares what it does in a **capability manifest**, validated
against `capabilities.schema.json`. The harness then enforces only normative
behavior plus whatever the implementation has declared.

`wash.capabilities.json`:

```json
{
  "spec_version": "1",
  "origin_form": "http://localhost",
  "directory_listing": true,
  "default_index_files": ["index.html"],
  "synthesized_resources": false,
  "mime": {
    "inference": "by-extension",
    "map": { ".txt": "text/plain", ".json": "application/json" },
    "default": "application/octet-stream"
  },
  "options_cors": "implementation-defined",
  "symlink_policy": "reject-escaping",
  "case_sensitive_lookup": true,
  "execution_metadata_headers": true,
  "error_body_formats": ["text/plain", "application/json"],
  "max_error_body_bytes": 8192,
  "writes_enabled": true,
  "deletes_enabled": true,
  "interpreters": ["sh", "python3"]
}
```

Field notes:

- `spec_version` pins the manifest to a specific revision of the specs. The
  harness records it as `<spec-version>@<spec-commit>` in every report so a
  conformance claim is reproducible against the exact spec text it was made
  against; a manifest whose `spec_version` predates the registry's spec revision
  is flagged.
- `origin_form` is the scheme+authority the implementation serves on (e.g.
  `http://localhost`). The harness uses it only to construct the `Origin` header
  for the cross-origin test (§13.1): a request is "cross-origin" when its
  `Origin` differs from this value.
- `interpreters` lists the interpreters the implementation can resolve through
  `exec` rules. The harness uses it to **skip** any root whose command scripts
  require an interpreter the implementation does not declare (§7.3), recording
  the skip with a reason rather than failing for a permitted limitation.

How tiers use it:

- **MUST tests** run for every implementation; failing one is non-conformance.
- **SHOULD tests** run for every implementation; failing produces a warning, not
  a hard failure, and is highlighted in the report.
- **Optional/implementation-defined tests** run only when the manifest declares
  the relevant capability, and they assert *internal consistency with the
  declaration* (e.g. "you said `directory_listing: true`, so a directory with no
  index must produce a listing"; "you said `mime.map` maps `.json`, so
  `/data.json` must return that type"). If a capability is declared absent, the
  matching tests are skipped and recorded as such.

This makes the harness fair (no penalty for permitted choices) while still
catching the most common real bug: behavior that contradicts the
implementation's own declared contract or the spec's MUSTs.

Some normative behaviors have policy branches. For example, `runtime.md` §9.2
and §9.4 require PUT/DELETE to target literal filesystem paths, but permit an
implementation policy to disable writes or deletes. The harness therefore runs
policy-aware MUST vectors:

- when `writes_enabled: true`, PUT vectors assert the exact literal mutation;
- when `writes_enabled: false`, PUT vectors assert an allowed policy rejection
  such as 403 or 405 and no tree mutation;
- when `deletes_enabled: true`, DELETE vectors assert the exact literal deletion;
- when `deletes_enabled: false`, DELETE vectors assert an allowed policy
  rejection and no tree mutation.

This still tests the MUST-level contract without forcing a spec-permitted
mutability policy.

---

## 5. Spec clause registry

`conformance/spec.py` holds a registry mapping a stable clause id to its source
section and tier. Every vector references one or more clause ids. This gives:

- traceability (each failure cites e.g. `PP-§4` "metadata-free arity 0"),
- coverage reporting (which clauses have ≥1 vector; §9),
- tier lookup (MUST/SHOULD/optional) without duplicating it in every vector.

Examples of clause ids and tiers (illustrative, not exhaustive):

| Clause id | Source | Tier | Requirement |
|-----------|--------|------|-------------|
| `RT-6.2-precedence` | runtime §6.2 | MUST | exact file > command > synthesized > 404 |
| `RT-6.3-direct-cmd-file` | runtime §6.3 | MUST | `/bin/wc` serves the file |
| `RT-9.1-get-no-mutate` | runtime §9.1 | MUST | GET must not mutate state |
| `RT-9.2-put-literal` | runtime §9.2 | MUST | PUT targets literal path, no cmd parse |
| `RT-9.5-head-from-get` | runtime §9.5 | MUST | GET implies HEAD, body omitted |
| `RT-9.5-methods-405` | runtime §9.5 | MUST | method not in `methods` → 405 |
| `RT-13.1-cors-default` | runtime §13.1 | SHOULD | cross-origin disabled by default |
| `PP-2-parse-algo` | pipeline §2 | MUST | normative parse order |
| `PP-4-arity0-default` | pipeline §4 | MUST | metadata-free command = arity 0 |
| `PP-4-implied-cat` | pipeline §4 | MUST | rightmost suffix fed via implied cat |
| `PP-5.1-arity-n` | pipeline §5.1 | MUST | arity N consumes N segments |
| `PP-5.2-arity-star` | pipeline §5.2 | MUST | `arity *` consumes rest as argv |
| `PP-5.4-exit-map` | pipeline §5.4 | MUST | exit→status mapping + pipefail |
| `PP-5.5-malformed-500` | pipeline §5.5 | MUST | malformed metadata → 500 |
| `PP-6.1-core-arg` | pipeline §6.1 | MUST | `?arg=` is the only core query param |
| `PP-6.3-arg-noncmd-400` | pipeline §6.3 | MUST | core arg on non-command → 400 |
| `PP-8-stderr-prefix` | pipeline §8 | MUST | `/&` prefix merges one boundary |
| `PP-9.2-no-cmd-in-dir` | pipeline §9.2 | MUST | no command lookup after dir traversal |
| `PP-9.1-trailing-q` | pipeline §9.1 | MUST | trailing `?` is resource query first |
| `RT-6.5-dir-index` | runtime §6.5 | optional | declared default file > listing |
| `PP-11-headers` | pipeline §11 | optional | `X-WebShell-*` header names |
| `PP-9.5-synth` | pipeline §9.5 | optional | synthesized-resource behavior |
| `RT-R7-case` | audit R7 | optional | case-sensitivity (declared, not mandated) |

---

## 6. Root-directory corpus

The heart of the harness. Each root is a self-contained, version-controlled
fixture exercising specific spec behaviors. Roots are deliberately small and
single-purpose so a failure points at one concept. A vector names exactly one
root; many vectors share a root.

Layout under `harness/roots/<root-name>/`. Where a root needs `env/path`,
`env/meta/<cmd>`, `exec`, or command files, they are checked in as ordinary
files. Command scripts are POSIX `sh`/`python3` (matched by an `exec` rule) so
they run anywhere the adapter's declared interpreters exist.

### 6.1 Corpus overview

| Root | Purpose / clauses exercised |
|------|------------------------------|
| `empty/` | Empty root is valid (§4.2). Everything 404s; `/` is dir behavior. |
| `plain-files/` | Literal file mapping (§6.1), MIME inference, raw bytes, nested paths, dot-segment normalization, root-escape rejection. Trailing-`?` disambiguation (§9.1/Q19): `/file.txt?download=1` strips the query and matches the file first, while a `?` followed by any raw `/` is per-command syntax and prevents the exact-file match. |
| `directories/` | Directory behavior (§6.5): one dir holding a default file (named from the manifest's `default_index_files`, materialized per-impl), one without (listing or impl-defined, gated on `directory_listing`), trailing-slash equivalence and repeated-slash collapse (§9.1), directory used as an implied-cat suffix `/wc/docs` (§9.4). Because §6.5 is implementation-defined, these run as capability-gated consistency checks, not flat MUST/SHOULD. |
| `precedence/` | The §6.2 ladder. Contains a real file `wc` at root, a real file `bin/wc`, a real `grep/docs/file.txt`, and commands `wc`/`grep` on PATH. Proves exact-path-wins, `/bin/wc` serves file, `/grep/docs/file.txt` serves file. |
| `commands-mf/` | Metadata-free commands only (arity 0). `cat`-style pass-through, identity, line-count. Proves implied cat, multi-stage pipelines, and that path args → 400 (§13.1, §13.2 of pipeline). |
| `commands-arity/` | Commands with `arity 1`, `arity 2` (diff-like), `arity *`. Proves path-arg consumption, multi-resource via root-relative argv (§10.5), arity-star argv. |
| `commands-query/` | Query argv: `?arg=`, repeated `arg`, percent-encoded `/?&=` in values, query-disables-metadata-arity, core-arg-on-noncommand→400. |
| `body-input/` | Request body as stdin (§10.6, §12.4): `POST /transform` with a body feeds the rightmost stage's stdin; input suffix wins over body when both present; `arity *` suppresses the URL input suffix but the body still feeds stdin (§5.2); no suffix and no body → stdin closed and empty. |
| `commands-meta/` | Full metadata coverage: `methods`, `mutates`, `mime`, `stderr`, `exit` mappings, `parse-mode raw` (an `explain`-like command). |
| `meta-malformed/` | Each subdir/command has one deliberately malformed metadata field (bad arity, bad exit pair, `mutates true`+GET, `input file`, range arity, raw-not-leftmost) → each must 500. |
| `pipelines/` | Realistic multi-stage pipelines (`jq`/`grep`/`wc` analogues with proper metadata) to validate the worked examples in pipeline §12 and runtime §8.4/§16.4. |
| `stderr/` | Commands that write to stderr; validates `/&` boundary semantics (§8) and `stderr merge` metadata (§5.9), single-boundary scoping, rightmost-prefix rule. |
| `exit-codes/` | Commands with deterministic exit codes + `exit` maps; validates default nonzero→400, custom maps, and pipefail aggregation (first-in-URL-order wins, §5.4). |
| `methods/` | Commands declaring `methods GET POST`, GET-only, mutating-with-POST; validates 405, HEAD-from-GET, every-stage-must-permit-method. |
| `mutation/` | PUT/DELETE/POST against plain files; validates literal targeting (§9.2/§9.4), POST-to-plain→405 (§9.3), command-governed POST write semantics. **Run only on disposable copies.** |
| `exec-rules/` | `exec` interpreter rules: exact basename match, glob match against relative path, first-match-wins, comment/blank handling, malformed rule→500, unresolved interpreter→500 (§7.2, §15.5). |
| `encoding/` | Percent-encoding edge cases: `%5B%5D`, `%2F` in argv vs path, `%3F` literal `?` filename, `%26` literal-`&` command name, NUL/`/` rejection in path segments. |
| `synthesized/` | Optional synthesized-resource checks. Runs only when the capability manifest declares concrete synthesized fixture paths (for example `/docs/index`) and their expected status/body/header behavior; validates command-parse-beats-synth, exact-file-beats-synth precedence, and 400-is-terminal-no-fallback. |
| `path-outside/` | `env/path` pointing to `../shared/bin`; validates command dirs outside root work (§7.1) while literal file serving still rejects root escape (§12.2). Materialization copies this root as part of a fixture bundle that preserves the sibling `shared/bin` relationship. |
| `case/` | Files differing only by case; behavior gated on `case_sensitive_lookup` declaration (audit R7, optional). |

### 6.2 Worked example: `precedence/`

```
roots/precedence/
  env/path            ->  "bin\n"
  bin/wc              ->  command script; first line "# wash-fixture: linecount"
  bin/grep            ->  command script (filters)
  env/meta/grep       ->  "arity 1\n"
  wc                  ->  plain file containing "i am a regular file named wc"
  grep/docs/file.txt  ->  plain file "served as a file, not a pipeline"
  haystack.json       ->  sample input of three lines
```

The `bin/wc` script begins with a fixed `# wash-fixture: linecount` marker line
(a comment, not a shebang — §4.4 commands need none) so a direct-file-access test
has a byte-stable substring to match, and it writes only a bare line count to
stdout so a piped-execution test has a byte-stable output.

Vectors against this root assert, among others:
- `GET /wc` → 200, body is the *file* "i am a regular file named wc" (§6.2 last
  paragraph: single-segment exact path wins).
- `GET /bin/wc` → 200, serves the command file's bytes; matched by
  `body_contains: "# wash-fixture: linecount"` (§6.3).
- `GET /grep/docs/file.txt` → 200, serves the file even though `grep` is a
  command (§6.2 / pipeline §3, §9.1).
- `GET /wc/haystack.json` → executes `cat haystack.json | wc`, body matched by
  `body_matches: '^\s*3\s*$'` (the script emits a bare line count for the
  three-line input; §6.2: no `root/wc/haystack.json` exists, so command parse
  proceeds).

### 6.3 Command scripts in fixtures

Fixture commands are tiny and deterministic, written so output is byte-stable
across platforms. They avoid real tools (`wc`, `jq`, `grep`) whose output format
varies by platform/locale; where real-tool behavior is conceptually needed it is
replaced by a custom script that produces a frozen format.

Because the execution-metadata headers (`X-WebShell-*`, pipeline §11) are
*optional*, the harness cannot rely on them to confirm that a pipeline was
assembled and ordered correctly. The proof has to come from the response body.
Fixture commands are therefore designed to make pipeline structure observable in
their output bytes, following one **stage-tagging output contract**:

- A transform stage reads stdin (treated as newline-separated records) and emits,
  for each record, a line `‹TAG›(‹argv…›):‹record›` — its own tag, its received
  argv joined by commas, and the record it passed through. Tags are the command's
  basename. Because each stage prepends its own tag, the final stdout encodes the
  exact stage order: `cat data | jq | grep needle` over a one-line input `x`
  yields `grep(needle):jq():x`, and any other assembly order produces a different,
  detectable string. This lets a single `body_exact` assertion pin both the set
  of stages and their order without any header support.
- Argv-echo commands (`echo1` arity 1, `echo2` arity 2, `echoN` arity *) emit
  their received argv as `argv=[a|b|...]` plus, for `echo2`, whether each argv
  names a file that exists in the cwd (root) — so root-relative argv handling
  (§10.5/§12.3) is asserted without depending on system `diff`.
- Stderr behavior is made observable by `noisy`, which writes a fixed marker to
  **stdout** (`out:‹record›`) and a different fixed marker to **stderr**
  (`err:‹record›`) for each record. A downstream stage tags whatever it reads, so
  a `/&`-merged boundary makes the `err:` markers appear (tagged) in the final
  body while an unmerged boundary keeps them out. This distinguishes "merged at
  exactly this one boundary" from "not merged" and from "whole pipeline merged"
  (§8) purely from the body bytes.
- Exit behavior is made observable by `exitN` commands that ignore input and exit
  with a fixed code (and emit a fixed line first), so pipefail aggregation
  (§5.4) can be asserted by constructing a two-failure pipeline and checking which
  stage's status and diagnostic surface.

`roots/_lib/` holds the canonical implementations of these scripts (one `.sh` and
one `.py` variant of each), and each root's command files are copies of, or thin
wrappers around, those canonical scripts so the output contract stays identical
everywhere. The interpreter a script needs is declared in that root's `exec`
file and gated against the manifest's `interpreters` (§4, §7.3).

### 6.4 Mutability and isolation

- Read-only vectors may share a materialized root when they do not assert
  post-request tree state.
- Any vector with `no_mutation`, any vector with a `mutation` expectation, and
  all PUT/DELETE/POST-write vectors get a fresh temp root unless they are part of
  an explicitly ordered scenario.
- After such a vector, the harness diffs the temp tree against the pristine
  fixture to assert either *exactly* the intended mutation or no mutation at all
  (`RT-9.1-get-no-mutate`).
- Roots with external relatives, such as `path-outside/` and its sibling
  `shared/bin`, are materialized as bundles so relative command-path entries keep
  the same shape they had in the canonical corpus. The bundle is laid out as
  `‹tmp›/root/` (the served root, with `env/path` containing `../shared/bin`) and
  `‹tmp›/shared/bin/`, so the `../shared/bin` entry resolves relative to the
  served root exactly as it does in the checked-in corpus. The adapter is
  launched with `{root}` = `‹tmp›/root`.
- Some fixtures are **parameterized per implementation** at materialization time.
  The `directories/` default-file fixture is created using the first entry of the
  manifest's `default_index_files` (so an implementation whose default file is not
  `index.html` is still tested against its own declared default), and is skipped
  entirely when that capability is absent.
- Symlink fixtures (for the §9.1 default-reject test) are **not** checked in as
  real symlinks; they are synthesized into the materialized tree at run time and
  only when the platform supports symlink creation and the manifest declares a
  `symlink_policy`. On platforms or implementations without symlink support the
  symlink vectors are skipped with a recorded reason. This keeps `validate-roots`
  (§6.5) free of checked-in symlinks while still exercising the behavior where it
  is meaningful.

### 6.5 Generation vs checked-in

Roots are checked in as plain files (Git-friendly, matches the spec's ethos).
A `rootcorpus.py validate` command verifies invariants before a run: required
fixture files present, `env/path`/`exec`/`meta` parse, no accidental executable
bits that would mask "no exec bit needed" tests (§4.4), and symlinks present only
where a symlink test intends them.

---

## 7. Declarative test vectors

Vectors are YAML, validated against `vector.schema.json`. They describe a raw
request and an expected outcome in terms the harness can check language-neutrally.
Critically, the **request is expressed as a raw request-target**, because the
spec requires parsing the unnormalized target (multi-`?` URLs, raw `/` vs `%2F`);
the harness's HTTP client (§8) sends it verbatim.

`vectors/precedence.yaml` (excerpt):

```yaml
- id: prec-single-segment-file-wins
  clauses: [RT-6.2-precedence]
  tier: MUST
  root: precedence
  request:
    method: GET
    target: "/wc"
    headers: {}
    body_base64: ""
  expect:
    status: 200
    body_exact: "i am a regular file named wc"

- id: prec-direct-command-file
  clauses: [RT-6.3-direct-cmd-file]
  tier: MUST
  root: precedence
  request: { method: GET, target: "/bin/wc" }
  expect:
    status: 200
    body_contains: "# wash-fixture: linecount"   # the script's marker line; byte-stable

- id: prec-command-over-file-of-same-name
  clauses: [RT-6.2-precedence, PP-4-implied-cat]
  tier: MUST
  root: precedence
  request: { method: GET, target: "/wc/haystack.json" }
  expect:
    status: 200
    body_matches: '^\s*3\s*$'   # the line count, not the file named wc

- id: arg-on-noncommand-is-400
  clauses: [PP-6.3-arg-noncmd-400]
  tier: MUST
  root: commands-query
  request: { method: GET, target: "/grep/-i?arg=needle/file.txt" }
  expect:
    status: 400
```

### 7.1 Expectation vocabulary

A vector's `expect` block supports a small, declarative matcher set:

- `status`, or `status_any: [..]` where the spec permits a choice.
- `body_exact`, `body_contains`, `body_matches` (regex), `body_base64` (binary).
- `header`: exact match; `header_present` / `header_absent`; `header_matches`.
- `content_type` (with `mime.*` capability awareness — only enforced when the
  implementation declares MIME inference and a mapping for the extension).
- `no_mutation`: assert the post-request root-tree diff is empty (GET safety).
- `mutation`: assert a specific path was created/replaced/deleted with given
  bytes (PUT/DELETE/command-write). Policy-aware mutation vectors may also carry
  `when_writes_disabled` or `when_deletes_disabled` branches with allowed
  rejection statuses and `no_mutation: true`.
- `pipeline_header`: when `execution_metadata_headers` is declared, assert
  `X-WebShell-Pipeline` etc. reflect the expected effective pipeline.
- `error_body`: when `Accept: application/json`, assert the error doc contains
  diagnostic fields (failing command, unexpected segment) — SHOULD tier, since
  exact text is non-normative (pipeline §10.1).

A vector's `request` block supports:

- `method` and raw `target` (required).
- `headers` as exact wire header names and values, including `Origin` and
  `Accept`.
- `body_exact`, `body_base64`, or `body_file` for PUT/POST/stdin cases.

The schema rejects vectors that specify more than one body source. Omitted
headers mean no extra headers beyond the HTTP minimum; omitted body means an
empty request body.

### 7.2 Negative and ambiguity vectors

The spec is explicit that certain URLs are invalid. These get first-class
vectors asserting the precise status (400 vs 404 vs 500 vs 405), since the most
common implementation bug is the *wrong* error class:

- metadata-free path args → 400 (`/wc/-l/file.txt`).
- core arg on non-command → 400.
- malformed metadata → 500 (not 400).
- POST to plain file → 405.
- method not permitted → 405.
- no resource, no command → 404.
- command-parse-started-then-failed is terminal (no synthesized fallback) → 400.

### 7.3 Capability-conditional vectors

A vector may carry `requires_capability: directory_listing` (etc.). The harness
skips (with a recorded reason) when the implementation declares it absent, and
runs it as a consistency check when present. `forbidden_when` handles the inverse
(e.g. CORS headers must be absent unless cross-origin is explicitly enabled).

A vector (or its root) may carry `requires_interpreter: python3` (etc.). A root
whose command scripts need an interpreter the manifest's `interpreters` list does
not include is skipped wholesale, with the reason recorded, so an implementation
is never failed for not running a language it never claimed to support. Because
`roots/_lib/` ships both `.sh` and `.py` variants of every fixture command (§6.3),
most roots can be materialized with whichever interpreter the implementation
declares; a vector pins a specific interpreter only when the behavior under test
is interpreter-specific.

---

## 8. HTTP client requirements

A standout property of this spec is that **the runtime must parse the raw
request-target itself** and not lean on a library's single path/query split
(runtime §12.2, pipeline §6). The harness's client must therefore *send* raw
targets faithfully, or it can't test the very behavior under scrutiny:

- Send multi-`?` targets like `/grep?arg=needle/jq?arg=.items%5B%5D/haystack.json`
  byte-for-byte, without re-encoding or collapsing.
- Preserve `%2F`, `%3F`, `%26`, `%5B%5D` exactly as authored in the vector.
- Do not auto-normalize dot segments (let the server do §12.2 normalization).
- Allow crafting cross-origin requests (an `Origin` header) to test §13.1.
- Allow request bodies without text transcoding, including binary PUT/POST bodies
  and POST bodies used as command stdin.
- Capture status, headers, and raw body bytes; never transcode the body.
- Enforce a per-request timeout (§3.1) so a hung command surfaces as a `TIMEOUT`
  outcome instead of blocking the run; the socket is closed and the result
  recorded distinctly from a spec failure.

This likely means a thin client over a low-level socket/`http.client` rather than
`requests`/`httpx` default behavior. The client module documents and tests this
"don't normalize" property against a loopback echo so we trust the harness itself.

---

## 9. Coverage and the audit boundary

- **Clause coverage report.** Cross-reference the clause registry (§5) with
  vectors; emit a table of clauses with zero vectors so the suite's own gaps are
  visible. Target 100% MUST-clause coverage before declaring the harness v1.
- **Audit R1–R7 handling.** The `specs/audit.md` open items are *not* failures:
  - R1 (OPTIONS/CORS), R2 (`input file`/`output file`/`input none`), R3 (cwd
    override), R4 (range arity), R6 (`explain` contract) → vectors that assert the
    v1 *reserved* behavior (e.g. `input file` declared in metadata → 500; range
    arity → 500; OPTIONS is implementation-defined → only assert CORS-off
    default, not preflight specifics). The cross-origin-default assertion is
    concrete: against a default launch (§3), a GET carrying an `Origin` that
    differs from the manifest's `origin_form` must come back **without an
    `Access-Control-Allow-Origin` header** (`header_absent`). The harness asserts
    only this header absence — it does not require the request to be rejected,
    since "disabled" means the browser blocks the response, not that the server
    returns an error.
  - R5 (quoting in metadata/exec) → vectors confirm whitespace-separated tokens
    only; values needing quoting are out of scope (not tested as supported).
  - R7 (case sensitivity) → optional tier, gated on the capability declaration.
- **Synthesized resources.** Because synthesis is implementation-defined, the
  manifest must declare concrete synthesized fixture targets before synthesized
  vectors run. A bare `synthesized_resources: true` is informational only; it
  does not give the harness enough information to assert portable behavior.
- **Per-implementation scorecard.** MUST pass rate (must be 100% to be
  "conformant"), SHOULD pass rate, declared optional features and their
  consistency results, and an explicit list of skipped tests with reasons.

---

## 10. Reporting

Three reporters from one result model (`report.py`). Each (impl, root, vector)
record carries one outcome — `PASS`, `FAIL`, `SKIP` (with reason), `WARN`
(a failed SHOULD), `TIMEOUT` (§8), or `LAUNCH_FAILURE` (§3.1) — so an
implementation problem, a permitted skip, a hung command, and a broken adapter are
never conflated.

1. **Human summary** (stdout): per impl, a tiered table (MUST/SHOULD/optional),
   the first N failures with clause id, the exact request target, expected vs
   actual status/body diff, and the cited spec section text.
2. **JSON** (`results.json`): machine-readable full results for dashboards or
   cross-run diffing; one record per (impl, root, vector) with timing.
3. **JUnit XML**: for CI integration; testcase names encode `impl/clause/vector`
   so CI surfaces regressions per clause.

Optional: a **conformance matrix** (markdown) — implementations as columns,
clauses as rows, ✓/✗/– (skip) cells — to compare implementations at a glance and
track an implementation's progress over time.

A non-zero exit code if any MUST fails (gate for CI); SHOULD/optional failures
are warnings unless `--strict` is passed.

---

## 11. CLI surface

```
# Run everything against one implementation:
wash-conformance run --adapter adapters/reference-python.toml

# Compare several:
wash-conformance run --adapter adapters/*.toml --report matrix

# Subset by clause, tier, or root:
wash-conformance run --adapter A.toml --tier MUST --root precedence
wash-conformance run --adapter A.toml --clause PP-5.4-exit-map

# Validate the corpus / a manifest without running an impl:
wash-conformance validate-roots
wash-conformance validate-capabilities adapters/reference-python.toml

# Coverage of the vectors against the clause registry:
wash-conformance coverage
```

Under the hood these are pytest invocations with parametrization, so
`pytest`-native flags (`-k`, `-x`, `-n` for parallelism) also work.

---

## 12. Build order (suggested phases)

0. **Minimal reference implementation.** A small `wash` server covering the MVP
   surface (runtime.md §18): literal GET, basic directory behavior, PUT/DELETE,
   `env/path`, `exec`, `env/meta/<command>`, left-to-right resolution, child
   process per request, the error classes, and cross-origin off by default. It
   lives under `impls/reference/` with its own adapter and capability manifest and
   gets no special treatment from the harness — it is the green target the
   vertical slice (phase 4) runs against, and "the reference is just another
   adapter" keeps the harness honest and language-neutral.
1. **Skeleton + contracts.** `pyproject.toml`, the two JSON Schemas
   (capabilities, vector), `spec.py` clause registry seeded with MUST clauses,
   and `report.py` result model. No server interaction yet.
2. **Non-normalizing HTTP client** (§8) with a self-test against a loopback echo.
3. **Adapter lifecycle** (§3): launch/ready/teardown, free-port allocation, root
   materialization + post-run diff.
4. **First vertical slice:** the `precedence/` and `commands-mf/` roots plus their
   vectors, run against a reference implementation, green end to end.
5. **Fill the corpus** root by root (§6 table), writing vectors alongside each.
6. **Capability gating** (§4) and the optional/SHOULD tiers.
7. **Coverage + reporters** (§9, §10), then the comparison matrix.
8. **CI wiring** and a `--strict` gate.

Phase 0 exists so every later phase has a live server to develop against. The
reference participates only through its adapter and capability manifest, so
nothing in phases 1–8 may depend on its internals.

---

## 13. Open questions to revisit during build

- **Byte-stability of command output across OSes.** The fixture commands are
  custom deterministic scripts following the §6.3 output contract rather than
  wrappers over `wc`/`jq`/`grep`; confirm the `.sh` and `.py` variants in
  `roots/_lib/` produce byte-identical output across the supported platforms.
- **Windows.** `sh`/`python3` interpreter availability and process-group
  signaling differ. Decide whether v1 of the harness targets POSIX only and
  gates Windows behind a capability/skip.
- **Parallelism.** Per-launch isolation (§2) makes parallel runs safe; confirm
  per-launch port allocation and temp-root cleanup are robust under `pytest -n`.
