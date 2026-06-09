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

```
impls/go/
├── go.mod                    # Module definition (go 1.23)
├── go.sum                    # Dependency checksums (empty for stdlib-only)
├── main.go                   # Entry point, CLI flags
├── wash.capabilities.json    # Capability declaration
├── cmd/
│   └── wash-server/
│       └── main.go           # CLI wrapper
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

### runtime.md §6: URL-to-directory Mapping

| Clause | Component | Notes |
|--------|-----------|-------|
| RT-6.1-literal-file | `filesystem.ResolveExact` | Exact path resolution before command parse |
| RT-6.2-precedence | `parser.Parse` | Precedence ladder: exact > command > synthesized > 404 |
| RT-6.3-direct-cmd-file | `filesystem.ReadFile` | Direct file access to command files |
| RT-6.4-missing-path | `parser.Parse`, `server.Handler` | 404 for unresolvable paths |
| RT-6.5-dir-index | `filesystem.ListDir` | Index.html precedence over listing |

### runtime.md §7: Directory Layout

| Clause | Component | Notes |
|--------|-----------|-------|
| RT-7.1-command-path | `config.LoadCommandPath` | `env/path` line-oriented loading |
| RT-7.2-exec-rules | `config.LoadExecRules` | `exec` file parsing, glob matching |

### pipeline_parsing.md §2: Parse Algorithm

| Clause | Component | Notes |
|--------|-----------|-------|
| PP-2-parse-algo | `parser.Parse` | Left-to-right algorithm implementation |
| PP-4-arity0-default | `metadata.Defaults` | Arity 0, stdin/stdout defaults |
| PP-4-implied-cat | `executor.Pipeline` | Runtime primitive for input suffix |

### pipeline_parsing.md §5: Metadata

| Clause | Component | Notes |
|--------|-----------|-------|
| PP-5.1-arity-n | `metadata.Parse`, `parser.consumeArgv` | Fixed arity consumption |
| PP-5.2-arity-star | `metadata.Parse`, `parser.consumeArgv` | Variable arity (rest-of-URL) |
| PP-5.3-input-stdout | `executor.Stage` | stdin/stdout mode handling |
| PP-5.4-exit-map | `executor.Stage`, `metadata.ExitMap` | Exit code to HTTP status |
| PP-5.5-malformed-500 | `metadata.Validate` | Return 500 for malformed metadata |
| PP-5.7-parse-raw | `parser.RawCommandParse` | parse-mode raw handling |
| PP-5.7-method-all-stages | `parser.checkMethods` | Method gate for all stages |
| PP-5.7-mutates-get-invalid | `metadata.Validate` | GET + mutates=true = 500 |
| PP-5.8-mime-final | `executor.Result` | Final stage Content-Type |
| PP-5.9-stderr-field | `executor.Stage` | discard/merge semantics |

### pipeline_parsing.md §6: Query Strings

| Clause | Component | Notes |
|--------|-----------|-------|
| PP-6-query-delim | `parser.segment` | Per-command query delimited by next / |
| PP-6.1-core-arg | `parser.segment` | arg parameter handling |
| PP-6.2-query-disables-arity | `parser.Pipeline` | Query argv overrides path arity |
| PP-6.3-arg-noncmd-400 | `parser.segment` | arg on non-command = 400 |

### pipeline_parsing.md §8: Stderr Pipeline

| Clause | Component | Notes |
|--------|-----------|-------|
| PP-8-stderr-prefix | `parser.segment` | & prefix parsing |
| PP-8.1-amp-name | `parser.segment` | Leading & stripped pre-decode |

### HTTP Methods (§9)

| Clause | Component | Notes |
|--------|-----------|-------|
| RT-9.1-get-no-mutate | `server.Handler` | GET must not mutate |
| RT-9.2-put-literal | `server.Handler` | PUT targets literal path |
| RT-9.3-post-plain-405 | `server.Handler` | POST without command = 405 |
| RT-9.4-delete-literal | `server.Handler` | DELETE targets literal path |
| RT-9.5-head-from-get | `server.Handler` | HEAD derived from GET |
| RT-9.5-methods-405 | `parser.checkMethods` | Method not in metadata = 405 |

### Error Handling

| Clause | Component | Notes |
|--------|-----------|-------|
| RT-15.1-not-found | `server.Handler` | 404 for no resource/parse |
| RT-15.2-invalid-parse | `server.Handler` | 400 for parse errors |
| RT-15.3-exit-status | `executor.Stage` | Nonzero exit mapped to HTTP status |
| RT-15.5-interpreter-fail | `executor.Stage` | 500 for unresolved interpreter |

## Implementation Order

### Phase 1: Foundation (Week 1)
1. **Project skeleton**: `go.mod`, `main.go`, basic HTTP server
2. **Filesystem module**: Root resolution, exact path lookup, root-escape detection
3. **Basic file serving**: GET for literal files, MIME inference by extension
4. **Adapter manifest**: `harness/adapters/go.toml` for conformance testing

**Milestones**: Can serve static files from root directory; passes `plain-files` vectors

### Phase 2: Command Path & Metadata (Week 2)
1. **Command path loading**: `env/path` parsing
2. **Metadata loader**: `env/meta/*` file reading
3. **Metadata parser**: Line-oriented format, field validation
4. **Basic command execution**: Single command, no pipeline

**Milestones**: Commands resolve from path; metadata loads; basic command execution works

### Phase 3: Pipeline Parsing (Week 3)
1. **Segment parsing**: Raw target split, percent-decoding, query string extraction
2. **Precedence ladder**: Exact file → command → synthesized → 404
3. **Pipeline construction**: Multi-stage pipeline with argv consumption
4. **Arity handling**: Fixed arity, arity star, query argv

**Milestones**: Complex pipelines parse correctly; passes `pipelines` and `commands-*` vectors

### Phase 4: Execution Engine (Week 4)
1. **Interpreter rules**: `exec` file parsing, glob matching
2. **Stage execution**: Subprocess management, stdin/stdout plumbing
3. **Pipeline plumbing**: Multi-stage data flow, stderr handling
4. **Exit code mapping**: Exit map evaluation, HTTP status derivation

**Milestones**: Full pipeline execution; passes `exec-rules`, `exit-codes`, `stderr` vectors

### Phase 5: HTTP Methods & Mutation (Week 5)
1. **PUT support**: Literal file creation/replacement, parent directory creation
2. **DELETE support**: File deletion
3. **POST support**: Command-governed POST handling
4. **HEAD support**: Derived from GET
5. **Method validation**: Metadata methods field enforcement

**Milestones**: Full CRUD support; passes `mutation`, `methods` vectors

### Phase 6: Advanced Features (Week 6)
1. **Directory handling**: Index files, directory listing
2. **Symlink support**: Symlink resolution, escape detection
3. **Error responses**: Content negotiation (JSON vs text)
4. **Case sensitivity**: Case-sensitive lookup option
5. **CORS handling**: OPTIONS responses

**Milestones**: All advanced features; passes `directories`, `symlinks`, `security` vectors

### Phase 7: Conformance & Polish (Week 7)
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

Use the harness vectors as the primary integration test suite. The Go adapter:

```toml
# harness/adapters/go.toml
name        = "go"
start       = ["go", "run", "./impls/go/cmd/wash-server", "--root", "{root}", "--port", "{port}"]
stop        = "SIGTERM"
port_mode   = "assigned"
ready       = { type = "tcp" }
ready_timeout_sec = 10
cwd         = "."
env         = {}
capabilities = "impls/go/wash.capabilities.json"
```

## Noted External Libraries

While the implementation is stdlib-only, these libraries would provide significant benefit if added:

| Library | Purpose | Benefit |
|---------|---------|---------|
| `github.com/spf13/cobra` | CLI framework | Flag parsing, subcommands, help generation |
| `github.com/go-chi/chi` | HTTP routing | Clean routing, middleware pattern |
| `github.com/stretchr/testify` | Testing | Assertions, test suites |
| `github.com/gobwas/glob` | Glob matching | Faster, more correct glob matching for exec rules |

## Capability Declaration

```json
{
  "spec_version": "1",
  "origin_form": "http://127.0.0.1",
  "directory_listing": true,
  "default_index_files": ["index.html"],
  "synthesized_resources": { "enabled": false, "fixtures": [] },
  "mime": {
    "inference": "by-extension",
    "map": { ".txt": "text/plain", ".json": "application/json", ".html": "text/html" },
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

1. **Conformance**: Pass all MUST and SHOULD tier vectors
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
