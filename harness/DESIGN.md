# wash Conformance Harness Design

> A language-neutral evaluation harness for `wash` (Web Shell) implementations.
> It launches any implementation against a corpus of root directories, drives it
> over HTTP, and reports how faithfully it implements `specs/runtime.md` and
> `specs/pipeline_parsing.md` — including where it falls short.

Status: implemented draft. This document began as the architecture plan and now
records design contracts for the Python conformance harness in
`harness/conformance/`, the root corpus in `harness/roots/`, and adapter
manifests in `harness/adapters/`.

For day-to-day agent orientation, start with `../AGENTS.md` and `AGENTS.md` in
this directory. Keep this file focused on durable architecture and contract
rationale; do not use it as the canonical command list.

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
   resources, OPTIONS/CORS, symlink policy, case sensitivity, command-emitted full
   HTTP responses). The harness
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
  DESIGN.md                # this document
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

impls/                     # reference implementations, each its own adapter target
  reference/               # the phase-0 minimal server (§12); just another adapter
```

`impls/` sits beside `harness/` (not inside it) so the harness has no code path
into any implementation: the reference server is reached only through its adapter
manifest and capability manifest, exactly like a third-party implementation. The
`cwd` and `capabilities` paths in adapter manifests (§3) are relative to the
repository root, so they reference `impls/...`.

Because both the harness and the reference implementation are written in Python,
they are kept as **separate packages with disjoint import roots**: the harness's
`conformance` package never imports the reference's `wash` package (the reference
is launched only as a subprocess via its adapter). This is a packaging invariant,
not just a convention — nothing under `conformance/` may `import wash`, so the
"reference is just another adapter" property cannot be violated by accident. The
reference may be installed into its own environment; the harness does not require
it to be importable.

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
                if cannot_run(vector, caps, materialized):
                    record unrunnable_outcome(vector, reason)
                    # SKIP for optional/capability-absent vectors;
                    # UNTESTED for selected MUST vectors.
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
mutation vector and every `no_mutation` assertion a pristine materialized root.
Every vector is a single self-contained request, so no vector ever depends on the
side effects of an earlier one; this prevents one PUT/DELETE/POST test from
contaminating later assertions.

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
name        = "reference"
# Command to start a server. Placeholders are substituted by the harness.
#   {root} = absolute path to a materialized root directory
#   {port} = TCP port the server MUST bind on the loopback host (§3.1) (only with port_mode = "assigned")
start       = ["python", "-m", "wash.server", "--root", "{root}", "--port", "{port}"]
# Optional explicit shutdown; default is SIGTERM to the process group.
stop        = "SIGTERM"
# Port acquisition strategy (see §3.1). Default "assigned".
#   "assigned" — the harness picks a free port and substitutes {port}; the harness
#                retries the whole launch on a bind-failure exit (race-safe).
#   "ephemeral" — the implementation binds an OS-chosen free port (e.g. :0) and
#                 prints "WASH-PORT <n>" to stdout as its first line; {port} is not
#                 substituted and the harness reads the actual port from that line.
port_mode   = "assigned"
# How the harness decides the server is up (see §3.1). The default is a TCP
# connect probe so readiness itself never sends a GET into the served namespace.
ready       = { type = "tcp" }
ready_timeout_sec = 10
# Working directory for the start command (default: repo root).
cwd         = "impls/reference"
# Environment overrides for the child process. These must NOT change behavior the
# harness probes for as a default (e.g. do not disable CORS here — the
# cross-origin-default test in §13.1 relies on a plain, default launch).
env         = {}
# Path to this implementation's capability manifest (§4).
capabilities = "impls/reference/wash.capabilities.json"
```

The `start` command is an argv array, not a shell string. Placeholders are
substituted into individual argv elements, with no shell interpolation, globbing,
or quoting step; this keeps roots with spaces or shell metacharacters launchable.
The command launches the implementation in its *default* configuration. The
harness asserts spec defaults (cross-origin disabled, `mutates false`, GET only)
against this default launch, so the adapter must not pre-toggle any of them
through `env` or start arguments.

### 3.1 Lifecycle requirements the harness enforces

- **Connection host.** `runtime.md` §4.1 leaves the bind address
  implementation-defined (`localhost`, `127.0.0.1`, `::1`, or a custom local
  hostname). The harness therefore does not guess: the host it connects to is the
  **authority of the manifest's `origin_form` (§4)** combined with the launch port,
  and the implementation MUST bind that host. For example `origin_form:
  http://127.0.0.1` ⇒ the implementation binds and the harness dials `127.0.0.1`.
  This makes the loopback-host choice explicit and contractual rather than a source
  of spurious launch failures, and it is the same `origin_form` already used for the
  cross-origin test (§4/§13.1). To avoid the IPv4/IPv6 dual-stack ambiguity of the
  name `localhost` (which resolves to both `127.0.0.1` and `::1`, so a server that
  binds only one family while the harness dials the other yields intermittent
  connection-refused), `origin_form` SHOULD use a literal loopback IP. An
  implementation that nevertheless declares `origin_form: http://localhost` MUST
  bind **every** address family `localhost` resolves to on the host; otherwise the
  harness's dial may miss the bound family. The reference implementation (§12)
  declares `http://127.0.0.1`.
- **Binding.** The implementation MUST bind a loopback address (the
  `origin_form` host above). Two strategies (selected by `port_mode`, §3) avoid the
  pick-then-bind race that otherwise makes `pytest -n` flaky:
  - `assigned` (default): the harness reserves a free port, substitutes `{port}`,
    and launches. Because another worker can claim that port between reservation
    and the child's `bind()`, the harness treats a fast non-ready exit whose
    captured output matches a configurable bind-failure pattern (default regex,
    case-insensitive: `EADDRINUSE|address already in use|address in use`) as a
    *retryable* launch, re-reserving a new port and relaunching up to **5** times
    before declaring `LAUNCH_FAILURE`.
  - `ephemeral`: the child binds an OS-chosen free port (bind `:0`) and prints
    `WASH-PORT <n>` as its **first line of stdout, before any other stdout
    output**. The harness reads the actual port from that line and derives
    `base_url` from it. This eliminates the race entirely and is the recommended
    mode for implementations that can report their port. The reference
    implementation (§12) supports `ephemeral`.
- **Child output capture.** The harness captures the child's stdout and stderr for
  the life of the process. Bind-failure pattern matching (assigned mode) scans
  **both** streams. The `WASH-PORT` readout (ephemeral mode) reads **stdout only**
  and requires line-buffered output (the implementation must flush the port line
  immediately, not hold it in a block buffer). Captured output is attached to any
  `LAUNCH_FAILURE` / `PROCESS_DIED` report for diagnosis.
- **Root isolation.** Each launch gets a *fresh copy* of the root directory in a
  temp dir (§6.4), because PUT/DELETE/POST tests mutate the tree. The harness
  never runs mutation tests against the canonical corpus.
- **Readiness.** The harness polls `ready` until success or timeout. The default
  `tcp` readiness succeeds when a fresh loopback TCP connection can be opened to
  the declared host/port; the probe is closed immediately and sends no HTTP
  request. This is intentionally weaker than a full HTTP request, but it avoids
  mutating or warming the served root before a vector's own before/after
  snapshot. Adapters may opt into `ready = { type = "http", path = "..." }` only
  for an endpoint that is guaranteed by the implementation to be outside the
  served root namespace and non-mutating. HTTP readiness success means the probe
  got back a well-formed HTTP status line on a fresh connection; the status value
  is not matched. An implementation that never becomes ready within
  `ready_timeout_sec` is reported as a launch failure, not a spec failure (so a
  broken adapter is distinguishable from a broken runtime).
- **Liveness between vectors.** Within an isolation group the harness checks the
  child is still alive before each vector. If a request gets connection-refused,
  connection-reset, EOF before a status line, or another transport-level failure,
  the harness immediately polls the child: if it has exited, the affected vector
  and the remainder of the group are reported as `PROCESS_DIED` (§10), with the
  captured child output attached; if the child is still alive, only that vector is
  scored as a response failure (`FAIL` for MUST/optional, `WARN` for SHOULD) with
  the transport diagnostic attached. This keeps crashes distinct from servers that
  stay up but fail to produce a valid HTTP response for a particular request.
- **One root per instance.** Per `runtime.md` §4.2/§12.1, a server maps exactly
  one root. The harness relaunches for each root rather than reconfiguring.
- **Teardown.** SIGTERM, then SIGKILL after a grace period. Port must be released
  before the next launch on it.
- **Per-request deadline.** Every request is sent with a timeout
  (`per_request_timeout`, default 10s, overridable per vector for slow
  pipelines). A request that does not complete in time closes the socket and is
  scored according to the vector's `timeout_means` (§7.1). The default is `fail`,
  because for most vectors a hang is itself the symptom of non-conformance — most
  importantly the closed-and-empty-stdin cases (pipeline §4: no input suffix and
  no body), where a stage blocks forever precisely when the implementation failed
  to close stdin. A vector that drives a legitimately slow pipeline sets
  `timeout_means: timeout` to record the neutral `TIMEOUT` outcome instead, which
  is kept separate from a spec failure and from a launch failure. Either way a
  hung command cannot stall the run.

---

## 4. Capability manifest (tiered conformance)

The specs mark many behaviors implementation-defined. Rather than guess, each
implementation declares what it does in a **capability manifest**, validated
against `capabilities.schema.json`. The harness then enforces only normative
behavior plus whatever the implementation has declared.

The fields whose values are drawn from a fixed set are **closed enumerations** in
`capabilities.schema.json`, so `validate-capabilities` rejects an unknown value
rather than silently accepting it: `options_cors` ∈ {`implementation-defined`, `disabled`}; `symlink_policy` ∈
{`reject-escaping`, `follow`, `unsupported`}; `error_body_formats` entries are
media-type strings drawn from {`text/plain`, `application/json`}. Free-form fields
(`runtime_artifact_paths`) stay open for values, but not for shape or safety:
filesystem paths are schema-validated according to their role, with absolute
paths, empty names, `.`/`..` segments, backslashes, NULs, and control bytes
rejected before materialization. MIME maps, index names, directory-listing policy,
and interpreter availability are not conformance claims in this manifest: serving
behavior is read from each root's `env/` files, and interpreter availability lives
in the adapter TOML. The schema is the source of truth for these sets; this list is
illustrative of the shape, and the schema must be authored to match in phase 1
(§12).

`wash.capabilities.json`:

```json
{
  "spec_version": "1",
  "origin_form": "http://127.0.0.1",
  "synthesized_resources": { "enabled": false, "fixtures": [] },
  "options_cors": "implementation-defined",
  "symlink_policy": "reject-escaping",
  "case_sensitive_lookup": true,
  "execution_metadata_headers": true,
  "error_body_formats": ["text/plain", "application/json"],
  "max_error_body_bytes": 8192,
  "writes_enabled": true,
  "deletes_enabled": true,
  "put_creates_parents": true,
  "runtime_artifact_paths": [],
  "command_full_http_response": { "enabled": false }
}
```

Field notes:

- `spec_version` pins the manifest to a specific revision of the specs. The
  canonical version string is the single source of truth held in
  `conformance/spec.py` as `SPEC_VERSION` (currently `"1"`); the spec **commit** is
  resolved at run time from `git rev-parse HEAD` of the repository containing
  `specs/` (falling back to `unknown` outside a checkout). If `git status
  --porcelain -- specs/` is non-empty the commit is suffixed `+dirty`, because
  uncommitted edits to `specs/` mean the recorded commit's text no longer matches
  what was actually tested. The harness records the triple as
  `<spec-version>@<spec-commit>[+dirty]` in every report so a conformance claim is
  reproducible against the exact spec text it was made against (and a `+dirty`
  claim is visibly non-reproducible). A manifest whose
  `spec_version` does not equal `spec.py`'s `SPEC_VERSION` is flagged.
- `origin_form` is the scheme+authority the implementation serves on (e.g.
  `http://127.0.0.1`; see §3.1 on why a literal loopback IP is preferred over the
  dual-stack name `localhost`). It serves two purposes. First, its host is the host the
  harness binds and connects to, combined with the per-launch port, to form
  `base_url` (§3.1 *Connection host*). Second, it anchors the cross-origin test
  (§13.1):
  the request carries a fixed foreign `Origin` of `http://cross-origin.invalid`
  (the `.invalid` TLD is reserved by RFC 2606 and can never collide with
  `origin_form`), and "cross-origin" means precisely that this differs from
  `origin_form`. If an implementation legitimately serves on
  `http://cross-origin.invalid`, it may override the foreign origin the harness
  sends via an optional `cross_origin_probe` manifest field.
  `validate-capabilities` rejects any `origin_form` that is not `http`, that
  contains a path/query/fragment/userinfo component, that embeds a port, or whose
  host is not a loopback literal/name accepted by the adapter lifecycle. The
  launch port always comes from the harness, never from the manifest.
- `put_creates_parents` records whether PUT to a path whose parent directory does
  not yet exist creates the intervening directories. runtime §9.2 leaves this to
  implementation policy, so the MUST-level PUT vectors target paths whose parent
  already exists (the literal mutation is then unambiguous), and the
  missing-parent case is a separate capability-gated vector: when the flag is
  true it asserts the parents and file are created, and when false it asserts an
  allowed policy rejection (e.g. 404/403/409) and no tree mutation.
- `runtime_artifact_paths` lists root-relative paths (caches, logs, indexes) the
  implementation expects to create while serving. These paths are diagnostic
  metadata only: they are recorded in reports to make unexpected tree changes
  easier to interpret, but they are **not** exempted from `no_mutation` or
  `mutation` diffs. A GET that changes any file in the materialized served-root
  bundle still fails `RT-9.1-get-no-mutate`; implementations that cache generated
  results should keep that cache outside the served tree or behind an internal
  store not visible to the corpus diff.
- `max_error_body_bytes` is the implementation's declared cap on diagnostic
  body bytes (runtime §10.3 recommends 8 KiB, truncation indicated). The harness
  records it and enforces it as a SHOULD-tier consistency check against the
  implementation's own declaration: any error response (4xx/5xx) carrying a body
  must not exceed the declared cap. This rides on the error vectors already in
  the suite, so it adds no fixtures, and it makes the field an enforced contract
  rather than unused metadata.
- `synthesized_resources.fixtures` is the complete set of optional synthesized
  targets the harness can assert for this implementation. Each fixture gives a
  raw target plus expected status, headers, and body matchers using the same
  vocabulary as vector `expect` blocks. `enabled: true` with an empty fixture list
  is informational only and runs no synthesized-resource vectors.
- `command_full_http_response.enabled` records whether an implementation supports
  commands that emit full HTTP responses. The flag is informational only in v1:
  the specs do not define a portable stdout protocol or metadata switch that lets
  the shared corpus distinguish "raw bytes" from "full HTTP response", so the
  harness does not materialize or assert implementation-specific command fixtures
  for this behavior.

Synthesized-resource fixtures use the same expectation vocabulary as vectors and
are validated by `capabilities.schema.json`:

```json
{
  "id": "docs-index",
  "root": "synthesized",
  "target": "/docs/index",
  "expect": {
    "status": 200,
    "header": { "Content-Type": "text/plain" },
    "body_exact": "wash-fixture: synthesized docs index\n"
  }
}
```

How tiers use it:

- **MUST tests** run for every implementation; failing one is non-conformance.
- **SHOULD tests** run for every implementation; failing produces a warning, not
  a hard failure, and is highlighted in the report.
- **Optional/implementation-defined tests** run only when the manifest declares
  the relevant capability, and they assert *internal consistency with the
  declaration* (for example, a declared symlink policy or concrete synthesized
  resource fixture). If a capability is declared absent, the matching tests are
  skipped and recorded as such. Literal-file MIME, directory index selection, and
  directory-listing policy are no longer manifest capabilities; they are
  normative behavior driven by root-local `env/` files.

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
| `PP-8.1-amp-name` | pipeline §8.1 | MUST | leading `&` stripped pre-decode; `%26` is a name char |
| `PP-9.2-no-cmd-in-dir` | pipeline §9.2 | MUST | no command lookup after dir traversal |
| `PP-9.1-trailing-q` | pipeline §9.1 | MUST | trailing `?` is resource query first |
| `PP-9.1-slash-collapse` | pipeline §9.1 | MUST | leading/trailing/repeated `/` collapse; trailing slash insignificant |
| `PP-9.4-dir-suffix` | pipeline §9.4 | MUST | directory suffix is evaluated through implied cat, never direct HTTP directory behavior |
| `PP-5.7-parse-raw` | pipeline §5.7 | MUST | `parse-mode raw` takes the encoded suffix, stops parsing |
| `PP-5.7-method-all-stages` | pipeline §5.7 | MUST | every stage must permit the request method |
| `PP-5.8-mime-final` | pipeline §5.8 | MUST | `mime` sets final-stage Content-Type; ignored mid-pipeline |
| `PP-5.9-stderr-field` | pipeline §5.9 | MUST | `stderr discard`/`merge` semantics |
| `PP-6-query-delim` | pipeline §6 | MUST | per-command query ends at next raw `/` |
| `PP-6.2-query-disables-arity` | pipeline §6.2 | MUST | query argv disables metadata path arity |
| `PP-7-mid-noncmd-400` | pipeline §7 | MUST | non-command middle segment (`/foo/bar/baz`) → 400 |
| `RT-6.5-dir-index` | runtime §6.5 | optional | declared default file > listing |
| `PP-11-headers` | pipeline §11 | optional | `X-WebShell-*` header names |
| `PP-9.5-synth` | pipeline §9.5 | optional | synthesized-resource behavior |
| `RT-R7-case` | audit R7 | optional | case-sensitivity (declared, not mandated) |
| `RT-9.5-head-explicit` | runtime §9.5 / audit R8 | optional | HEAD for an explicit `methods` list with GET but no HEAD (implementation-defined; not asserted) |

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
| `directories/` | Directory behavior (§6.5): one dir holding `index.html`, one without an index (listing enabled by default), trailing-slash equivalence and repeated-slash collapse (§9.1), directory used as an implied-cat suffix `/dirprobe/docs` (§9.4), and `/docs/grep/needle/file.txt` → 404 (no command lookup after directory traversal, §9.2). This root ships its own `env/path` + `dirprobe` (a fixture command that emits a fixed `dirprobe:` prefix before echoing any stdin) and `grep` (a tagging transform) commands and a real `docs/` directory, so the implied-cat-over-directory and no-command-in-directory vectors both have the fixtures they need. Directory serving is now normative: an index file wins over listing, an index-less directory lists when `env/listing` is absent or `on`, and roots can disable listing with `env/listing off`. The `/dirprobe/docs` implied-cat-over-directory case uses `one_of` expectations (§7.1) rather than a broad status wildcard: a success response must contain the `dirprobe:` marker, proving command execution rather than direct directory serving; a natural directory-read failure may return an error status, but the body must not contain the fixed direct-directory marker or default-index marker. |
| `env-serving/` | Root-local serving configuration: `env/mime` suffix/default Content-Type rules and `env/index` candidate ordering. |
| `env-listing-off/` | `env/listing off` behavior: index-less directories return 404 while matching index files still serve. |
| `env-mime-bad/` | Malformed `env/mime` produces a 500 for literal-file responses resolved through it. |
| `precedence/` | The §6.2 ladder. Contains a real file `wc` at root, a real file `bin/wc`, a real `grep/docs/file.txt`, and commands `wc`/`grep` on PATH. Proves exact-path-wins, `/bin/wc` serves file, `/grep/docs/file.txt` serves file. |
| `commands-mf/` | Metadata-free commands only (arity 0). `cat`-style pass-through, identity, line-count. Proves implied cat, multi-stage pipelines, and that path args → 400 (§13.1, §13.2 of pipeline). |
| `commands-arity/` | Commands with `arity 1`, `arity 2` (diff-like), `arity *`. Proves path-arg consumption, multi-resource via root-relative argv (§10.5), arity-star argv, and that a **path-arity** argument is percent-decoded and passed verbatim even when it contains a decoded `/` — `/echo1/a%2Fb/file.txt` with `echo1` arity 1 passes the single argv `a/b` (§5.1, Q21), distinct from the query-value encoding cases in `commands-query/`. |
| `commands-query/` | Query argv: `?arg=`, repeated `arg`, percent-encoded `/?&=` in values, query-disables-metadata-arity, core-arg-on-noncommand→400. |
| `body-input/` | Request body as stdin (§10.6, §12.4): `POST /transform` with a body feeds the rightmost stage's stdin; input suffix wins over body when both present; `arity *` suppresses the URL input suffix but the body still feeds stdin (§5.2); no suffix and no body → stdin closed and empty. |
| `commands-meta/` | Full metadata coverage: `methods`, `mutates`, `mime`, `stderr`, `exit` mappings, `parse-mode raw` (an `explain`-like command). |
| `meta-malformed/` | Each subdir/command has one deliberately malformed metadata field → each must 500. Coverage spans bad arity, bad `exit` pair, bad `mime`, bad `stderr`, `mutates true`+GET, each reserved input/output mode (`input file`, `input none`, `output file`; R2), both reserved range-arity forms (`arity 1..3`, `arity 0..*`; R4), and `parse-mode raw` not in leftmost position. |
| `pipelines/` | Realistic multi-stage pipelines (`jq`/`grep`/`wc` analogues with proper metadata) to validate the worked examples in pipeline §12 and runtime §8.4/§16.4. |
| `stderr/` | Commands that write to stderr; validates `/&` boundary semantics (§8) and `stderr merge` metadata (§5.9), single-boundary scoping, rightmost-prefix rule. |
| `exit-codes/` | Commands with deterministic exit codes + `exit` maps; validates default nonzero→400, custom maps, and pipefail aggregation (first-in-URL-order wins, §5.4). |
| `methods/` | Commands declaring `methods GET POST`, GET-only, mutating-with-POST; validates 405, every-stage-must-permit-method, and HEAD-from-GET. The HEAD assertion is made only for the metadata-absent default (GET permitted ⇒ HEAD answered, body omitted), which §9.5 states unambiguously; the vector pairs the HEAD with its GET via `head_of` and asserts matching status, omitted body, and only the explicitly named header expectations (§7.1). Whether an *explicit* `methods` list that includes GET but omits HEAD suppresses HEAD is genuinely ambiguous in §9.5 (the suppression sentence conflicts with the GET⇒HEAD default), so the harness does not assert HEAD behavior for explicit-list commands — it is recorded as implementation-defined until the spec resolves it (tracked as audit R8). |
| `mutation/` | PUT/DELETE/POST against plain files; validates literal targeting (§9.2/§9.4) and POST-to-plain→405 (§9.3). The MUST-level PUT/DELETE vectors target paths whose parent already exists, so the literal mutation is unambiguous; PUT into a missing parent is a separate vector gated on `put_creates_parents` (§4). Command-governed POST *write* semantics (e.g. the `sort output.txt/input.txt` redirection of §9.3) are command-specific, not defined by the core spec, so they are **not** a core MUST: this root ships a fixture command with declared write behavior and the vector asserts only consistency with that shipped command's contract (it exercises the impl's body/argv plumbing and method gating, not a portable redirection rule). **Run only on disposable copies.** |
| `exec-rules/` | `exec` interpreter rules: exact basename match, glob match against relative path, first-match-wins, comment/blank handling, malformed rule→500, unresolved interpreter→500 (§7.2, §15.5). The positive rules participate in interpreter substitution like other command roots; malformed-rule fixtures are authored so their invalidity is independent of the interpreter token, and unresolved-interpreter fixtures use a reserved missing-interpreter sentinel that substitution deliberately leaves untouched. |
| `encoding/` | Percent-encoding edge cases: `%5B%5D`, `%2F` in argv vs path, `%3F` literal `?` filename, `%26` literal-`&` command name, decoded NUL/`/` rejection in path segments. A decoded `/` or NUL is valid in an *argument* segment (§5.1, passed verbatim) but invalid in a *filesystem-lookup* segment (§9.1/§12.2); the spec marks the latter "invalid" without fixing a status, so those vectors assert `status_any: [400, 404]` rather than a single class. |
| `symlinks/` | Symlink policy checks gated on `symlink_policy` and host support. The materializer synthesizes an in-root symlink and a harmless escaping symlink to a sibling bundle file. `reject-escaping` asserts the escaping target is not served (allowed rejection statuses only, and body must not contain the outside bytes); `follow` asserts the declared follow behavior against the synthesized fixtures; `unsupported` skips the symlink vectors. |
| `synthesized/` | Optional synthesized-resource checks. Runs only when the capability manifest declares concrete synthesized fixture paths (for example `/docs/index`) and their expected status/body/header behavior; validates command-parse-beats-synth, exact-file-beats-synth precedence, and 400-is-terminal-no-fallback. |
| `path-outside/` | `env/path` pointing to `../shared/bin`; validates command dirs outside root work (§7.1) while literal file serving still rejects root escape (§12.2). Materialization copies this root as part of a fixture bundle that preserves the sibling `shared/bin` relationship. |
| `case/` | Files differing only by case; behavior gated on `case_sensitive_lookup` declaration (audit R7, optional). The case-colliding pair is **synthesized at run time** and the vectors skip on a case-insensitive host (§6.6) — it is not checked in. |

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
their output bytes. Most follow one **stage-tagging output contract**; a few
purpose-built commands deliberately deviate from it where a different, equally
byte-stable shape is what a clause needs (the bare-count `linecount` and the
write-redirecting `sort` below). The complete canonical set in `roots/_lib/` (each
shipped as a byte-compatible `.sh` and `.py` variant, §"Interpreter binding") is:

| `_lib/` command | Output shape | Used by |
|-----------------|--------------|---------|
| tagging transforms — `cat`/`identity`, `grep`, `jq`, `filter`, `count`, `dirprobe` | stage-tagging contract (below); `grep`/`filter` take `arity 1`, the rest arity 0; `dirprobe` emits a fixed `dirprobe:` prefix even when stdin is empty | `commands-mf/`, `precedence/` (`grep`), `directories/`, `pipelines/`, `stderr/` (`count`/`filter`) |
| `linecount` (a `wc` analogue) | **bare** line count only (`^\s*N\s*$`); not stage-tagged — an explicit exception so a direct-file-access and a piped-execution test each have a byte-stable body | `precedence/` (`wc`), `directories/` (`wc`) |
| argv-echo — `echo1` (arity 1), `echo2` (arity 2), `echoN` (arity *) | `argv=[a|b|...]` (plus file-existence flags for `echo2`) | `commands-arity/`, `commands-query/` |
| `noisy` | `out:‹record›` to stdout, `err:‹record›` to stderr | `stderr/` |
| `exitN` (a family, fixed exit code each) | one fixed line then exit `N` | `exit-codes/`, pipefail vectors |
| `transform` | stage-tagging contract; reads request-body stdin | `body-input/` |
| `sort` | **write-redirecting** per its declared `mutates`/method contract (runtime §9.3); not stage-tagged | `mutation/` |
| `explain` | `parse-mode raw`; echoes its received raw suffix | `commands-meta/` (the `parse-mode raw` command) |

A root is materializable for an implementation only if every command it serves has
a `_lib/` variant for a declared interpreter (§"Interpreter binding"); the table
above is the authoritative inventory `validate-roots` checks that against, so a
root referencing a command absent from `_lib/` is a corpus bug.

The stage-tagging contract (used by every command above except `linecount` and
`sort`):

- A transform stage reads stdin (treated as newline-separated records) and emits,
  for each record, a line `‹TAG›(‹argv…›):‹record›` — its own tag, its received
  argv joined by commas, and the record it passed through. Tags are the command's
  basename. **Record framing is fixed so `body_exact` is stable:** input is split on
  LF (`\n`) only; a single trailing `\n` terminates the last record and does **not**
  produce an extra empty record; an interior empty line *is* a record (emitted as
  `‹TAG›(‹argv…›):`); and CR is treated as an ordinary data byte (fixtures are
  authored LF-only, never CRLF). Each emitted line is LF-terminated. Fixture input
  files are likewise authored with explicit, known trailing-newline state so the
  expected output bytes are computable. Because each stage prepends its own tag, the final stdout encodes the
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

`roots/_lib/` holds the canonical implementations of every command in the
inventory table above (one `.sh` and one `.py` variant of each), and each root's
command files are copies of, or thin wrappers around, those canonical scripts so a
given command's output bytes are identical wherever it appears.

#### Interpreter binding: one canonical form, substitution at materialization

The checked-in corpus is **single-interpreter and concrete**, which keeps it
Git-friendly and lets `validate-roots` (§6.5) check what is literally on disk. The
canonical interpreter is POSIX `sh`:

- Each root's command files are checked in as real `sh` scripts (copied from the
  `.sh` variant in `_lib/`), and the root's checked-in `exec` file contains the
  literal rule(s) that bind them to `sh`.
- This `sh` form is the one `validate-roots` validates by default and the one a
  reader sees in the repository.

An adapter that declares `sh` in its TOML `interpreters` list gets this tree
copied verbatim at materialization. An adapter that does **not** declare
`sh` but **does** declare another interpreter the corpus supports (e.g. `python3`)
triggers an **interpreter-substitution pass** during materialization:

1. For each served command, the harness replaces the `sh` script with the
   corresponding `.py` variant from `_lib/` (same output contract, §6.3).
2. The harness rewrites the materialized `exec` file so every rule that bound the
   command to `sh` now binds it to the chosen interpreter.

Substitution is purely mechanical because `_lib/` guarantees a byte-compatible
variant per interpreter and the served command name carries no extension, so the
`exec` rewrite only changes the interpreter token. A root is materializable for an
implementation iff every command it serves has a `_lib/` variant for at least one
interpreter the adapter declares; otherwise the root's optional/capability-gated
vectors are `SKIP` and its selected MUST vectors are `UNTESTED`, all with
recorded reasons (§7.3). `validate-roots --interpreter python3` validates the
substituted form so the substitution pass itself is covered, not just the
checked-in `sh` baseline.

**Roots that test `exec`/interpreter binding.** The substitution pass is
syntax-aware enough to keep `exec-rules/` portable without rewriting away the
behavior under test. Rules that bind ordinary fixture commands to the canonical
`sh` interpreter are rewritten to the selected supported interpreter, exactly as in
other roots. Malformed-rule fixtures are invalid regardless of interpreter token
(for example, a one-token rule), so substitution cannot make them valid.
Unresolved-interpreter fixtures use a reserved sentinel interpreter name such as
`__wash_missing_interpreter__`; the materializer never substitutes that sentinel
and `validate-roots` asserts it is not listed in the implementation's
adapter `interpreters`. A selected MUST vector in `exec-rules/` is therefore `UNTESTED`
only when the implementation declares no interpreter for which the corpus has
fixture variants, not merely because it does not support POSIX `sh`.

### 6.4 Mutability and isolation

- Read-only vectors may share a materialized root when they do not assert
  post-request tree state.
- Any vector with `no_mutation`, any vector with a `mutation` expectation, and
  all PUT/DELETE/POST-write vectors get a fresh temp root. Each such vector is a
  single request evaluated against a pristine tree; there are no multi-request
  ordered scenarios, so the post-request diff always attributes any change to the
  one request under test.
- After such a vector, the harness diffs the temp tree against the pristine
  fixture to assert either *exactly* the intended mutation or no mutation at all
  (`RT-9.1-get-no-mutate`).
- The snapshot/diff model compares entry existence, entry type, file bytes,
  symlink targets, and executable mode bits only when a vector explicitly makes
  mode relevant. It ignores access times, modification times, creation times,
  ownership, platform-specific extended attributes, and directory timestamp churn.
  This keeps mutation assertions about observable served-tree content rather than
  host filesystem bookkeeping.
- The diff never ignores changes inside the materialized served-root bundle for a
  vector that asserts `no_mutation` or an exact `mutation`. Paths declared in
  `runtime_artifact_paths` (§4) are shown in diagnostics when they change, but they
  do not make a served-tree write conformant.
- Roots with external relatives, such as `path-outside/` and its sibling
  `shared/bin`, are materialized as bundles so relative command-path entries keep
  the same shape they had in the canonical corpus. The bundle is laid out as
  `‹tmp›/root/` (the served root, with `env/path` containing `../shared/bin`) and
  `‹tmp›/shared/bin/`, so the `../shared/bin` entry resolves relative to the
  served root exactly as it does in the checked-in corpus. The adapter is
  launched with `{root}` = `‹tmp›/root`. For a bundle, `no_mutation`/`mutation`
  diffing snapshots the **whole bundle** (`‹tmp›/`), not just the served root, so a
  command that writes into the sibling `../shared/bin` is still detected rather
  than silently missed.
- Some fixtures are **synthesized at materialization time** for host-dependent
  behavior, such as symlinks and case-colliding names. Root-local serving
  configuration is checked in as ordinary corpus data under `env/`, not generated
  from implementation declarations.
- Symlink fixtures for `symlinks/` are **not** checked in as real symlinks; they
  are synthesized into the materialized tree at run time and only when the
  platform supports symlink creation and the manifest declares a `symlink_policy`.
  On platforms or implementations without symlink support the symlink vectors are
  skipped with a recorded reason. This keeps `validate-roots` (§6.5) free of
  checked-in symlinks while still exercising the behavior where it is meaningful.

### 6.5 Generation vs checked-in

Roots are checked in as plain files (Git-friendly, matches the spec's ethos) in
their canonical `sh` form (§6.3). A `rootcorpus.py validate` command verifies
invariants before a run: required fixture files present, `env/path`/`exec`/`meta`
parse, no accidental executable bits that would mask "no exec bit needed" tests
(§4.4), and no checked-in fixtures of a kind the corpus is required to synthesize
at run time (symlinks, §6.4; case-variant files, §6.6). `validate-roots
--interpreter <name>` additionally materializes each root through the
interpreter-substitution pass (§6.3) and validates the substituted tree, so a
non-`sh` implementation's view of the corpus is checked too.

Two kinds of fixture are deliberately **never checked in** and are instead
synthesized into the materialized tree at run time, because they cannot be
represented portably in a Git working tree:

- **Symlink fixtures** (§6.4) — not all platforms create symlinks; checking them in
  would also break clones on restrictive filesystems.
- **Case-variant fixtures** (§6.6) — two names differing only by case cannot
  coexist in a case-insensitive working tree (e.g. macOS/APFS, the common
  development host), so they cannot be checked in at all.

`validate-roots` therefore asserts these are *absent* from the checked-in corpus;
the materializer adds them only where the platform and capability manifest make the
corresponding test meaningful.

### 6.6 Case-sensitivity fixtures (`case/`)

The `case/` root tests behavior gated on the `case_sensitive_lookup` declaration
(audit R7, optional). Its defining fixtures are two files whose names differ only
by case (e.g. `Readme` and `readme`). Because the development host is
case-insensitive, these **cannot** be checked in — the second file would collide
with the first. They are handled exactly like symlink fixtures (§6.4):

- The checked-in `case/` root contains only the case-insensitive scaffolding; the
  case-colliding pair is **synthesized into the materialized tree at run time**.
- Synthesis runs only when (a) the underlying temp filesystem is itself
  case-sensitive — probed once at run start by creating `A`/`a` in a scratch dir —
  and (b) the manifest declares `case_sensitive_lookup`.
- When either precondition fails, the case-collision vectors are **skipped with a
  recorded reason** (case-insensitive host filesystem, or capability not declared),
  never failed. An implementation is thus never penalized for the host filesystem's
  behavior, which the spec leaves implementation/host-defined (R7).

This keeps the corpus committable on macOS while still exercising case sensitivity
on hosts where it is observable.

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

- `status`, `status_any: [..]` where the spec permits a choice, or
  `status_class` (`success` = any 2xx, `non_error` = any 2xx/3xx,
  `client_error` = any 4xx, `server_error` = any 5xx) where the spec fixes only
  the response class and not the exact code.
- `one_of`: a list of complete expectation blocks, exactly one of which must
  match. This is reserved for spec-permitted alternatives, and each branch must be
  narrow enough to prove the relevant behavior. For example, the directory-suffix
  vector can allow either a success branch with `body_contains: "dirprobe:"` or a
  natural failure branch with an error status and `body_not_contains` guards,
  instead of accepting a broad uninspected status set.
- `body_exact`, `body_contains`, `body_not_contains`, `body_matches` (regex),
  `body_base64` (binary).
- `body_empty`: assert the response carries no entity body. This is how a HEAD
  vector asserts the omitted body (runtime §9.5) without an empty-string
  comparison that would be ambiguous against a missing body.
- `head_of`: names a sibling vector id whose request is the GET equivalent of this
  HEAD. The harness runs both and asserts the HEAD response reproduces the GET's
  status while `body_empty` holds. Header checks are limited to headers the vector
  explicitly names: for example, `Content-Type` may be compared when the GET
  response declares one, and `Content-Length` may be checked if the HEAD response
  includes it, but the harness does not require full header parity or require
  `Content-Length` to be present. This makes "computed as for GET, body omitted" a
  real assertion without imposing HTTP header choices the spec does not mandate.
- `header`: exact match; `header_present` / `header_absent`; `header_matches`.
  Response header names are matched case-insensitively and normalized to lowercase
  in the result model. Duplicate response headers are preserved as an ordered list
  of values. A string matcher requires exactly one value for that header; a list
  matcher requires the same ordered value list. Header values are compared as raw
  decoded header field values after RFC response parsing, with no MIME- or
  whitespace-specific normalization unless the matcher says so.
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
  exact text is non-normative (pipeline §10.1 diagnostics, §10.5 Accept
  negotiation).

A vector's `request` block supports:

- `method` and raw `target` (required).
- `headers` as exact wire header names and values, including `Origin` and
  `Accept`.
- `body_exact`, `body_base64`, or `body_file` for PUT/POST/stdin cases.

The schema rejects vectors that specify more than one body source. Omitted
headers mean no extra headers beyond the HTTP minimum; omitted body means an
empty request body.

`vector.schema.json` is the single source of truth for the full vector shape:
every matcher and condition introduced anywhere in this document — the `expect`
matchers above, `timeout_means` (§3.1), the capability/interpreter gates
`requires_capability` / `forbidden_when` / `requires_interpreter` (§7.3), and the
policy branches `when_writes_disabled` / `when_deletes_disabled` (§4) — is defined
as a field in that schema so none is silently dropped. `validate-vectors` loads
every YAML vector, rejects unknown fields, validates matcher combinations, and
checks that referenced clauses, roots, capabilities, and sibling `head_of` ids
exist. Schema fields mentioned in prose but not represented in
`vector.schema.json` are treated as phase-1 contract gaps before vectors are
authored.

A vector may also carry an optional top-level `timeout_means` (§3.1) with the
value `fail` (default) or `timeout`. It controls how a per-request deadline is
scored: `fail` for vectors where the spec requires the request to complete — the
closed-empty-stdin cases set it implicitly — and `timeout` only for vectors that
exercise a deliberately slow pipeline, where exceeding the deadline is a neutral
`TIMEOUT` rather than non-conformance.

### 7.2 Negative and ambiguity vectors

The spec is explicit that certain URLs are invalid. These get first-class
vectors asserting the precise status (400 vs 404 vs 500 vs 405), since the most
common implementation bug is the *wrong* error class:

- metadata-free path args → 400 (`/wc/-l/file.txt`).
- non-command middle segment with metadata-free commands → 400
  (`/foo/bar/baz/file.txt` where `foo`/`baz` are commands and `bar` is not, §7).
- core arg on non-command → 400.
- malformed metadata → 500 (not 400).
- POST to plain file → 405.
- method not permitted → 405.
- no resource, no command → 404.
- command-parse-started-then-failed is terminal (no synthesized fallback) → 400.

### 7.3 Capability-conditional vectors

Capability gates are structured predicates, not free-form strings. A vector may
carry `requires_capability` as either a shorthand boolean path (for boolean
manifest fields such as `writes_enabled`) or an object predicate:

```yaml
requires_capability:
  path: "symlink_policy"
  equals: "reject-escaping"
```

Supported predicate operators are `equals`, `not_equals`, `present`, `absent`,
`nonempty`, `contains`, and `matches_key` (for any remaining manifest maps). Paths use
dot notation over the capability manifest. `all` and `any` compose predicates for
multi-condition cases. `forbidden_when` uses the same predicate vocabulary for inverse
assertions, for example asserting that a response header is absent under a given
declared capability state.

When a predicate is false for an optional or implementation-defined vector, the
harness records `SKIP` with the evaluated predicate as the reason. When a
selected MUST vector is un-runnable because a required interpreter or corpus
fixture is unavailable, the harness records `UNTESTED` rather than `SKIP` (§10).
Note the harness only ever launches the implementation in its default
configuration (§3), so it tests the cross-origin-**disabled** default only — the
cross-origin response headers must be absent (§13.1) — and never drives a
cross-origin-enabled launch (there is no adapter or manifest switch to enable it,
and §3 forbids the adapter from pre-toggling defaults).

A vector (or its root) may carry `requires_interpreter: python3` (etc.). Because
`roots/_lib/` ships both `.sh` and `.py` variants of every fixture command, the
materializer's interpreter-substitution pass (§6.3) can bind a root to whichever
interpreter the adapter declares. A vector pins a specific interpreter via
`requires_interpreter` only when the behavior under test is interpreter-specific
(in which case substitution to another interpreter is not attempted). If an
optional or implementation-defined vector cannot run under the declared
interpreters, it is `SKIP`; if a selected MUST vector cannot run, it is `UNTESTED`
and blocks a complete conformance claim (§10).

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
- **Request-line contract.** Each request is `‹METHOD› ‹raw-target› HTTP/1.1`
  followed by exactly these framing headers, then the vector's own headers, then
  the body:
  - `Host:` set to the authority the harness dialed — the `origin_form` host plus
    the launch port (e.g. `127.0.0.1:54321`). HTTP/1.1 servers may reject a
    missing `Host` with 400, so the harness always sends one; the value is fixed
    and identical regardless of how many `?` the request-target contains.
  - `Connection: close`, and **one fresh TCP connection per request** (no
    keep-alive reuse). This keeps the sequential vectors in an isolation group
    independent and makes the liveness check (§3.1) a clean connect-per-request.
  - `Content-Length` for any request carrying a body. The harness does not send
    chunked request bodies.
  A vector may add or override `Origin`, `Accept`, etc.; it may not change the
  framing rules above (they are what make the raw-target test meaningful).
- Allow crafting cross-origin requests (an `Origin` header) to test §13.1.
- Allow request bodies without text transcoding, including binary PUT/POST bodies
  and POST bodies used as command stdin.
- Capture status, headers, and raw body bytes; never transcode the body.
- Frame the *response* correctly per RFC 7230 — honor `Content-Length` and
  decode `Transfer-Encoding: chunked` so the captured body is the exact entity
  bytes with no chunk headers leaking in. The "don't normalize" rule applies to
  the request line only; response framing must be standards-correct or
  `body_exact`/`body_base64` assertions silently corrupt.
- **HEAD responses carry no body.** The response parser must be told the request
  method so that a HEAD response — which may carry a `Content-Length` describing
  the body the equivalent GET *would* return — is read as header-only and does not
  block waiting for entity bytes that never arrive. The `methods/` root exercises
  HEAD-from-GET (§9.5), so a parser that ignores the method would hang there and be
  mis-scored against `timeout_means: fail`.
- Enforce a per-request timeout (§3.1); on expiry the socket is closed and the
  result is scored per the vector's `timeout_means` (a hang on a closed-stdin
  vector is non-conformance, not a neutral `TIMEOUT`).

This likely means a thin client that writes the raw request line over a
socket but reuses `http.client`'s response parser for correct framing, rather
than `requests`/`httpx`, whose request-side normalization would defeat the test.
The client module documents and tests both properties — verbatim request-target
out, RFC-correct entity bytes in — against a loopback echo so we trust the
harness itself.

---

## 9. Coverage and the audit boundary

- **Clause coverage report.** Cross-reference the clause registry (§5) with
  vectors; emit a table of clauses with zero vectors so the suite's own gaps are
  visible. Target 100% MUST-clause coverage before declaring the harness v1. The
  zero-vector check is only as good as the registry's completeness: the §5 table is
  illustrative, so the real `spec.py` registry must enumerate **every** MUST clause
  — including ones not shown there, e.g. runtime §6.4 (missing path → 404), §10.7
  (commands consuming URL expressions), the error-handling clauses runtime
  §15.1–§15.6 (notably §15.6 command-generated HTTP errors) and pipeline
  §10.2/§10.4/§10.5 (404 conditions, 500 cases, Accept-negotiated error format) —
  or an untested clause passes the gate by simply never appearing. Seeding the full MUST set into `spec.py` is part
  of phase 1 (§12), and the coverage tool reports only on under-tested *known*
  clauses, never on clauses the registry forgot.
- **Audit R1–R8 handling.** The `specs/audit.md` open items are *not* failures:
  - R1 (OPTIONS/CORS), R2 (`input file`/`output file`/`input none`), R3 (cwd
    override), R4 (range arity), R6 (`explain` contract) → vectors that assert the
    v1 *reserved* behavior (e.g. `input file` declared in metadata → 500; range
    arity → 500; OPTIONS is implementation-defined → only assert CORS-off
    default, not preflight specifics). The cross-origin-default assertion is
    concrete: against a default launch (§3), a GET carrying the fixed foreign
    `Origin: http://cross-origin.invalid` (which differs from the manifest's
    `origin_form`, §4) must come back **without an
    `Access-Control-Allow-Origin` header** (`header_absent`). The harness asserts
    only this header absence — it does not require the request to be rejected,
    since "disabled" means the browser blocks the response, not that the server
    returns an error.
  - R5 (quoting in metadata/exec) → vectors confirm whitespace-separated tokens
    only; values needing quoting are out of scope (not tested as supported).
  - R7 (case sensitivity) → optional tier, gated on the capability declaration.
  - R8 (HEAD for an explicit `methods` list that includes GET but omits HEAD) →
    optional tier (`RT-9.5-head-explicit`), recorded as implementation-defined and
    **not asserted**, because §9.5 sentences 1 and 2 contradict each other for this
    case. Only the metadata-absent default (GET permitted ⇒ HEAD answered, body
    omitted) is asserted, in the `methods/` root (§6.1). The clause appears in the
    registry so coverage reporting (§9) accounts for the deliberate non-assertion
    rather than treating it as a forgotten clause.
- **Synthesized resources.** Because synthesis is implementation-defined, the
  manifest must declare concrete synthesized fixture targets before synthesized
  vectors run. `synthesized_resources.enabled: true` with an empty `fixtures` list
  is informational only; it does not give the harness enough information to assert
  portable behavior.
- **Command-emitted full HTTP responses** (runtime §12.5, pipeline §5.8: a command
  setting its own status, headers, redirects, cookies, or overriding `mime`) are
  **implementation-defined and not portably testable**, because the spec never
  defines the mechanism by which a command signals "this is a full HTTP response"
  versus raw stdout bytes. The harness therefore does not assert this behavior by
  default. The `command_full_http_response.enabled` capability flag records
  whether an implementation supports it, and reports include that declaration, but
  no shared-corpus vectors are generated from it in v1.
- **Per-implementation scorecard.** MUST pass rate (must be 100% to be
  "conformant"), SHOULD pass rate, declared optional features and their
  consistency results, an explicit list of skipped optional/implementation-defined
  tests with reasons, and an explicit list of `UNTESTED` MUST vectors/clauses. A
  result set with any `UNTESTED` MUST vector is an incomplete conformance claim,
  even when every runnable MUST vector passes.

---

## 10. Reporting

Three reporters from one result model (`report.py`). Each (impl, root, vector)
record carries one outcome — `PASS`, `FAIL`, `SKIP` (with reason), `WARN`
(a failed SHOULD), `UNTESTED` (a selected MUST vector could not be run by the
available corpus/interpreter setup), `TIMEOUT` (§3.1/§8), `LAUNCH_FAILURE`
(§3.1, the server never became ready), or `PROCESS_DIED` (§3.1, the server was
ready but exited or crashed mid-group) — so an implementation problem, a
permitted optional skip, incomplete MUST coverage, a deliberately-slow timeout, a
broken adapter, and a runtime crash are never conflated. `PROCESS_DIED` is not a
spec `FAIL`: it carries the captured child output and, like `LAUNCH_FAILURE`,
points at the process rather than at a clause. `TIMEOUT` records only the neutral
slow-pipeline case (`timeout_means: timeout`); a deadline exceeded where the spec
requires the request to complete (the default `timeout_means: fail`, e.g. a stage
blocking because stdin was never closed) is a `FAIL`, since the hang is the
non-conformance itself.

1. **Human summary** (stdout): per impl, a tiered table (MUST/SHOULD/optional),
   the first N failures with clause id, the exact request target, expected vs
   actual status/body diff, and the cited spec section text.
2. **JSON** (`results.json`): machine-readable full results for dashboards or
   cross-run diffing; one record per (impl, root, vector) with timing.
3. **JUnit XML**: for CI integration; testcase names encode `impl/clause/vector`
   so CI surfaces regressions per clause.

Optional: a **conformance matrix** (markdown) — implementations as columns,
clauses as rows, ✓/✗/–/U (skip/untested) cells — to compare implementations at a
glance and track an implementation's progress over time.

A non-zero exit code if any MUST fails, if any selected MUST vector is
`UNTESTED`, or if any `LAUNCH_FAILURE` or `PROCESS_DIED` occurs (gate for CI — an
implementation that cannot stay up or leaves MUST coverage incomplete cannot be
called conformant); SHOULD/optional failures are warnings unless `--strict` is
passed.

---

## 11. CLI surface

```
# Run everything against one implementation:
wash-conformance run --adapter adapters/reference.toml

# Compare several:
wash-conformance run --adapter adapters/*.toml --report matrix

# Subset by clause, tier, or root:
wash-conformance run --adapter A.toml --tier MUST --root precedence
wash-conformance run --adapter A.toml --clause PP-5.4-exit-map

# Validate the corpus / a manifest without running an impl:
wash-conformance validate-roots
wash-conformance validate-vectors
wash-conformance validate-capabilities adapters/reference.toml

# Coverage of the vectors against the clause registry:
wash-conformance coverage
```

Under the hood these are pytest invocations with parametrization, so
`pytest`-native flags (`-k`, `-x`, `-n` for parallelism) also work.

---

## 12. Build order (suggested phases)

0. **Minimal reference implementation.** A small `wash` server (Python, launched as
   `python -m wash.server`) covering the MVP
   surface (runtime.md §18): literal GET, basic directory behavior, PUT/DELETE,
   `env/path`, `exec`, `env/meta/<command>`, left-to-right resolution, child
   process per request, the error classes, and cross-origin off by default. It
   lives under `impls/reference/` with its own adapter and capability manifest and
   gets no special treatment from the harness — it is the green target the
   vertical slice (phase 4) first runs against, and is then grown to full v1
   coverage root-by-root in phase 5 (§12) so it stays the green oracle for the
   whole corpus. "The reference is just another adapter" keeps the harness honest
   and language-neutral throughout.
1. **Skeleton + contracts.** `pyproject.toml`, the two JSON Schemas
   (capabilities, vector), `spec.py` clause registry seeded with MUST clauses,
   `validate-capabilities`, `validate-vectors`, and `report.py` result model. No
   server interaction yet.
2. **Non-normalizing HTTP client** (§8) with a self-test against a loopback echo.
3. **Adapter lifecycle** (§3): launch/ready/teardown, both port modes
   (`assigned` with bind-failure retry, and `ephemeral` port readout), root
   materialization (including interpreter substitution, §6.3, and runtime
   synthesis of symlink/case fixtures, §6.4/§6.6) + post-run diff.
4. **First vertical slice:** the `precedence/` and `commands-mf/` roots, with
   their vectors authored in this phase (not deferred to phase 5), run against a
   reference implementation, green end to end.
5. **Fill the remaining corpus** root by root (§6 table), writing vectors
   alongside each — and **extending the reference implementation to pass each
   root's MUST vectors before moving to the next root.** The reference grows from
   the phase-0 MVP to full v1 coverage here (path arity, query argv, exit maps +
   pipefail, `parse-mode raw`, `stderr merge`, `methods`/405, `mime`), staying the
   green oracle across the entire corpus. This is what makes the corpus
   self-validating: a mis-authored MUST expectation is caught because a known-good
   reference exercises it. A root is "done" only when its MUST vectors are green
   against the reference; SHOULD/optional gaps in the reference are recorded in its
   capability manifest rather than left as silent failures.
6. **Capability gating** (§4) and the optional/SHOULD tiers.
7. **Coverage + reporters** (§9, §10), then the comparison matrix.
8. **CI wiring** for `validate-roots`, `validate-vectors`,
   `validate-capabilities`, coverage, and a `--strict` gate.

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
- **Parallelism.** Per-launch isolation (§2) makes parallel runs safe, and the
  port-binding contract (§3.1) handles the pick-then-bind race via `assigned`-mode
  retry or `ephemeral` port readout. Remaining to confirm under `pytest -n`:
  temp-root cleanup under worker crashes, and the one-time case-sensitivity probe
  (§6.6) running once per session rather than once per worker.
