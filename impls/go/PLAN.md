# Go Port Implementation Plan for wash

## Overview

This document outlines the implementation plan for a Go port of the wash Web Shell specification, targeting full conformance with all MUST and SHOULD clauses defined in `specs/runtime.md` and `specs/pipeline_parsing.md`.

## Target Specifications

- **Go Version**: Latest stable (1.23+)
- **Spec Conformance**: Full (all MUST and SHOULD clauses)
- **Platforms**: macOS and Linux (primary), others as feasible
- **Dependencies**: Minimal stdlib-only with noted alternatives

## Architecture

### Module Structure

Module path: `github.com/curtcox/wash/impls/go` (matches the `origin` remote;
`internal/...` import lines and `internal/` visibility are derived from it).

```
impls/go/
├── go.mod                    # Module github.com/curtcox/wash/impls/go (go 1.23)
│                             # No go.sum while stdlib-only — the file is absent,
│                             # not empty; it appears only once a dependency is added.
├── wash.capabilities.json    # Capability declaration
├── bin/                      # Build artifacts (gitignored): wash-server binary
├── cmd/
│   └── wash-server/
│       └── main.go           # Sole entry point: CLI flags, server bootstrap
├── internal/
│   ├── server/               # HTTP server, routing, handlers
│   │   ├── server.go         # HTTP server setup
│   │   ├── handler.go        # Request handler
│   │   ├── response.go       # Response building
│   │   └── middleware.go     # CORS, logging (optional)
│   ├── parser/               # URL pipeline parsing
│   │   ├── parser.go         # Main parsing logic
│   │   ├── segment.go        # Segment parsing (stderr merge, query strings)
│   │   ├── pipeline.go       # Pipeline construction
│   │   └── precedence.go     # Resolution precedence ladder
│   ├── filesystem/           # File/directory operations
│   │   ├── root.go           # Root directory, path resolution
│   │   ├── file.go           # File reading, MIME inference
│   │   ├── dir.go            # Directory listing
│   │   ├── mutation.go       # PUT, DELETE operations
│   │   └── symlink.go        # Symlink handling
│   ├── metadata/             # Command metadata
│   │   ├── loader.go         # env/meta/* loading
│   │   ├── parser.go         # Line-oriented metadata parsing
│   │   ├── validator.go      # Metadata validation
│   │   └── defaults.go       # Default metadata values
│   ├── executor/             # Command execution
│   │   ├── executor.go       # Pipeline execution
│   │   ├── interpreter.go    # Interpreter rule resolution
│   │   ├── stage.go          # Single stage execution
│   │   └── pipe.go           # Pipeline plumbing
│   └── config/               # Configuration
│       ├── path.go           # Command path loading
│       └── exec.go           # exec rule loading
├── pkg/
│   └── wash/                 # Public API (optional, may be internal-only)
└── testdata/                 # Internal test fixtures
```

### Key Interfaces

```go
// Parser transforms HTTP request-target into parse result
package parser

type Parser interface {
    Parse(rawTarget string, root string, method string) (ParseResult, error)
}

type ParseResult interface {
    IsFilesystem() bool
    IsPipeline() bool
    IsNotFound() bool
}

// Executor runs command pipelines
package executor

type Executor interface {
    Execute(ctx context.Context, pipeline Pipeline, stdin io.Reader) (*Result, error)
}

type Pipeline struct {
    Stages []Stage
    InputSuffix string  // may be empty
    RequestBody io.Reader // may be nil
}

// Filesystem handles root-relative operations
package filesystem

type FS interface {
    ResolveExact(path string) (*Resource, error)
    ReadFile(path string) ([]byte, error)
    ListDir(path string) (*DirListing, error)
    PutFile(path string, data []byte, createParents bool) error
    DeleteFile(path string) error
    CheckEscape(path string) error
}
```

## Spec Clause Mapping

This table is the full contract: every clause in the conformance registry
(`harness/conformance/spec.py`) is listed, in registry order, with its tier and
the Go component responsible for it. **Source of truth is `spec.py`** — if a
clause is added or retiered there, update this table or conformance drifts.
66 clauses total — 57 MUST, 4 SHOULD, 5 optional. Implementation must pass all
MUST and SHOULD; optional clauses are gated by `wash.capabilities.json` (declare
a capability ⇒ the matching optional vectors run and must pass; leave it off ⇒
they are skipped).

### runtime.md

| Clause | Tier | Component | Notes |
|--------|------|-----------|-------|
| RT-4.2-root-valid | MUST | `filesystem.NewRoot`, `server.Server` | Empty root directory is valid; server still starts |
| RT-6.1-literal-file | MUST | `filesystem.ResolveExact` | Plain URL path maps literally to root file before any command parse |
| RT-6.2-precedence | MUST | `parser.Parse` | Ladder: exact file > command > synthesized > 404 |
| RT-6.3-direct-cmd-file | MUST | `filesystem.ReadFile` | Concrete path to a command file serves its bytes |
| RT-6.4-missing-path | MUST | `parser.Parse`, `server.Handler` | No parse + no resource → 404 |
| RT-6.5-dir-index | optional | `filesystem.ListDir` | Declared index file wins over listing (gated by `default_index_files`) |
| RT-7.1-command-path | MUST | `config.LoadCommandPath` | `env/path` line-oriented search path |
| RT-7.2-exec-rules | MUST | `config.LoadExecRules`, `executor.Interpreter` | First-match-wins; malformed rule → 500 |
| RT-9.1-get-no-mutate | MUST | `server.Handler` | GET must not mutate local state |
| RT-9.2-put-literal | MUST | `server.Handler`, `filesystem.PutFile` | PUT targets literal path, no command parsing |
| RT-9.3-post-plain-405 | MUST | `server.Handler` | POST to plain file/dir without governing command → 405 |
| RT-9.4-delete-literal | MUST | `server.Handler`, `filesystem.DeleteFile` | DELETE targets literal path, no command parsing |
| RT-9.5-head-from-get | MUST | `server.Handler` | GET permitted ⇒ HEAD answered with body omitted |
| RT-9.5-methods-405 | MUST | `parser.checkMethods`, `metadata` | Method not in `methods` metadata → 405 |
| RT-9.5-head-explicit | optional | `server.Handler` | HEAD when explicit methods list has GET but not HEAD (not asserted) |
| RT-10.4-invalid-parse | MUST | `server.Handler` | Client-controlled parse errors → 400 |
| RT-10.5-multi-resource | MUST | `parser.consumeArgv`, `executor` | Command may consume multiple root-relative resources via arity |
| RT-10.6-request-body | MUST | `executor.Pipeline`, `server.Handler` | Request body feeds rightmost stage stdin; **input suffix wins over body** |
| RT-10.7-url-expr | MUST | `parser.RawCommandParse` | parse-raw consumes remaining URL expression and stops parsing |
| RT-12.2-request-handling | MUST | `server.Handler`, `parser` | Parse the **raw** request-target: read `r.RequestURI`, never `r.URL.Path` (Go's `net/http` path-cleans the latter). No `net/url` normalization before parse |
| RT-12.2-root-escape | MUST | `filesystem.CheckEscape` | Literal serving rejects paths escaping configured root |
| RT-12.3-cwd-root | MUST | `executor.Stage` | Command cwd defaults to root for root-relative argv |
| RT-13.1-cors-default | SHOULD | `server.middleware` | No `Access-Control-Allow-Origin` by default |
| RT-13.2-mutating-methods | MUST | `server.Handler`, `metadata.Validate` | Mutation requires explicit method/metadata opt-in |
| RT-15.1-not-found | MUST | `server.Handler` | No resource and no parse → 404 |
| RT-15.2-invalid-parse | MUST | `server.Handler` | Invalid parse → 400 with diagnostics |
| RT-15.3-exit-status | MUST | `executor.Stage`, `metadata.ExitMap` | Nonzero exit mapped to error status with diagnostics |
| RT-15.5-interpreter-fail | MUST | `executor.Interpreter` | Unresolved interpreter → 500 |
| RT-15.6-cmd-http-errors | MUST | `executor.Result`, `server.Handler` | Command-generated HTTP errors surfaced per contract |
| RT-R7-case | optional | `filesystem.ResolveExact` | Case sensitivity consistent with `case_sensitive_lookup` |

### pipeline_parsing.md

| Clause | Tier | Component | Notes |
|--------|------|-----------|-------|
| PP-2-parse-algo | MUST | `parser.Parse` | Normative left-to-right algorithm + precedence ladder |
| PP-4-arity0-default | MUST | `metadata.Defaults`, `parser` | Metadata-free ⇒ arity 0, closed-empty stdin when no suffix/body |
| PP-4-implied-cat | MUST | `executor.Pipeline` | Rightmost suffix fed via implied `cat` primitive |
| PP-5.1-arity-n | MUST | `metadata.Parse`, `parser.consumeArgv` | Arity N consumes N segments as argv |
| PP-5.2-arity-star | MUST | `metadata.Parse`, `parser.consumeArgv` | Arity `*` consumes rest of URL; no input suffix |
| PP-5.3-input-stdout | MUST | `executor.Stage` | v1 stdin/stdout modes; reserved modes → 500 |
| PP-5.4-exit-map | MUST | `executor`, `metadata.ExitMap` | exit→status with pipefail aggregation (first in URL order wins) |
| PP-5.5-malformed-500 | MUST | `metadata.Validate` | Malformed recognized field → 500 |
| PP-5.7-parse-raw | MUST | `parser.RawCommandParse` | parse-raw takes encoded suffix and stops parsing |
| PP-5.7-method-all-stages | MUST | `parser.checkMethods` | Every stage must permit the request method |
| PP-5.7-mutates-get-invalid | MUST | `metadata.Validate` | GET permitted + mutates=true is invalid → 500 |
| PP-5.8-mime-final | MUST | `executor.Result` | `mime` sets final-stage Content-Type; ignored mid-pipeline |
| PP-5.9-stderr-field | MUST | `executor.Stage` | stderr discard/merge semantics for response body |
| PP-6-query-delim | MUST | `parser.segment` | Per-command query ends at next raw `/` |
| PP-6.1-core-arg | MUST | `parser.segment` | `arg` is the only core query parameter |
| PP-6.2-query-disables-arity | MUST | `parser.Pipeline` | Query argv disables metadata path arity for that command |
| PP-6.3-arg-noncmd-400 | MUST | `parser.segment` | Core `arg` on non-command segment → 400 |
| PP-7-mid-noncmd-400 | MUST | `parser.Parse` | Non-command middle segment with metadata-free commands → 400 |
| PP-8-stderr-prefix | MUST | `parser.segment` | `/&` prefix merges exactly one pipeline boundary |
| PP-8.1-amp-name | MUST | `parser.segment` | Leading `&` stripped pre-decode; `%26` is a name character |
| PP-9.1-trailing-q | MUST | `parser.segment` | Trailing `?` in final segment is resource query before command reinterpretation |
| PP-9.1-slash-collapse | MUST | `parser.segment` | Leading/trailing/repeated `/` collapse; trailing slash insignificant |
| PP-9.1-invalid-segment | MUST | `parser.segment`, `filesystem` | Decoded `/` and NUL invalid in filesystem-lookup segments |
| PP-9.2-no-cmd-in-dir | MUST | `parser.Parse` | No command lookup after directory traversal |
| PP-9.3-args-before-suffix | MUST | `parser.consumeArgv` | Path arity arguments consumed before input suffix |
| PP-9.4-dir-suffix | MUST | `parser.Parse`, `executor.Pipeline` | Directory suffix evaluated via implied `cat`, not HTTP directory behavior |
| PP-9.5-synth | optional | `server.Handler` | Synthesized resource behavior (disabled in capabilities) |
| PP-9.5-parse-terminal | MUST | `parser.Parse` | Started-command parse failure is terminal; no synthesized fallback |
| PP-10.1-400-diagnostics | SHOULD | `server.response` | 400 bodies include parse-failure diagnostics |
| PP-10.2-404 | MUST | `server.Handler` | 404 when no resource, no synth, no command parse can start |
| PP-10.3-exit-diagnostics | SHOULD | `server.response`, `executor` | Nonzero-exit bodies include command/exit/pipeline diagnostics |
| PP-10.4-500 | MUST | `server.Handler`, `metadata` | Malformed metadata + server-side failures → 500 |
| PP-10.5-error-format | SHOULD | `server.response` | Error bodies content-negotiated via `Accept` |
| PP-11-headers | optional | `server.response` | `X-WebShell-*` execution metadata headers when declared (`execution_metadata_headers`) |
| PP-13.1-mf-path-args | MUST | `parser`, `metadata.Defaults` | Metadata-free path arguments invalid → 400 |
| PP-13.2-mf-multi-path-args | MUST | `parser` | Metadata-free multi-command path args invalid → 400 |

## Implementation Order

### Phase 1: Foundation
1. **Project skeleton**: `go.mod`, `main.go`, basic HTTP server
2. **Filesystem module**: Root resolution, exact path lookup, root-escape detection
3. **Basic file serving**: GET for literal files, MIME inference by extension
4. **Adapter manifest + build target**: `harness/adapters/go.toml` pointing at the
   pre-built `impls/go/bin/wash-server`, plus a `build-go` Makefile target (see
   Integration Testing). Verify a build → conformance loop works end to end before
   layering on behavior.

**Milestones**: Can serve static files from root directory; passes `plain-files` vectors

### Phase 2: Command Path & Metadata
1. **Command path loading**: `env/path` parsing
2. **Metadata loader**: `env/meta/*` file reading
3. **Metadata parser**: Line-oriented format, field validation
4. **Basic command execution**: Single command, no pipeline

**Milestones**: Commands resolve from path; metadata loads; basic command execution works

### Phase 3: Pipeline Parsing
1. **Segment parsing**: Raw target split, percent-decoding, query string extraction
2. **Precedence ladder**: Exact file → command → synthesized → 404
3. **Pipeline construction**: Multi-stage pipeline with argv consumption
4. **Arity handling**: Fixed arity, arity star, query argv

**Milestones**: Complex pipelines parse correctly; passes `pipelines` and `commands-*` vectors

### Phase 4: Execution Engine
1. **Interpreter rules**: `exec` file parsing, glob matching
2. **Stage execution**: Subprocess management, stdin/stdout plumbing
3. **Pipeline plumbing**: Multi-stage data flow, stderr handling
4. **Exit code mapping**: Exit map evaluation, HTTP status derivation

**Milestones**: Full pipeline execution; passes `exec-rules`, `exit-codes`, `stderr` vectors

### Phase 5: HTTP Methods & Mutation
1. **PUT support**: Literal file creation/replacement, parent directory creation
2. **DELETE support**: File deletion
3. **POST support**: Command-governed POST handling
4. **HEAD support**: Derived from GET
5. **Method validation**: Metadata methods field enforcement

**Milestones**: Full CRUD support; passes `mutation`, `methods` vectors

### Phase 6: Advanced Features
1. **Directory handling**: Index files, directory listing
2. **Symlink support**: Symlink resolution, escape detection
3. **Error responses**: Content negotiation (JSON vs text)
4. **Case sensitivity**: Case-sensitive lookup option
5. **CORS handling**: OPTIONS responses

**Milestones**: All advanced features; passes `directories`, `symlinks`, `security` vectors

### Phase 7: Conformance & Polish
1. **Full conformance run**: All MUST/SHOULD vectors
2. **Performance tuning**: Streaming for large files, pipeline optimization
3. **Edge cases**: Encoding quirks, malformed input handling
4. **Documentation**: API docs, usage guide

**Milestones**: 100% conformance; production-ready

## Testing Strategy

### Conformance-Driven Development

The implementation uses the existing conformance harness:

```bash
# Run specific vector against Go implementation
wash-conformance run --adapter harness/adapters/go.toml --root plain-files

# Run all MUST tier vectors
wash-conformance run --adapter harness/adapters/go.toml --tier MUST

# Run full conformance suite
wash-conformance run --adapter harness/adapters/go.toml
```

### Unit Testing

Internal packages have unit tests for logic that is:
- Complex (parsing edge cases)
- Error-prone (path escaping)
- Performance-critical (streaming)

Example test structure:
```go
// internal/parser/parser_test.go
func TestParseSegment(t *testing.T) {
    cases := []struct {
        raw      string
        wantName string
        wantQuery map[string][]string
    }{...}
}
```

### Integration Testing

Use the harness vectors as the primary integration test suite.

**Build the binary first — the adapter does not compile.** The adapter schema
(`harness/conformance/adapter.py`) only runs `start`/`stop`; it has no build
hook. The harness launches a *fresh server process per root* (≈22 roots, many
times across a full run), so a `start = ["go", "run", ...]` line would recompile
on every launch and pay the Go compile cost each time. Worse, a cold first
compile can exceed `ready_timeout_sec = 10` and produce flaky readiness
failures. So `start` must point at a **pre-built binary**:

```toml
# harness/adapters/go.toml
name        = "go"
start       = ["impls/go/bin/wash-server", "--root", "{root}", "--port", "{port}"]
stop        = "SIGTERM"
port_mode   = "assigned"
ready       = { type = "tcp" }
ready_timeout_sec = 10
cwd         = "."          # paths in `start` resolve from repo root
env         = {}
capabilities = "impls/go/wash.capabilities.json"
```

The binary is produced out-of-band before conformance runs. Add Makefile
targets and wire them into the gate so `harness/adapters/go.toml` always has a
fresh binary to launch. The existing `lint`/`typecheck`/`unit` targets are
Python-only (`ruff`/`mypy`/`pytest`); Go needs its own equivalents
(`gofmt`/`go vet`/`go test`) — none of which exist yet:

```makefile
build-go:
	cd impls/go && go build -o bin/wash-server ./cmd/wash-server

lint-go:
	cd impls/go && test -z "$$(gofmt -l .)" && go vet ./...

test-go: build-go        # Go unit tests (*_test.go)
	cd impls/go && go test ./...

conformance-go: build-go
	wash-conformance run --adapter harness/adapters/go.toml
```

**Gate wiring.** `make test` (the repo CI gate per `AGENTS.md`) currently runs
`validate unit lint typecheck conformance` — all reference-only. Keep the Go
checks out of that target so a missing Go toolchain never breaks the reference
gate; instead expose an umbrella `test-go-all` and run it as a **separate CI
job** alongside (not inside) the reference job:

```makefile
test-go-all: lint-go test-go conformance-go
```

**CI.** Mirror both halves of `.github/workflows/conformance.yml`, not just the
`conformance` job:

- The `validate` job must also validate the new adapter/capabilities pair —
  add `wash-conformance validate-capabilities harness/adapters/go.toml`
  alongside the existing `reference.toml` line (this needs the harness installed,
  which the `validate` job already does; no Go toolchain required for it).
- Add a Go job (`needs: validate`) that runs `actions/setup-go`, then
  `make test-go-all`. Use `go build` in place of the reference job's editable
  `pip install`. Process cleanup needs no special handling: the harness sends
  `SIGTERM` to the whole process group (`os.killpg`, with
  `start_new_session=True`), so a single compiled binary is reaped cleanly on
  shutdown.

`impls/go/bin/` is a build artifact — add it to `.gitignore`.

**Single entry point.** No Go sources exist yet (`impls/go/` holds only this
plan); create exactly one `main` package, at `./cmd/wash-server`, and build only
from there. Do not add a second root-level `main.go`.

## Noted External Libraries

While the implementation is stdlib-only, these libraries would provide significant benefit if added:

| Library | Purpose | Benefit |
|---------|---------|---------|
| `github.com/spf13/cobra` | CLI framework | Flag parsing, subcommands, help generation |
| `github.com/go-chi/chi` | HTTP routing | Clean routing, middleware pattern |
| `github.com/stretchr/testify` | Testing | Assertions, test suites |
| `github.com/gobwas/glob` | Glob matching | Faster, more correct glob matching for exec rules |

## Capability Declaration

This mirrors `impls/reference/wash.capabilities.json` exactly. Keep it in lock-step
with the reference unless the Go impl deliberately diverges — the harness uses
these flags to decide which optional-tier vectors apply, so an unintended extra
entry (e.g. an `.html` MIME mapping the reference omits) silently changes which
vectors run against the Go server.

```json
{
  "spec_version": "1",
  "origin_form": "http://127.0.0.1",
  "directory_listing": true,
  "default_index_files": ["index.html"],
  "synthesized_resources": { "enabled": false, "fixtures": [] },
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
  "put_creates_parents": true,
  "runtime_artifact_paths": [],
  "interpreters": ["sh", "python3"],
  "command_full_http_response": { "enabled": false }
}
```

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Subprocess streaming complexity | Use `io.Pipe`, thorough testing with large files |
| Path traversal attacks | Aggressive root-escape validation, harness security vectors |
| Metadata parsing edge cases | Fuzz testing, comprehensive malformed metadata vectors |
| Platform differences (macOS/Linux) | CI testing on both platforms, avoid platform-specific syscalls |
| Performance with many pipeline stages | Benchmarks, goroutine pool limits |

## Success Criteria

1. **Conformance**: Pass all MUST and SHOULD tier vectors (57 MUST + 4 SHOULD
   clauses). Optional-tier clauses (5) are in scope only where the matching
   capability is declared — with the capabilities above, dir-index, case, and
   `X-WebShell-*` header vectors run and must pass, while synthesized-resource
   vectors are expected to be skipped (declared disabled), not passed.
2. **Performance**: Comparable or better than Python reference on benchmark roots
3. **Compatibility**: Drop-in replacement via adapter manifest change
4. **Maintainability**: Clear module boundaries, comprehensive comments

## Appendix: Reference Implementation Notes

Key insights from Python reference (`impls/reference/wash/`):

- **server.py**: Uses `ThreadingHTTPServer`; Go equivalent is `net/http` with goroutines
- **parser.py**: Complex left-to-right parse with backtracking; Go uses explicit state machine
- **executor.py**: `selectors` module for subprocess I/O; Go uses `io.Copy` goroutines
- **filesystem.py**: `pathlib.Path` operations; Go uses `path/filepath` and `os`
- **metadata.py**: Line-oriented text parsing; Go uses `bufio.Scanner`

## Appendix: Vector Coverage Matrix

| Vector File | Primary Components | Estimated Complexity |
|-------------|-------------------|---------------------|
| `plain-files.yaml` | filesystem | Low |
| `directories.yaml` | filesystem, server | Low |
| `precedence.yaml` | parser | Medium |
| `pipelines.yaml` | parser, executor | High |
| `commands-arity.yaml` | parser, metadata | Medium |
| `commands-mf.yaml` | parser, metadata | Medium |
| `commands-query.yaml` | parser | Medium |
| `commands-meta.yaml` | parser, metadata, executor | High |
| `exec-rules.yaml` | config, executor | Medium |
| `exit-codes.yaml` | metadata, executor | Medium |
| `stderr.yaml` | executor | Medium |
| `methods.yaml` | parser, server | Medium |
| `mutation.yaml` | filesystem, server | Medium |
| `body-input.yaml` | executor, server | Medium |
| `encoding.yaml` | parser | Medium |
| `case.yaml` | filesystem | Low |
| `symlinks.yaml` | filesystem | Medium |
| `security.yaml` | filesystem, parser | Medium |
| `path-outside.yaml` | config | Low |
| `synthesized.yaml` | server | Low (disabled) |
| `meta-malformed.yaml` | metadata | Medium |
| `empty.yaml` | all | Low |

---

**Last Updated**: 2026-06-09  
**Plan Version**: 1.0
