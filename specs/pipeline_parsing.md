# Addendum: URL Pipeline Parsing and Metadata-Free Command Arity

> This addendum extends runtime.md.

## 1. Parsing Problem Statement

The runtime maps a local HTTP URL space to a single project/root directory. A URL path may denote:

1. an exact filesystem resource,
2. a synthesized resource,
3. a command pipeline,
4. command path arguments,
5. command query arguments,
6. an input suffix consumed through stdin,
7. or a stderr-composing pipeline boundary.

Command resolution proceeds left-to-right in URL order. Data flow normally proceeds right-to-left, from the rightmost input suffix through each command stage toward the leftmost command.

The primary ambiguity resolved by this addendum is how to parse URL pipelines when command metadata is absent or incomplete.

## 2. Normative Parse Algorithm

Given an HTTP request-target:

1. Split the raw request-target on raw / before percent-decoding. Per-command query strings are delimited by the next raw / or the end of the request-target (§6). A literal /, ?, &, or = inside a query value must be percent-encoded.
2. Check whether the request path resolves to an exact filesystem resource (§9.1).
   - If yes, the exact filesystem resource wins.
   - No command parsing is attempted for that path.
3. If no exact filesystem resource exists, attempt command parsing from the leftmost segment.
4. If the leftmost segment is not a command and no exact filesystem resource exists, return 404 Not Found, unless a synthesized resource resolves.
5. If the leftmost segment is a command, begin a command pipeline parse.
6. For each command stage:
   - Resolve the command name through the command PATH.
   - Load metadata from root/env/meta/<command> if present.
   - If metadata is absent, use metadata-free defaults.
   - If resolved metadata contains a malformed recognized field, return 500 Internal Server Error (§5.5, §10.4).
   - If metadata declares parse-mode raw, pass the remaining raw suffix to that command and stop parsing (§5.7).
   - Determine argv from either query arguments or path arguments.
   - Core query argv is valid only on a recognized command segment.
   - Query argv disables metadata path arity for that command; following segments are parsed as pipeline/input suffix, not as argv.
7. Continue scanning the remaining suffix for known command segments.
   - Known command segments inside a suffix create pipeline stages.
   - Each recognized command divides the URL into another stage.
8. The final rightmost non-command suffix is supplied as input through an implied cat.
   - If there is no input suffix but the request has a body, the body feeds the rightmost stage's stdin.
   - If there is neither input suffix nor request body, stdin is closed and empty by default.
   - If both an input suffix and request body are present, the suffix wins unless command metadata explicitly captures the body.
9. If command parsing starts but the URL violates client-controlled arity, query, or pipeline boundary rules, return 400 Bad Request. A 400 from a started command parse is terminal: the runtime does not fall back to a synthesized resource (§9.5).
10. If no resource exists and no command parse can start, return 404 Not Found.

## 3. Command Resolution Rules

Command resolution is left-to-right.

A command segment is resolved through a PATH-like command search path, such as:

text root/env/path 

Command metadata may exist at:

text root/env/meta/<command> 

Metadata is optional. If absent, the command uses metadata-free defaults.

A command segment shadows an ordinary file only when command parsing has already begun and no exact filesystem path has matched the full URL.

An exact filesystem path has precedence over command parsing.

Example:

text /grep/docs/file.txt 

If /grep/docs/file.txt exists as a filesystem path, it is served as a file and does not parse as a command pipeline, even if grep is on PATH.

## 4. Metadata-Free Default Behavior

A command with no metadata has:

text arity 0 input stdin output stdout methods GET mutates false 

This means a metadata-free command consumes zero path arguments. Remaining suffix segments are not treated as argv for that command.

If the remaining suffix contains known command names, those command names create further pipeline stages.

If the rightmost remaining suffix resolves as a file or directory path, it is supplied to the pipeline through an implied cat. The implied cat is a runtime primitive that reads filesystem bytes for the suffix; it is not resolved through the command PATH, carries no metadata, and imposes no method restriction of its own (the method gate is enforced by the real command stages, §5.7). A user-defined cat command on the PATH does not affect implied-cat behavior.

If no input suffix exists and the HTTP request has no body, stdin is closed and empty. A command that requires an input resource must declare and enforce that requirement through metadata or command behavior.

Example:

text /foo/bar/baz/qux.txt 

If foo is a metadata-free command, bar is not a command, and /bar/baz/qux.txt exists, this parses as:

sh cat bar/baz/qux.txt | foo 

Example:

text /foo/bar/baz/qux.txt 

If both foo and bar are metadata-free commands, and /baz/qux.txt exists, this parses as:

sh cat baz/qux.txt | bar | foo 

The discriminator between a valid implied-cat suffix and invalid path arguments is
filesystem resolution, not segment count. A metadata-free command may be followed
by a multi-segment suffix as long as that whole suffix resolves to an existing file
or directory under the root; it is then the implied-cat input. A multi-segment
suffix that does not resolve is invalid (§13.1, §13.2) and returns 400. A single
trailing segment that does not resolve is instead a missing implied-cat resource
and returns 404 (§10.2).

Metadata-free commands do not infer arity from Unix command names.

Therefore, with all commands metadata-free:

text /wc/-l/grep/needle/jq/.items%5B%5D/haystack.json 

is invalid and returns 400 Bad Request.

It does not parse as:

sh cat haystack.json | jq '.items[]' | grep needle | wc -l 

because wc, grep, and jq each default to zero path arguments.

## 5. Metadata Fields and Defaults

The line-oriented metadata file format is part of the specification.

A basic metadata file may contain fields such as:

text arity 1 input stdin output stdout methods GET POST stderr discard exit 0=200 1=404 *=400 

### 5.1 arity

arity N means exactly N URL path segments immediately following the command are consumed as positional arguments before parsing continues.

Example metadata:

text arity 1 

Example URL:

text /grep/needle/file.txt 

If grep has arity 1, this parses as:

sh cat file.txt | grep needle 

Argument segments are percent-decoded after the raw / split and passed to the command verbatim as
strings. Because an argument is never used for filesystem lookup, it may contain bytes that are illegal
in ordinary filesystem path segments, including a decoded / or NUL. For example /grep/a%2Fb/file.txt
with grep arity 1 passes the single argument a/b.

### 5.2 Variable Arity

Metadata may support variable arity.

At minimum, the following form is supported:

text arity * 

arity * means the command consumes the rest of the URL as argv, leaving no input suffix and no downstream pipeline. Suppressing the URL-derived input suffix does not suppress a request body: if the method is permitted and a request body is present, that body still feeds the command's stdin (§4, §10.6 of runtime.md).

Example:

text /cmd/a/b/c.txt 

If cmd has:

text arity * 

then the command receives:

text ["a", "b", "c.txt"] 

as argv.

In v1, only fixed arity (a non-negative integer N) and arity * are defined. Range forms such as arity 0..* or arity 1..3 are reserved for a future extension and are treated as malformed metadata by a v1 runtime (§5.5, 500).

### 5.3 Input and Output

Metadata defines stdin/stdout behavior separately from arity.

The metadata-free default input mode is:

text input stdin 

The only v1 normative input/output modes are:

text input stdin output stdout 

The names input file, input none, and output file are reserved for future specification. A v1 runtime that does not define an implementation extension for those modes treats them as malformed recognized metadata and returns 500 for requests resolving to that command (§5.5, §10.4).

### 5.4 Exit Status Mapping

Default exit mapping is:

text exit 0 => 200 exit nonzero => 400 

Metadata may override specific exit codes.

Example:

text exit 0=200 1=404 *=400 

The exit field value is a whitespace-separated list of code=status pairs. code is a non-negative integer or the wildcard *; status is an HTTP status code. An explicit numeric code takes precedence over *. A nonzero exit that matches no explicit code and has no * pair falls back to the default mapping (nonzero => 400). A malformed pair is a malformed recognized value and returns 500 (§5.5).

In a multi-stage pipeline, every stage's exit status is mapped through that stage's metadata or defaults. If any stage maps to a non-2xx HTTP status, the overall response is an error. When multiple stages map to non-2xx statuses, the first failing stage in URL order wins. This is intentionally pipefail-like: an upstream stage failure cannot be hidden by a downstream stage that exits successfully.

Because URL order is reversed relative to data-flow (shell) order, the first failing stage in URL order is the most downstream stage in the pipeline, matching shell set -o pipefail. For example, given the URL /wc/grep/jq/haystack.json (data flow cat haystack.json | jq | grep | wc), if both jq and wc exit nonzero, wc — first in URL order — determines the HTTP status and primary diagnostic.

### 5.5 Metadata Grammar

The metadata file is line-oriented:

- One field per line: a field name followed by whitespace-separated values.
- Blank lines are ignored.
- A line whose first non-whitespace character is # is a comment and is ignored. An inline # is not treated as a comment.
- Tokens are separated by ASCII whitespace. Quoting and escaping for values containing whitespace are not defined in v1; values requiring such handling are out of scope.
- If a field appears more than once, the last occurrence wins.
- An unrecognized field name is ignored; an implementation may warn.
- A recognized field with a malformed value makes the metadata invalid; a request resolving to that command returns 500 Internal Server Error, since it is a server-side configuration error rather than a client error (§10.4).

### 5.6 Normative Field List

The defined metadata fields are:

text arity input output methods mime mutates parse-mode stderr exit 

All fields are optional; defaults apply for any absent field (§4).

### 5.7 Methods, Mutation, and Parse Mode

The default allowed method for a command is:

text methods GET 

The methods field is a whitespace-separated list of HTTP methods. Method names are case-sensitive
and use their standard uppercase spelling, for example:

text methods GET POST 

A request method not permitted by a command's methods metadata returns 405 Method Not Allowed. In a
multi-stage pipeline, every stage must permit the request method.

The mutates field is boolean:

text mutates true mutates false 

The default is:

text mutates false 

GET must not mutate. A metadata file that permits GET and declares mutates true is invalid metadata
and returns 500 for requests resolving to that command. For non-GET mutating commands, the command
must opt into the relevant method with methods metadata.

The parse-mode field defaults to:

text parse-mode normal 

The only additional v1 parse mode is:

text parse-mode raw 

When a resolved command declares parse-mode raw, the runtime passes the remaining still-encoded URL
suffix to that command and stops pipeline parsing. A raw-parse command is only valid in leftmost
command position; elsewhere it is invalid metadata for that request and returns 500.

### 5.8 MIME

The mime field is a single media type string applied to the command's output when that command is the
final (leftmost in URL order) stage:

text mime application/json 

It sets the response Content-Type. The mime field is ignored for non-final stages, and is overridden
when a command emits a full HTTP response that sets its own Content-Type (§12.5 of runtime.md). When no
mime field is present, the MIME type is inferred heuristically. A malformed mime value is a malformed
recognized value and returns 500 (§5.5).

### 5.9 Stderr

The stderr field controls how a stage's standard error is handled. The default is:

text stderr discard 

The two v1 values are:

text stderr discard stderr merge 

stderr discard keeps standard error out of the response body for that stage. The runtime may still
capture stderr internally for error diagnostics (§10.3); discard refers to the response stream, not to
internal error reporting. stderr merge folds that stage's standard error into its standard output, the
metadata-level equivalent of marking that stage's output boundary with the /& URL token (§8). When both
a stderr merge field and a /& prefix apply to the same boundary, the effect is the same single merge.
Any other stderr value is a malformed recognized value and returns 500 (§5.5).

## 6. Query String Attachment Rules

Query strings attach to the command segment on which they appear.

The runtime parses per-command query strings from the raw request-target. A command query starts at
the first raw ? in a segment and ends at the next raw / or the end of the request-target. Query
parsing happens before percent-decoding values. Literal /, ?, &, and = inside query values must be
percent-encoded.

Example:

text /foo?x=1/bar/baz.txt 

The query string x=1 attaches only to foo. The suffix /bar/baz.txt remains available for command parsing or input suffix resolution.

Example:

text /foo/bar?x=1/baz.txt 

The query string x=1 attaches to bar only if bar is recognized as a command stage.

### 6.1 Core Query Argv

The core spec reserves query argv semantics.

Command-specific query parameters are allowed, but are not interpreted by the core parser unless reserved by the spec.

For example:

text /grep?pattern=needle/file.txt 

Here pattern=needle is command-specific, not a core argv rule.

By contrast:

text /grep?arg=needle/file.txt 

uses core argv semantics and parses as:

sh cat file.txt | grep needle 

Repeated query argv parameters produce multiple argv entries.

Example:

text /grep?arg=-i&arg=needle/file.txt 

parses as:

sh cat file.txt | grep -i needle 

In v1, arg is the only reserved core query parameter. All other parameter names — including argv — are command-specific and are not interpreted by the core parser.

### 6.2 Query Argv Disables Metadata Arity

If query argv is present for a command, it disables metadata path arity for that command.

Metadata arity specifies how many path elements to consume as command arguments only when query argv is not used. When query argv is used, the command consumes zero path arguments and following segments are parsed as pipeline stages or input suffix.

### 6.3 Core Arg on Non-command Segments

Core arg is valid only on a recognized command segment.

Example:

text /grep/-i?arg=needle/file.txt 

is invalid because -i is not a recognized command segment in this parse, so arg cannot attach to it as core argv.

The runtime should return 400 Bad Request.

### 6.4 Query Args in Pipelines

Example:

text /grep?arg=needle/jq?arg=.items%5B%5D/haystack.json 

parses as:

sh cat haystack.json | jq '.items[]' | grep needle 

## 7. Pipeline Boundary Rules

Known command segments inside a suffix create pipeline stages.

Example:

text /grep/jq/haystack.txt 

If both grep and jq are metadata-free commands, this parses as:

sh cat haystack.txt | jq | grep 

The resulting command behavior is governed by normal command execution and exit-status mapping. For example, grep with no pattern may exit nonzero and produce a 400 response under default exit handling.

A metadata-free command does not consume following path segments as argv. Therefore:

text /foo/bar/baz/file.txt 

If foo and baz are commands, bar is not, and no metadata exists, the URL is invalid and returns 400 Bad Request.

It does not parse as either:

sh baz file.txt | foo bar 

or:

sh foo bar baz file.txt 

## 8. /& Stderr Rules

/& is a pipeline boundary token between stages.

It corresponds to shell |&.

The token is written as a prefix on the command segment whose output boundary is to be merged. That boundary is the connection from the prefixed command to the stage appearing immediately before it in URL order (the prefixed command's downstream consumer in data-flow order).

Example:

text /wc/-l/grep/error/file.txt 

parses as:

sh cat file.txt | grep error | wc -l 

Example:

text /wc/-l/&grep/error/file.txt 

parses as:

sh cat file.txt | grep error |& wc -l 

The /& token modifies exactly one pipeline boundary. It does not place the remainder of the pipeline into stderr-merge mode.

Example:

text /count/&filter/&noisy/file.txt 

Each /& affects only the boundary it marks.

A prefix is legal on the rightmost command stage; it modifies that command's output connection to the stage appearing immediately before it in URL order (its downstream consumer), never the implied cat input connection feeding it.

Example:

text /wc/&grep/file.txt 

The & prefixes grep and marks the grep→wc boundary (grep's output flowing into wc), not the cat file.txt → grep input boundary.

### 8.1 Command Names Beginning With &

The /& prefix is detected on the raw segment before percent-decoding: the runtime tests for a raw leading & on the segment, strips it if present, and then percent-decodes the remainder to obtain the command name used for PATH lookup.

A literal command name that begins with & is therefore discouraged. To address such a command, percent-encode the leading & as %26 so it is decoded to a name character rather than parsed as a stderr-merge prefix.

## 9. File, Directory, Command, and Synthesized Resource Precedence

### 9.1 Exact Filesystem Path Wins

If the complete request path resolves to an exact filesystem path, that path wins before command parsing.

Exact filesystem matching is performed after splitting the raw request-target on raw / and before
interpreting any per-segment query syntax as command syntax.

A raw ? is an ordinary-resource query only when it appears in the final path segment with no raw /
after it. In that case the runtime first strips the query and attempts the exact filesystem match
against the path without it, so /file.txt?download=1 may resolve to /file.txt. Only if that match
misses is the segment reinterpreted as a command carrying a per-command query (§6). A raw ? that has
any raw / after it is always per-command query syntax and prevents exact filesystem matching; to match
a literal ? as part of a filesystem name, percent-encode it as %3F.

For filesystem lookup, raw path segments are split before percent-decoding. Decoded / and NUL are
invalid in ordinary filesystem path segments. Dot segments are normalized for filesystem lookup, and
ordinary literal file serving must reject any path that escapes the configured root. Symlink escape
behavior is implementation-defined; the default policy should reject symlinks that expose files
outside the root for direct file serving.

Leading, trailing, and repeated raw / are collapsed before parsing, so an empty path segment is never
a valid command or argument segment. A trailing slash is not significant: /dir/ and /dir resolve to the
same resource, and /wc/ parses identically to /wc.

Example:

text /bin/wc 

If /bin/wc exists as a file under the project root and bin is not a command, the runtime serves the file.

No attempt is made to reinterpret wc as a command.

### 9.2 No Command Lookup After Directory Traversal

Command lookup does not apply inside ordinary directory traversal.

Example:

text /docs/grep/needle/file.txt 

If /docs is a real directory, grep is on the command PATH, and /docs/grep/needle/file.txt does not exist, the runtime returns 404 Not Found.

It does not reinterpret grep as a command after entering /docs.

### 9.3 Command Arguments Before Input Suffix

If a command has metadata arity, path arguments are consumed before interpreting the remainder as input suffix.

Example metadata:

text arity 1 

Example URL:

text /grep/docs/file.txt 

This parses as:

sh cat file.txt | grep docs 

The segment docs is the argument. The segment file.txt is the input suffix.

### 9.4 Directory Input Suffix

A directory may appear as the suffix supplied through implied cat.

Example:

text /wc/docs 

If wc is metadata-free and /docs is a directory, this behaves as:

sh cat docs | wc 

Implied-cat suffix evaluation uses filesystem file bytes only. Direct HTTP directory behavior, such as serving a configured default file or producing a directory listing, does not apply when the directory is used as a pipeline input suffix. A directory suffix is passed to the implied cat operation as a filesystem path and may fail naturally; any resulting failure is determined by the actual behavior of the command pipeline and exit-status mapping.

### 9.5 Synthesized Resources

Synthesized resources are allowed in the same namespace as files and directories.

Precedence:

1. Exact filesystem resource wins first.
2. Command parse wins over synthesized resource.
3. Synthesized resource may resolve if no exact filesystem resource exists and command parsing does not apply or does not win.

A synthesized resource is consulted only when no command parse starts (the leftmost segment is not a command). If a command parse starts and then fails, the result is 400 and is terminal (§2 step 9); the runtime does not fall back to a synthesized resource. "Does not win" therefore covers a command parse that never starts, not one that started and errored.

Therefore, if /docs/index is synthesized and /docs/index can also parse as a command pipeline, the command parse wins over the synthesized resource.

Synthesized resources may resolve globally or after partial directory traversal, including beneath real directories whose exact requested child path does not exist. For example, if /docs is a real directory and /docs/index is not a real file, an implementation-defined synthesized /docs/index may resolve as long as no exact filesystem resource or command parse wins.

A runtime may optionally emit a diagnostic header indicating that a synthesized resource was available but lost precedence to a command parse. Broader synthesized-resource discovery is limited in v1 to optional headers and implementation-defined resources; no conventional discovery command or resource is required.

## 10. Error Reporting Rules

### 10.1 400 Bad Request

Return 400 Bad Request when command parsing starts but the URL is invalid for client-controlled query rules, arity rules, pipeline rules, or default metadata-free behavior.

Examples include:

text /wc/-l/file.txt 

when wc is metadata-free.

text /grep/-i?arg=needle/file.txt 

because core arg appears on a non-command segment.

Exact error-message text is not normative.

Implementations should provide helpful failure information, such as:

- command where parsing failed,
- unexpected segment,
- effective metadata/defaults,
- suggested query-string rewrite,
- effective pipeline if one was formed,
- candidate interpretations if ambiguity occurred.

### 10.2 404 Not Found

Return 404 Not Found when no exact filesystem resource exists, no synthesized resource wins, and no command parse can start.

Example:

text /not-found/path.txt 

returns 404 if no such resource exists and not-found is not a command.

### 10.3 Nonzero Command Exit

Default mapping:

text exit 0 => HTTP 200 exit nonzero => HTTP 400 

In a multi-stage pipeline, every stage's exit status is mapped independently. If any mapped status is
non-2xx, the whole response is an error. When multiple stages fail, the first failing stage in URL
order determines the HTTP status and primary diagnostic.

For nonzero command exits, the response may include:

- command name,
- exit status,
- limited sanitized stdout,
- limited sanitized stderr,
- effective pipeline.

The response should not be generic-only unless an implementation intentionally suppresses detail for safety or policy reasons.

The byte limits for included stdout/stderr are implementation-defined; the recommended default is a cap of 8 KiB each, with truncation indicated in the response.

### 10.4 500 Internal Server Error

The exact classification of runtime failures as 500 is not fully normative.

Reasonable 500 cases include:

- command executable could not be invoked despite being resolved,
- pipe setup failure,
- internal interpreter exception,
- runtime filesystem failure,
- implementation bug.

Malformed metadata (an unrecognized value for a recognized field, or a reserved-but-undefined form such as a range arity) returns 500, since it is a server-side configuration error rather than a client error (§5.5).

### 10.5 Error Response Format

Error responses are content-negotiated via the HTTP Accept header.

Plain text and JSON are both reasonable supported formats.

## 11. Optional Execution Metadata Headers

Successful command responses may expose execution metadata through headers.

These headers are suggested, not required. When a runtime does expose execution metadata via headers, it should use the following standardized names rather than inventing its own:

text X-WebShell-Command: grep X-WebShell-Pipeline: cat file.txt | grep needle X-WebShell-Source: root/path/file.txt 

Implementations may also expose this information through an optional explain command, but the existence of explain is not required by this addendum.

## 12. Canonical Parsing Examples

### 12.1 Exact Filesystem Resource

text /a/b/c.txt 

If /a/b/c.txt exists, serve it directly.

If it does not exist and a is not a command, return 404.

If it does not exist and a is a metadata-free command, and /b/c.txt exists, parse as:

sh cat b/c.txt | a 

### 12.2 Metadata-Free Pipeline

text /foo/bar/baz/qux.txt 

If foo and bar are metadata-free commands and /baz/qux.txt exists:

sh cat baz/qux.txt | bar | foo 

### 12.3 Query Argv Pipeline

text /grep?arg=needle/jq?arg=.items%5B%5D/haystack.json 

parses as:

sh cat haystack.json | jq '.items[]' | grep needle 

### 12.4 Metadata Path Argv Pipeline

Given:

text grep: arity 1 jq: arity 1 wc: arity 1 

the URL:

text /wc/-l/grep/needle/jq/.items%5B%5D/haystack.json 

parses as:

sh cat haystack.json | jq '.items[]' | grep needle | wc -l 

Without that metadata, the same URL returns 400 Bad Request.

### 12.5 Stderr Boundary

text /wc/-l/&grep/error/file.txt 

Given wc and grep each have arity 1, this parses as:

sh cat file.txt | grep error |& wc -l 

## 13. Ambiguous or Invalid Examples

### 13.1 Metadata-Free Path Args Are Invalid

text /wc/-l/file.txt 

If wc has no metadata, this returns 400 Bad Request.

Correct metadata-free form:

text /wc?arg=-l/file.txt 

### 13.2 Metadata-Free Multi-Command Path Args Are Invalid

text /wc/-l/grep/needle/jq/.items%5B%5D/haystack.json 

If all commands are metadata-free, this returns 400 Bad Request.

Correct metadata-free form:

text /wc?arg=-l/grep?arg=needle/jq?arg=.items%5B%5D/haystack.json 

### 13.3 Core Arg on a Non-command Segment Is Invalid

text /grep/-i?arg=needle/file.txt 

returns 400 Bad Request because -i is not a recognized command segment in this parse.

Use one of these forms instead:

text /grep/-i/needle/file.txt 

if metadata supports the needed path arity, or:

text /grep?arg=-i&arg=needle/file.txt 

for metadata-free query argv.

### 13.4 No Command Lookup Inside Directory Traversal

text /docs/grep/needle/file.txt 

If /docs is a directory, grep is a command, and the full filesystem path does not exist, return 404.

Do not reinterpret grep as a command from inside /docs.

## 14. Recommended Implementation Tests

Implementations should include tests for the following cases.

### 14.1 Filesystem Precedence

- Existing /grep/docs/file.txt wins over command parse.
- Existing /bin/wc is served as a file when bin is not a command.

### 14.2 Metadata-Free Defaults

- Metadata-free command consumes zero path args.
- Metadata-free command receives stdin by default.
- Rightmost suffix is supplied through implied cat.
- Known command segments inside suffix create pipeline stages.

### 14.3 Metadata Arity

- arity 0
- arity 1
- arity *
- Exact path-argument consumption before input suffix.
- Variable arity consumes the rest of the URL.

### 14.4 Query Argv

- ?arg=value
- repeated ?arg=...&arg=...
- query argv disables metadata path arity.
- core arg on a non-command segment returns 400.
- literal /, ?, &, and = inside query values must be percent-encoded.

### 14.5 Pipeline Boundaries

- normal |
- /& as |&
- /& affects one boundary only.
- /& before rightmost command modifies that command’s connection leftward, not the implied cat.

### 14.6 Error Handling

- no resource and no command parse returns 404.
- command parse starts but arity fails returns 400.
- nonzero command exit defaults to 400.
- malformed recognized metadata returns 500.
- multi-stage pipeline status uses pipefail-like aggregation.
- content negotiation controls error response format.

### 14.7 Synthesized Resources

- synthesized resources may exist in the namespace.
- exact filesystem resources beat synthesized resources.
- command parse beats synthesized resources.

## 15. Resolved Questions

The questions previously open in this section are resolved as follows:

1. Variable arity: only fixed N and arity * are defined in v1; range forms (arity 0..*, arity 1..3) are reserved for a future extension and are malformed in v1 (§5.2, §5.5).
2. Reserved query namespace: arg is the only reserved core parameter; argv and all other names are command-specific (§6.1). Core arg is valid only on recognized command segments and disables metadata path arity (§6.2, §6.3).
3. Metadata grammar: # line comments, whitespace-separated tokens, last-occurrence-wins for duplicates, unknown fields ignored, malformed values → 500 (§5.5).
4. Normative metadata field list: arity, input, output, methods, mime, mutates, parse-mode, stderr, exit (§5.6).
5. Malformed metadata → 500 (§5.5, §10.4).
6. Error-body stdout/stderr limits: implementation-defined, recommended 8 KiB cap each with truncation indicated (§10.3).
7. cat over a directory: allowed to fail naturally per the command's real behavior (§9.4).
8. Command names beginning with &: discouraged; percent-encode the leading & as %26 (§8.1).
9. Synthesized resource that lost to a command parse: may be reported via an optional diagnostic header; not required (§9.5).
10. Execution metadata headers: standardized as X-WebShell-Command, X-WebShell-Pipeline, X-WebShell-Source (§11).
11. Per-command query strings end at the next raw /; literal /, ?, &, and = in query values must be percent-encoded (§6).
12. Metadata-free commands permit GET only and default to mutates false (§5.7).
13. No suffix and no request body means stdin is closed and empty (§4).
14. Multi-stage pipeline exit status is pipefail-like; the first failing stage in URL order (the most downstream stage) wins (§5.4, §10.3).
15. Symlink escapes for direct file serving are implementation-defined; the default policy should reject them (§9.1).
16. stderr field values: discard (default) and merge; any other value is malformed and returns 500 (§5.9).
17. mime field: a single media type that sets the final stage's Content-Type; malformed values return 500 (§5.8).
18. exit field grammar: whitespace-separated code=status pairs, code a non-negative integer or *, explicit code beating * (§5.4).
19. Trailing ? in the final segment is an ordinary-resource query (filesystem match attempted first); a ? followed by any raw / is per-command syntax (§9.1).
20. A 400 from a started command parse is terminal and does not fall back to a synthesized resource (§2, §9.5).
21. Argument segments are percent-decoded and passed verbatim; they may contain bytes illegal in filesystem segments, including a decoded / (§5.1).
22. Leading, trailing, and repeated / are collapsed; an empty segment is never a valid command or argument, and a trailing slash is not significant (§9.1).
23. The implied cat is a runtime primitive, not resolved through PATH and carrying no metadata or method restriction (§4).
24. The /& prefix is detected on the raw segment before percent-decoding the command name (§8.1).
