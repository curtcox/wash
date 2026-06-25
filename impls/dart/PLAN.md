# Dart Port Implementation Plan for wash

## Overview

This document outlines the implementation plan for a Dart port of the wash Web Shell specification, targeting full conformance with all MUST and SHOULD clauses defined in `specs/runtime.md` and `specs/pipeline_parsing.md`.

## Implementation Status

**All phases complete.** Full conformance achieved.

| Conformance tier | Result |
|---|---|
| MUST (112 clauses) | 112/112 ✓ |
| SHOULD (1 clause) | 1/1 ✓ |
| optional | 2/11 (9 skipped — capability-gated) |

### Files delivered

- `pubspec.yaml` — SDK ≥3.0, deps: `args`, `glob`, `test`
- `bin/wash_server.dart` — CLI entry point (`--root`, `--port`)
- `lib/filesystem/filesystem.dart` — path resolution, MIME, PUT/DELETE, root-escape, symlink policy
- `lib/metadata/metadata.dart` — `env/meta/*` loader and field validator
- `lib/parser/parser.dart` — URL pipeline parser (segments, precedence, arity, query argv, parse-mode raw)
- `lib/executor/executor.dart` — interpreter resolution, stage runner, pipeline plumbing, exit mapping
- `lib/server/server.dart` — HTTP server with `_PatchedServerSocket` raw-target injection
- `test/parser/segment_test.dart` — 20 unit tests
- `wash.capabilities.json` — capability declaration
- `harness/adapters/dart.toml` — adapter manifest
- `Makefile` targets: `build-dart`, `lint-dart`, `test-dart`, `conformance-dart`, `test-dart-all`
- `.github/workflows/conformance.yml` — `conformance-dart` job (ubuntu + macos matrix)

### Implementation notes

- **Raw target preservation**: Dart's `HttpServer` normalises `/../` and `/%2e%2e/` before the handler runs. Solved via `_PatchedServerSocket` / `_PatchedSocket` which intercept the raw socket, sniff the request line, and inject the verbatim target as an `x-wash-raw-target` header before the HTTP parser sees the bytes.
- **Dependency minimalism**: only `args` and `glob` beyond `dart:io`/`dart:convert`. `shelf` not used.

## Target Specifications

- **Dart SDK Version**: Latest stable (3.x)
- **Spec Conformance**: Full (all MUST and SHOULD clauses)
- **Platforms**: macOS and Linux (primary), others as feasible
- **Dependencies**: Minimal; `dart:io` and `dart:convert` for core logic, `shelf` and `args` as optional quality-of-life additions

## Architecture

### Package Structure

Package name: `wash_server` under `impls/dart/`.

```
impls/dart/
├── pubspec.yaml              # Package declaration, dependencies, SDK constraint
├── wash.capabilities.json    # Capability declaration (mirrors Go/reference)
├── bin/
│   └── wash_server.dart      # Sole entry point: CLI flags, server bootstrap
├── lib/
│   ├── server/               # HTTP server, routing, handlers
│   │   ├── server.dart       # HttpServer setup, listen loop
│   │   ├── handler.dart      # Request dispatch
│   │   └── response.dart     # Response building, error formatting
│   ├── parser/               # URL pipeline parsing
│   │   ├── parser.dart       # Main left-to-right parsing logic
│   │   ├── segment.dart      # Segment parsing (stderr merge, query strings)
│   │   ├── pipeline.dart     # Pipeline construction
│   │   └── precedence.dart   # Resolution precedence ladder
│   ├── filesystem/           # File/directory operations
│   │   ├── root.dart         # Root directory, path resolution
│   │   ├── file.dart         # File reading, MIME inference
│   │   ├── dir.dart          # Directory listing
│   │   ├── mutation.dart     # PUT, DELETE operations
│   │   └── symlink.dart      # Symlink handling
│   ├── metadata/             # Command metadata
│   │   ├── loader.dart       # env/meta/* loading
│   │   ├── parser.dart       # Line-oriented metadata parsing
│   │   ├── validator.dart    # Metadata validation
│   │   └── defaults.dart     # Default metadata values
│   ├── executor/             # Command execution
│   │   ├── executor.dart     # Pipeline execution
│   │   ├── interpreter.dart  # Interpreter rule resolution
│   │   ├── stage.dart        # Single stage execution
│   │   └── pipe.dart         # Pipeline plumbing
│   └── config/               # Configuration
│       ├── path.dart         # Command path loading
│       └── exec.dart         # exec rule loading
└── test/                     # Unit tests (dart test)
```

### Key Abstractions

```dart
// lib/parser/parser.dart
abstract class Parser {
  ParseResult parse(String rawTarget, String root, String method);
}

abstract class ParseResult {
  bool get isFilesystem;
  bool get isPipeline;
  bool get isNotFound;
}

// lib/executor/executor.dart
abstract class Executor {
  Future<ExecutionResult> execute(Pipeline pipeline, Stream<List<int>>? stdin);
}

class Pipeline {
  final List<Stage> stages;
  final String? inputSuffix;
  final Stream<List<int>>? requestBody;
}

// lib/filesystem/root.dart
abstract class WashFS {
  Future<Resource?> resolveExact(String path);
  Future<List<int>> readFile(String path);
  Future<DirListing> listDir(String path);
  Future<void> putFile(String path, List<int> data, {bool createParents = false});
  Future<void> deleteFile(String path);
  void checkEscape(String path); // throws on escape
}
```

## Build/Run Model

Two modes are supported; the adapter uses the AOT binary for speed:

- **AOT binary** (used in CI and adapter): `dart pub get && dart compile exe bin/wash_server.dart -o bin/wash-server`
  - No SDK required at runtime; comparable startup to the Go binary.
  - The adapter's `start` command points at this pre-built binary.
  - **`dart pub get` is mandatory before any compile or test.** Unlike Go (which
    auto-fetches modules on `go build`), Dart cannot compile, run, or test without
    a resolved `.dart_tool/package_config.json`. This applies even to a "stdlib-only"
    build because `dart test` needs the `test` package fetched.
- **JIT dev mode** (local iteration): `dart run bin/wash_server.dart --root <root> --port <port>`
  - No compile step (but still requires `dart pub get` once); useful for quick local tests.

The adapter always uses the pre-built AOT binary for the same reasons as the Go impl: the harness launches ~22 server processes per full conformance run, and a cold JIT compile on every start would exceed `ready_timeout_sec`.

## Spec Clause Mapping

This table mirrors the Go plan exactly. Source of truth is `harness/conformance/spec.py`.
66 clauses total — 57 MUST, 4 SHOULD, 5 optional.

### runtime.md

| Clause | Tier | Component | Notes |
|--------|------|-----------|-------|
| RT-4.2-root-valid | MUST | `filesystem.Root`, `server.Server` | Empty root directory is valid; server still starts |
| RT-6.1-literal-file | MUST | `filesystem.resolveExact` | Plain URL path maps literally to root file before any command parse |
| RT-6.2-precedence | MUST | `parser.parse` | Ladder: exact file > command > synthesized > 404 |
| RT-6.3-direct-cmd-file | MUST | `filesystem.readFile` | Concrete path to a command file serves its bytes |
| RT-6.4-missing-path | MUST | `parser.parse`, `server.handler` | No parse + no resource → 404 |
| RT-6.5-dir-index | optional | `filesystem.listDir` | Declared index file wins over listing (gated by `default_index_files`) |
| RT-7.1-command-path | MUST | `config.loadCommandPath` | `env/path` line-oriented search path |
| RT-7.2-exec-rules | MUST | `config.loadExecRules`, `executor.interpreter` | First-match-wins; malformed rule → 500 |
| RT-9.1-get-no-mutate | MUST | `server.handler` | GET must not mutate local state |
| RT-9.2-put-literal | MUST | `server.handler`, `filesystem.putFile` | PUT targets literal path, no command parsing |
| RT-9.3-post-plain-405 | MUST | `server.handler` | POST to plain file/dir without governing command → 405 |
| RT-9.4-delete-literal | MUST | `server.handler`, `filesystem.deleteFile` | DELETE targets literal path, no command parsing |
| RT-9.5-head-from-get | MUST | `server.handler` | GET permitted ⇒ HEAD answered with body omitted |
| RT-9.5-methods-405 | MUST | `parser.checkMethods`, `metadata` | Method not in `methods` metadata → 405 |
| RT-9.5-head-explicit | optional | `server.handler` | HEAD when explicit methods list has GET but not HEAD (not asserted) |
| RT-10.4-invalid-parse | MUST | `server.handler` | Client-controlled parse errors → 400 |
| RT-10.5-multi-resource | MUST | `parser.consumeArgv`, `executor` | Command may consume multiple root-relative resources via arity |
| RT-10.6-request-body | MUST | `executor.Pipeline`, `server.handler` | Request body feeds rightmost stage stdin; **input suffix wins over body** |
| RT-10.7-url-expr | MUST | `parser.rawCommandParse` | parse-raw consumes remaining URL expression and stops parsing |
| RT-12.2-request-handling | MUST | `server.handler`, `parser` | Parse the **raw** request-target: read `HttpRequest.requestedUri` raw string, no normalization before parse |
| RT-12.2-root-escape | MUST | `filesystem.checkEscape` | Literal serving rejects paths escaping configured root |
| RT-12.3-cwd-root | MUST | `executor.stage` | Command cwd defaults to root for root-relative argv |
| RT-13.1-cors-default | SHOULD | `server.middleware` | No `Access-Control-Allow-Origin` by default |
| RT-13.2-mutating-methods | MUST | `server.handler`, `metadata.validate` | Mutation requires explicit method/metadata opt-in |
| RT-15.1-not-found | MUST | `server.handler` | No resource and no parse → 404 |
| RT-15.2-invalid-parse | MUST | `server.handler` | Invalid parse → 400 with diagnostics |
| RT-15.3-exit-status | MUST | `executor.stage`, `metadata.exitMap` | Nonzero exit mapped to error status with diagnostics |
| RT-15.5-interpreter-fail | MUST | `executor.interpreter` | Unresolved interpreter → 500 |
| RT-15.6-cmd-http-errors | MUST | `executor.result`, `server.handler` | Command-generated HTTP errors surfaced per contract |
| RT-R7-case | optional | `filesystem.resolveExact` | Case sensitivity consistent with `case_sensitive_lookup` |

### pipeline_parsing.md

| Clause | Tier | Component | Notes |
|--------|------|-----------|-------|
| PP-2-parse-algo | MUST | `parser.parse` | Normative left-to-right algorithm + precedence ladder |
| PP-4-arity0-default | MUST | `metadata.defaults`, `parser` | Metadata-free ⇒ arity 0, closed-empty stdin when no suffix/body |
| PP-4-implied-cat | MUST | `executor.pipeline` | Rightmost suffix fed via implied `cat` primitive |
| PP-5.1-arity-n | MUST | `metadata.parse`, `parser.consumeArgv` | Arity N consumes N segments as argv |
| PP-5.2-arity-star | MUST | `metadata.parse`, `parser.consumeArgv` | Arity `*` consumes rest of URL; no input suffix |
| PP-5.3-input-stdout | MUST | `executor.stage` | v1 stdin/stdout modes; reserved modes → 500 |
| PP-5.4-exit-map | MUST | `executor`, `metadata.exitMap` | exit→status with pipefail aggregation (first in URL order wins) |
| PP-5.5-malformed-500 | MUST | `metadata.validate` | Malformed recognized field → 500 |
| PP-5.7-parse-raw | MUST | `parser.rawCommandParse` | parse-raw takes encoded suffix and stops parsing |
| PP-5.7-method-all-stages | MUST | `parser.checkMethods` | Every stage must permit the request method |
| PP-5.7-mutates-get-invalid | MUST | `metadata.validate` | GET permitted + mutates=true is invalid → 500 |
| PP-5.8-mime-final | MUST | `executor.result` | `mime` sets final-stage Content-Type; ignored mid-pipeline |
| PP-5.9-stderr-field | MUST | `executor.stage` | stderr discard/merge semantics for response body |
| PP-6-query-delim | MUST | `parser.segment` | Per-command query ends at next raw `/` |
| PP-6.1-core-arg | MUST | `parser.segment` | `arg` is the only core query parameter |
| PP-6.2-query-disables-arity | MUST | `parser.pipeline` | Query argv disables metadata path arity for that command |
| PP-6.3-arg-noncmd-400 | MUST | `parser.segment` | Core `arg` on non-command segment → 400 |
| PP-7-mid-noncmd-400 | MUST | `parser.parse` | Non-command middle segment with metadata-free commands → 400 |
| PP-8-stderr-prefix | MUST | `parser.segment` | `/&` prefix merges exactly one pipeline boundary |
| PP-8.1-amp-name | MUST | `parser.segment` | Leading `&` stripped pre-decode; `%26` is a name character |
| PP-9.1-trailing-q | MUST | `parser.segment` | Trailing `?` in final segment is resource query before command reinterpretation |
| PP-9.1-slash-collapse | MUST | `parser.segment` | Leading/trailing/repeated `/` collapse; trailing slash insignificant |
| PP-9.1-invalid-segment | MUST | `parser.segment`, `filesystem` | Decoded `/` and NUL invalid in filesystem-lookup segments |
| PP-9.2-no-cmd-in-dir | MUST | `parser.parse` | No command lookup after directory traversal |
| PP-9.3-args-before-suffix | MUST | `parser.consumeArgv` | Path arity arguments consumed before input suffix |
| PP-9.4-dir-suffix | MUST | `parser.parse`, `executor.pipeline` | Directory suffix evaluated via implied `cat`, not HTTP directory behavior |
| PP-9.5-synth | optional | `server.handler` | Synthesized resource behavior (disabled in capabilities) |
| PP-9.5-parse-terminal | MUST | `parser.parse` | Started-command parse failure is terminal; no synthesized fallback |
| PP-10.1-400-diagnostics | SHOULD | `server.response` | 400 bodies include parse-failure diagnostics |
| PP-10.2-404 | MUST | `server.handler` | 404 when no resource, no synth, no command parse can start |
| PP-10.3-exit-diagnostics | SHOULD | `server.response`, `executor` | Nonzero-exit bodies include command/exit/pipeline diagnostics |
| PP-10.4-500 | MUST | `server.handler`, `metadata` | Malformed metadata + server-side failures → 500 |
| PP-10.5-error-format | SHOULD | `server.response` | Error bodies content-negotiated via `Accept` |
| PP-11-headers | optional | `server.response` | `X-WebShell-*` execution metadata headers when declared (`execution_metadata_headers`) |
| PP-13.1-mf-path-args | MUST | `parser`, `metadata.defaults` | Metadata-free path arguments invalid → 400 |
| PP-13.2-mf-multi-path-args | MUST | `parser` | Metadata-free multi-command path args invalid → 400 |

## Implementation Order

### Phase 1: Foundation
1. **Project skeleton**: `pubspec.yaml`, `bin/wash_server.dart`, basic `dart:io` HTTP server
2. **Filesystem module**: Root resolution, exact path lookup, root-escape detection
3. **Basic file serving**: GET for literal files, MIME inference by extension
4. **Adapter manifest + build target**: `harness/adapters/dart.toml` pointing at the
   pre-built `impls/dart/bin/wash-server`, plus `build-dart` and `conformance-dart`
   Makefile targets. Verify a compile → conformance loop works end to end before
   layering behavior.

**Milestones**: Serves static files from root; passes `plain-files` vectors.

> **Land one real test file in this phase.** Unlike Go (`go test ./...` exits 0
> with no test files, and the Go impl ships none), `dart test` errors with "No
> tests found" and exits non-zero when the `test/` tree is empty. `test-dart` must
> not be wired into CI (`test-dart-all`) until at least one test exists, or the
> job goes red immediately.

> **Sequencing for `validate-capabilities`:** add the
> `wash-conformance validate-capabilities harness/adapters/dart.toml` line to
> `make validate` and the CI `validate` job *only after* `impls/dart/dart.toml`
> and `impls/dart/wash.capabilities.json` exist. Added earlier, it fails the gate
> before any Dart code is written.

### Phase 2: Command Path & Metadata
1. **Command path loading**: `env/path` parsing
2. **Metadata loader**: `env/meta/*` file reading
3. **Metadata parser**: Line-oriented format, field validation
4. **Basic command execution**: Single command, no pipeline

### Phase 3: Pipeline Parsing
1. **Segment parsing**: Raw target split, percent-decoding, query string extraction
2. **Precedence ladder**: Exact file → command → synthesized → 404
3. **Pipeline construction**: Multi-stage pipeline with argv consumption
4. **Arity handling**: Fixed arity, arity star, query argv

### Phase 4: Execution Engine
1. **Interpreter rules**: `exec` file parsing, glob matching
2. **Stage execution**: `Process.start` subprocess management, stdin/stdout plumbing
3. **Pipeline plumbing**: Multi-stage data flow, stderr handling
4. **Exit code mapping**: Exit map evaluation, HTTP status derivation

### Phase 5: HTTP Methods & Mutation
1. **PUT support**: Literal file creation/replacement, parent directory creation
2. **DELETE support**: File deletion
3. **POST support**: Command-governed POST handling
4. **HEAD support**: Derived from GET
5. **Method validation**: Metadata methods field enforcement

### Phase 6: Advanced Features
1. **Directory handling**: Index files, directory listing
2. **Symlink support**: Symlink resolution, reject-escaping policy
3. **Error responses**: Content negotiation (JSON vs text)
4. **Case sensitivity**: Case-sensitive lookup
5. **CORS handling**: OPTIONS responses

### Phase 7: Conformance & Polish
1. **Full conformance run**: All MUST + SHOULD vectors passing
2. **Root escape rejection**: `..` segments rejected pre-decode
3. **parse-mode raw position check**: Only valid in leftmost stage
4. **Typed filesystem errors**: 404/400/500 correctly distinguished

### Phase 8: CI & Housekeeping
1. **`dart format`** / **`dart analyze`**: Clean output, no warnings
2. **CI workflow**: `validate` job validates `dart.toml` capabilities; `conformance-dart` job added (`needs: validate`, runs `make test-dart-all`) with a pub-cache step
3. **`make validate`** includes `wash-conformance validate-capabilities harness/adapters/dart.toml`
4. **`.gitignore`**: add `impls/dart/bin/wash-server`, `impls/dart/.dart_tool/`, `impls/dart/.packages` (do *not* ignore `impls/dart/bin/`, which holds committed source)
5. **`.PHONY`**: add `build-dart lint-dart test-dart conformance-dart test-dart-all`

## Testing Strategy

### Conformance-Driven Development

```bash
# Run specific root against Dart implementation
wash-conformance run --adapter harness/adapters/dart.toml --root plain-files

# Run all MUST tier vectors
wash-conformance run --adapter harness/adapters/dart.toml --tier MUST

# Run full conformance suite
wash-conformance run --adapter harness/adapters/dart.toml
```

### Unit Testing

Internal library code has `dart test` unit tests for:
- Complex parsing edge cases
- Path escaping / root-escape logic
- Metadata field validation

```dart
// test/parser/segment_test.dart
void main() {
  group('parseSegment', () {
    test('strips leading ampersand pre-decode', () { ... });
    test('query ends at next raw slash', () { ... });
  });
}
```

### Integration Testing

Use the harness vectors as the primary integration test suite.

**Build the binary first — the adapter does not compile.** The adapter only
launches a pre-built binary; a `dart run` start command would recompile on every
process launch (~22 roots × multiple runs) and likely exceed `ready_timeout_sec`.
The AOT binary (`dart compile exe`) starts in milliseconds.

```toml
# harness/adapters/dart.toml
name        = "dart"
start       = ["impls/dart/bin/wash-server", "--root", "{root}", "--port", "{port}"]
stop        = "SIGTERM"
port_mode   = "assigned"
ready       = { type = "tcp" }
ready_timeout_sec = 10
cwd         = "."
env         = {}
capabilities = "impls/dart/wash.capabilities.json"
```

## Makefile Targets

Dart-specific targets mirror the Go pattern. They are kept out of the `test`
target (reference gate) so a missing Dart SDK never breaks the reference CI job.

Add the new targets to the `.PHONY` line alongside the existing `build-go …` set.

```makefile
build-dart:
	cd impls/dart && dart pub get && dart compile exe bin/wash_server.dart -o bin/wash-server

lint-dart:
	dart analyze impls/dart
	dart format --output=none --set-exit-if-changed impls/dart

test-dart: build-dart
	cd impls/dart && dart test

conformance-dart: build-dart
	wash-conformance run --adapter harness/adapters/dart.toml

test-dart-all: lint-dart test-dart conformance-dart
```

`build-dart` runs `dart pub get` first and `cd`s into `impls/dart` so pub
resolves the package config; `dart compile exe` (and `dart test`) fail without it.

`impls/dart/bin/wash-server` is a build artifact — add it to `.gitignore`.
**Do not blanket-ignore `impls/dart/bin/`** the way `.gitignore` does for
`impls/go/bin/`: the Dart entry point `bin/wash_server.dart` is committed source
living in the same directory as the compiled binary. Add these specific entries:

```gitignore
impls/dart/bin/wash-server
impls/dart/.dart_tool/
impls/dart/.packages
```

## CI Workflow

Add a `conformance-dart` job to `.github/workflows/conformance.yml`. The existing
`conformance-go` and `conformance` jobs run **ubuntu-only**; this job intentionally
adds a macOS leg via a matrix (better platform coverage for `dart:io` path/symlink
behavior). That is a deliberate divergence from Go, not strict parity — if cost or
runner time is a concern, drop `macos-latest` to match the others.

`make test-dart-all` runs `build-dart`, which already invokes `dart pub get`, so no
separate pub-get step is needed. The pub cache is restored explicitly to keep the
AOT compile fast (matches the caching row in the Risk Assessment).

```yaml
conformance-dart:
  runs-on: ${{ matrix.os }}
  needs: validate
  strategy:
    matrix:
      os: [ubuntu-latest, macos-latest]
  steps:
    - uses: actions/checkout@v4
    - uses: dart-lang/setup-dart@v1
      with:
        sdk: stable
    - uses: actions/setup-python@v5
      with:
        python-version: "3.12"
    - name: Cache pub + build artifacts
      uses: actions/cache@v4
      with:
        path: |
          ~/.pub-cache
          impls/dart/.dart_tool
        key: pub-${{ matrix.os }}-${{ hashFiles('impls/dart/pubspec.yaml') }}
    - name: Install harness
      run: pip install -e "./harness[dev]"
    - name: Run Dart lint, unit tests, and conformance
      run: make test-dart-all
```

Also add `wash-conformance validate-capabilities harness/adapters/dart.toml` to
the `validate` job's step list alongside the existing reference and go lines —
but only once `harness/adapters/dart.toml` and `impls/dart/wash.capabilities.json`
exist (see Phase 1 sequencing note), or the gate fails before any code lands.

## Dart-Specific Notes

### Raw Request Target

Dart's `dart:io` `HttpRequest` exposes `requestedUri` (a `Uri` object) and
`uri` (a normalized `Uri`). **Always use `requestedUri`** and extract its raw
`path` + query before any `Uri` normalization — the same discipline as reading
`r.RequestURI` in Go's `net/http`. Apply percent-decoding only where the spec
mandates it, not before parse.

### Subprocess Plumbing

`Process.start` returns a `Process` object with `stdin`, `stdout`, and `stderr`
as Dart streams/sinks — a natural fit for the pipeline plumbing. Use
`StreamController` or direct `pipe` calls for multi-stage data flow. Set
`workingDirectory` for `RT-12.3-cwd-root`.

### Glob Matching for exec Rules

`dart:io` has no built-in glob; use the `glob` pub package (e.g. `glob: ^2.1.0`)
or implement the simple two-character wildcard the exec rule format requires
(`*` and `?`). The Go impl chose stdlib-only glob via `path.Match`; either
approach is valid here.

### Isolates

The `dart:io` `HttpServer` runs on a single isolate and handles concurrency via
the event loop. This is sufficient for the conformance harness. No need to spawn
multiple isolates for conformance purposes.

## Noted External Packages

| Package | Purpose | Notes |
|---------|---------|-------|
| `shelf` | HTTP server framework | Cleaner handler composition; optional |
| `shelf_router` | Routing on top of shelf | Only if `shelf` is adopted |
| `args` | CLI flag parsing | Small, well-maintained, standard for Dart CLIs |
| `glob` | Glob pattern matching | For exec rule interpreter resolution |
| `test` | Unit testing | Standard Dart test framework (already in pub ecosystem) |

If staying stdlib-only: `dart:io` `HttpServer` for serving, hand-rolled flag
parsing from `List<String> args`, and a small custom glob matcher. The `args` and
`glob` packages are strongly recommended even in a "minimal deps" build.

## Capability Declaration

Mirror `impls/reference/wash.capabilities.json` exactly (same as Go):

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
  "escape_policy": "reject-escaping",
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
| AOT compile stripping needed `dart:io` APIs | Test AOT binary early (Phase 1); AOT supports all `dart:io` |
| `requestedUri` normalization silently applied | Verify raw path extraction against encoding vectors early |
| Subprocess stream backpressure / deadlock | Test multi-stage pipelines with large inputs; use async `pipe` carefully |
| Glob matching edge cases in exec rules | Unit test against the same cases as the Go impl |
| Platform differences (macOS/Linux) | CI matrix covers both; avoid platform-specific path assumptions |
| Cold AOT compile time in CI | Cache `~/.pub-cache` and `impls/dart/.dart_tool` in CI |

## Success Criteria

1. **Conformance**: Pass all MUST and SHOULD tier vectors (57 MUST + 4 SHOULD clauses). With the capabilities above, dir-index, case, and `X-WebShell-*` header vectors also run and must pass; synthesized-resource vectors are skipped (declared disabled).
2. **Performance**: Comparable or better than Python reference on benchmark roots
3. **Compatibility**: Drop-in replacement via adapter manifest change
4. **Maintainability**: Clear library boundaries, `dart analyze` clean

## Appendix: Reference Implementation Notes

Key insights from Python reference (`impls/reference/wash/`) and Go port:

- **server.py / server.go**: Threading/goroutines → Dart event loop (`dart:io` `HttpServer`)
- **parser.py / parser.go**: Complex left-to-right parse with backtracking → explicit state machine in Dart
- **executor.py / executor.go**: `selectors`/`io.Pipe` → `Process.start` + async stream pipes
- **filesystem.py / filesystem.go**: `pathlib`/`path/filepath` → `dart:io` `File`, `Directory`, `Link`
- **metadata.py / metadata.go**: Line-oriented text parsing → `dart:io` `File.readAsLines`

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

**Last Updated**: 2026-06-09 (Plan drafted; pre-implementation review corrections applied — no implementation yet)
**Plan Version**: 1.1
