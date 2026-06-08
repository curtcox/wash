# Follow-up Spec Audit and Decision Log

Audit date: 2026-06-08
Implementation status: the author-decision proposals at the end of this document have been applied
to `runtime.md` and `pipeline_parsing.md`.

Files reviewed:

- `specs/runtime.md`
- `specs/pipeline_parsing.md`
- `specs/audit.md`

This audit treats `audit.md` as historical reconciliation material. The findings below record the
follow-up ambiguities found before the author decisions were applied; the active normative rules now
live in `runtime.md` and `pipeline_parsing.md`.

## Summary

The major execution-model conflicts from the earlier audit have mostly been resolved in
`runtime.md` and `pipeline_parsing.md`: implied `cat`, metadata-free arity 0, short metadata field
names, and `/&cmd` stderr syntax are now mostly aligned.

The remaining risk was implementer-facing precision. The author decisions at the end of this file
were applied to close the highest-impact gaps around per-segment query parsing, metadata errors,
method defaults, request bodies, and pipeline exit status.

## Findings Before Implementation

### 1. Malformed metadata is both 400 and 500

Severity: high

`pipeline_parsing.md` section 2 step 9 says that if command parsing starts and the URL violates
"arity, query, boundary, or metadata rules," the runtime returns 400. But sections 5.5 and 10.4 say
malformed recognized metadata is a server-side configuration error and returns 500.

These are incompatible for malformed metadata such as `arity 1..3`.

Proposed resolution: keep malformed recognized metadata as 500. Narrow section 2 step 9 to client
parse errors only, for example: arity mismatch, query misuse, and pipeline boundary violations.
Add a separate step: if resolved command metadata is malformed, return 500.

### 2. Query argv/path argv mixing is not well-defined

Severity: high

The addendum says query argv overrides metadata path arity, but also says mixing query argv and path
argv for the same command is invalid. The canonical invalid example is:

```text
/grep/-i?arg=needle/file.txt
```

This conflicts with the query attachment rule. The `?arg=needle` appears on `-i`, not on the
`grep` command segment. If query strings only attach to command segments, this is not query argv for
`grep`; it is either a query on an argument segment or an invalid segment-level query.

There is also a deeper issue: if query argv overrides path arity, then path argv no longer exists
for that command, so "mixing" cannot be detected by simply looking at following path segments. For
example, `/grep?arg=needle/file.txt` must remain valid and use `file.txt` as the input suffix, even
though `file.txt` would have been a path argument if metadata arity had applied.

Proposed resolution: replace the mixing rule with two clearer rules:

1. Core `arg` is valid only on a recognized command segment.
2. When core `arg` is present, metadata path arity for that command is treated as 0; following
   segments are parsed as pipeline/input suffix, not as argv.

If a stricter rule is desired, it needs a precise definition of which following segments count as
"path argv" after query argv has disabled metadata arity.

### 3. Per-segment query grammar needs delimiter rules

Severity: high

The specs intentionally parse the raw request-target and allow URLs such as:

```text
/grep?arg=needle/jq?arg=.items%5B%5D/haystack.json
```

That design works, but the grammar does not say where a command's query ends. In ordinary URI
syntax, `/` and `?` are legal inside the query component. Under this runtime-specific decomposition,
the next raw `/` appears to end the command query and resume segment parsing, but that is not stated.

Without a delimiter rule, these have multiple plausible parses:

```text
/cmd?arg=a/b/file.txt
/cmd?arg=a?b/file.txt
/cmd?arg=a&b=c/file.txt
```

Proposed resolution: define a runtime request-target grammar:

- A command query starts at the first raw `?` in a segment.
- It ends at the next raw `/` or the end of the request-target.
- Literal `/`, `?`, `&`, and `=` inside query values must be percent-encoded.
- Query parsing happens before percent-decoding values.

This keeps per-command query strings implementable without relying on stock URL parser behavior.

### 4. Exact filesystem matching with query strings is underspecified

Severity: medium/high

The precedence ladder says an exact full-path filesystem resource wins before command parsing.
The request handling section says the runtime parses the raw request-target itself into
per-segment paths and query strings.

The specs do not define what "exact full-path" means when a request-target contains query syntax:

```text
/file.txt?download=1
/foo?x=1/bar.txt
/foo%3Fx/bar.txt
```

For ordinary HTTP, `/file.txt?download=1` should usually address `/file.txt` with a query. For this
runtime, `/foo?x=1/bar.txt` could be command syntax, not a filesystem path. A literal filename
containing `?` should presumably require `%3F`, but the exact matching rule does not say so.

Proposed resolution: define exact filesystem matching over the raw path expression after stripping
only a final ordinary resource query, if ordinary resource queries are supported. Per-segment query
syntax should prevent exact filesystem matching unless `?` is percent-encoded as `%3F`.

This likely needs an author decision because it affects raw file access and command/query syntax.

### 5. Percent-decoding and path normalization need safety rules

Severity: medium/high

`pipeline_parsing.md` says to decode URL path segments according to normal URL path decoding rules,
but it does not specify whether splitting happens before decoding, nor how to handle encoded
slashes and dot segments:

```text
/raw/a%2Fb.txt
/raw/..%2Fsecret.txt
/raw/%2e%2e/secret.txt
```

If `%2F` is decoded before segment splitting, it changes pipeline structure. If `..` is normalized
too late or inconsistently, literal file serving may escape the root. The runtime says command PATH
entries may point outside root, but ordinary literal file paths should map under root.

Proposed resolution:

- Split the raw request-target on raw `/` before percent-decoding.
- Reject decoded `/` and NUL in ordinary path segments, or specify that `%2F` remains a literal
  character rather than a separator.
- Normalize `.` and `..` for filesystem lookup and reject any literal file path escaping root.
- State whether symlinks under root may point outside root.

### 6. `parse-mode raw` is specified in runtime but absent from the addendum algorithm

Severity: medium

`runtime.md` section 10.7 defines `parse-mode raw`: the command receives the remaining still-encoded
URL suffix and the runtime stops parsing. The addendum lists `parse-mode` as a metadata field but
does not include raw-mode behavior in its normative parse algorithm.

A strict implementation of only `pipeline_parsing.md` section 2 would continue scanning stages
after `/explain/...`, contradicting `runtime.md`.

Proposed resolution: add a normative parse-algorithm step after command metadata is loaded:
if `parse-mode raw`, pass the remaining raw suffix to that command and terminate pipeline parsing.
Also state whether raw mode is rejected outside the leftmost command position or merely "not useful."

### 7. Method defaults and `mutates` semantics are not defined

Severity: medium

The specs list `methods` and `mutates` as metadata fields. They also require GET not to mutate and
say a method not permitted by command metadata returns 405. But they do not define:

- the default allowed methods when `methods` is absent,
- the grammar for `methods`,
- the grammar and meaning of `mutates`,
- what happens if a command declares both `methods GET` and `mutates true`,
- whether a multi-stage pipeline checks mutability per stage.

This matters because metadata-free commands are common in the spec. Does `POST /grep/needle/sort`
work without `methods` metadata, or is it 405?

Proposed resolution: choose explicit defaults. A conservative option:

- Ordinary files: GET, PUT, DELETE as defined by resource support.
- Metadata-free commands: GET only.
- Commands may opt into POST, PUT, DELETE, etc. with `methods`.
- `mutates true` plus GET is invalid metadata, or GET requests to that command return 405.
- Every stage in a pipeline must allow the request method; every stage must be non-mutating for GET.

### 8. PUT and DELETE are goals, but lifecycle wording makes them optional

Severity: medium

`runtime.md` goal 12 says the system should support at least GET, PUT, POST, and DELETE. The
resource lifecycle sections say PUT "may create or replace" and DELETE "may delete" where
supported.

This leaves unclear whether PUT/DELETE support for ordinary files is required for a conforming v1
runtime or merely encouraged.

Proposed resolution: either make ordinary-file PUT and DELETE mandatory in v1, or soften the goal
to say these methods are part of the intended method model but individual implementations may
disable them by policy.

### 9. Request body input is in runtime but not in the pipeline addendum

Severity: medium

`runtime.md` section 10.6 defines body-as-stdin and says a file suffix wins over a request body.
`pipeline_parsing.md` does not mention request bodies in the normative parse algorithm or tests.

This makes body input feel non-normative even though it materially changes pipeline input.

Proposed resolution: add request-body cases to the addendum:

- no input suffix + body: body feeds the rightmost stage's stdin,
- input suffix + body: suffix wins unless command metadata captures the body,
- no suffix and no body: define whether stdin is empty/closed or unavailable.

### 10. No-input command execution is undefined

Severity: medium

The specs define metadata-free commands as `arity 0 input stdin`, but do not say what happens when
there is no input suffix and no request body:

```text
/wc
/date
/foo/bar
```

Should the runtime execute the rightmost command with empty stdin, hang waiting for input, return
400, or use command metadata to decide?

Proposed resolution: default to closed empty stdin when no suffix/body exists. Commands that require
an input resource can declare that through metadata once input-mode semantics are defined.

### 11. Pipeline exit-status aggregation is undefined

Severity: medium

Both specs define default command exit mapping (`0 -> 200`, nonzero -> 400), but not how to combine
exit statuses across a multi-stage pipeline.

Questions include:

- Does any failed stage make the HTTP response fail, like `pipefail`?
- Does only the leftmost/downstream stage determine HTTP status, like a shell without `pipefail`?
- If multiple stages fail with different metadata mappings, which status code wins?
- Can a stage mapped to 404 override a later stage mapped to 400?

Proposed resolution: use explicit pipefail-like behavior for HTTP status: every stage's exit status
is mapped through its metadata; if any stage maps to a non-2xx HTTP status, the response is an error.
Define tie-breaking, for example downstream stage wins, or earliest failed stage in execution order
wins.

### 12. `arity *`, input modes, and output modes are only partly specified

Severity: medium

The addendum defines `arity *` as consuming the rest of the URL as argv, leaving no input suffix and
no downstream pipeline "unless another explicit rule overrides this behavior." The overriding rules
are not defined.

Likewise, `input stdin`, `input file`, `input none`, `output stdout`, and `output file` are named,
but their complete semantics are implementation-defined.

Proposed resolution: keep v1 smaller:

- Normatively define only `input stdin` and `output stdout`.
- Treat other modes as reserved unless a later section defines them.
- Remove "unless another explicit rule overrides" from `arity *`, or name the override mechanism.

### 13. Directory input suffix conflicts with directory HTTP behavior

Severity: medium

`runtime.md` section 6.5 says a directory request serves a default file or directory listing.
`pipeline_parsing.md` section 9.4 says a directory may appear as an implied-cat suffix and may fail
naturally like `cat docs`.

For `/wc/docs`, should the input to `wc` be:

- the bytes of `docs/index.html`,
- the generated directory listing,
- an OS-level attempt to read the directory path, likely failing,
- a command-specific file-path argument?

The addendum's example implies the third option, but the runtime's "rightmost input resource" wording
could imply the first or second.

Proposed resolution: state that implied-cat suffix evaluation uses filesystem file bytes only. A
directory suffix is passed to the implied cat operation as a filesystem path and may fail naturally;
HTTP directory listing/default-file behavior applies only to direct directory resource requests.

### 14. Directory traversal vs. synthesized resources has a gap

Severity: low/medium

The addendum says command lookup does not happen after entering a real directory:

```text
/docs/grep/needle/file.txt
```

If `/docs` exists and the full path does not, this returns 404 rather than treating `grep` as a
command. Separately, synthesized resources can resolve when no exact filesystem resource exists and
command parsing does not win.

It is unclear whether a synthesized nested resource such as `/docs/index` may resolve when `/docs`
is a real directory but `/docs/index` is not a real file.

Proposed resolution: define whether synthesized resources are global only, directory-local, or
implementation-defined after partial directory traversal. If implementation-defined, say so in
section 9.2's 404 example.

### 15. The existing audit document is now partly stale

Severity: low/medium

`specs/audit.md` contains several items whose proposed resolutions appear to have been applied to
the current specs, while the old text still presents them as proposed or open. Examples include
items B, F, G, H, I, J, K, L, M, N, O, and P. Its final section says the Q-table items have been
ratified and applied, but earlier sections still read as pending.

This is not a problem if `audit.md` is a historical note. It is confusing if an implementer treats
all files in `specs` as active normative guidance.

Proposed resolution: add a header to `audit.md` marking it as historical and pointing to the current
specs plus this follow-up audit, or rewrite it into a closed decision log with each item marked
`resolved`, `superseded`, or `still open`.

### 16. The MVP section said "400 for ambiguous parses"

Severity: low

`runtime.md` section 10.4 and `pipeline_parsing.md` frame parsing as deterministic, with 400 for
invalid parses. Before implementation, `runtime.md` section 18 still listed "400 for ambiguous
parses."

Implemented resolution: changed the MVP bullet to "400 for invalid command parses."

## Implemented Author Decisions

The following proposed answers were accepted and applied to `runtime.md` and
`pipeline_parsing.md`.

1. Should malformed recognized metadata always be 500, with 400 reserved for client parse errors?
   Implemented answer: yes.

2. Should core `arg` on a command segment simply disable path arity for that command, making the
   current "mixing query argv and path argv" rule unnecessary?
   Implemented answer: yes; reject core `arg` on non-command segments.

3. What exact grammar should delimit per-command query strings inside the raw request-target?
   Implemented answer: a query ends at the next raw `/`; literal `/`, `?`, `&`, and `=` in values must
   be percent-encoded.

4. How should exact filesystem resource matching behave when `?` appears in the request-target?
   Implemented answer: final ordinary resource query may be stripped for direct resources; per-segment
   query syntax should not match literal filenames unless `?` is encoded as `%3F`.

5. What are the default `methods` and `mutates` semantics for metadata-free commands?
   Implemented answer: metadata-free commands permit GET only; mutating commands must opt into
   mutating methods, and GET must be rejected for mutating commands.

6. Is PUT/DELETE for ordinary files required in v1, or can implementations disable it and still
   conform?
   Implemented answer: required by the core contract unless disabled by an explicit implementation
   policy.

7. What is the HTTP status aggregation rule for multi-stage pipelines?
   Implemented answer: pipefail-like; any stage mapped to a non-2xx status fails the response, with a
   documented tie-breaker.

8. What happens when a command has stdin input mode but there is no suffix and no request body?
   Implemented answer: stdin is closed and empty.

9. Are symlinks under the root allowed to expose files outside the root for direct file serving?
   Implemented answer: implementation-defined, but the default should be to reject escapes for literal
   file serving.

10. Should `audit.md` remain historical, or should it be rewritten into a live decision log?
    Implemented answer: mark it historical and keep future live issues in a separate audit or issue
    tracker.
