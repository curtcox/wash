# Addendum: URL Pipeline Parsing and Metadata-Free Command Arity

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

Given an HTTP request path:

1. Decode URL path segments according to normal URL path decoding rules.
2. Check whether the request path resolves to an exact filesystem resource.
   - If yes, the exact filesystem resource wins.
   - No command parsing is attempted for that path.
3. If no exact filesystem resource exists, attempt command parsing from the leftmost segment.
4. If the leftmost segment is not a command and no exact filesystem resource exists, return 404 Not Found, unless a synthesized resource resolves.
5. If the leftmost segment is a command, begin a command pipeline parse.
6. For each command stage:
   - Resolve the command name through the command PATH.
   - Load metadata from root/env/meta/<command> if present.
   - If metadata is absent, use metadata-free defaults.
   - Determine argv from either query arguments or path arguments.
   - Query argv overrides metadata path arity.
   - Mixing query argv and path argv for the same command is invalid.
7. Continue scanning the remaining suffix for known command segments.
   - Known command segments inside a suffix create pipeline stages.
   - Each recognized command divides the URL into another stage.
8. The final rightmost non-command suffix is supplied as input through an implied cat.
9. If command parsing starts but the URL violates arity, query, boundary, or metadata rules, return 400 Bad Request.
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

text arity 0 input stdin 

This means a metadata-free command consumes zero path arguments. Remaining suffix segments are not treated as argv for that command.

If the remaining suffix contains known command names, those command names create further pipeline stages.

If the rightmost remaining suffix resolves as a file or directory path, it is supplied to the pipeline through an implied cat.

Example:

text /foo/bar/baz/qux.txt 

If foo is a metadata-free command, bar is not a command, and /bar/baz/qux.txt exists, this parses as:

sh cat bar/baz/qux.txt | foo 

Example:

text /foo/bar/baz/qux.txt 

If both foo and bar are metadata-free commands, and /baz/qux.txt exists, this parses as:

sh cat baz/qux.txt | bar | foo 

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

### 5.2 Variable Arity

Metadata may support variable arity.

At minimum, the following form is supported:

text arity * 

arity * means the command consumes the rest of the URL as argv, leaving no input suffix and no downstream pipeline unless another explicit rule overrides this behavior.

Example:

text /cmd/a/b/c.txt 

If cmd has:

text arity * 

then the command receives:

text ["a", "b", "c.txt"] 

as argv.

### 5.3 Input and Output

Metadata defines stdin/stdout behavior separately from arity.

The metadata-free default input mode is:

text input stdin 

Additional input/output modes may be specified by metadata, for example:

text input stdin input file input none output stdout output file 

The exact complete set of input/output modes remains implementation-defined unless otherwise specified by the main specification.

### 5.4 Exit Status Mapping

Default exit mapping is:

text exit 0 => 200 exit nonzero => 400 

Metadata may override specific exit codes.

Example:

text exit 0=200 1=404 *=400 

## 6. Query String Attachment Rules

Query strings attach to the command segment on which they appear.

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

### 6.2 Query Argv Overrides Metadata Arity

If query argv is present for a command, it overrides metadata path arity for that command.

Metadata arity specifies how many path elements to consume as command arguments only when query argv is not used.

### 6.3 Mixing Query Argv and Path Argv

Mixing query argv and path argv for the same command is invalid.

Example:

text /grep/-i?arg=needle/file.txt 

is invalid because -i is a path argument while arg=needle is a query argument for the same command.

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

The syntax is attached as a prefix to the command segment on the left side of the boundary in URL order.

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

/& is legal before the rightmost command stage, but it modifies that command’s connection to the next command to its left. It does not modify the implied cat input connection.

Example:

text /wc/&grep/file.txt 

The /& marks the boundary between grep and wc, not the boundary between cat file.txt and grep.

## 9. File, Directory, Command, and Synthesized Resource Precedence

### 9.1 Exact Filesystem Path Wins

If the complete request path resolves to an exact filesystem path, that path wins before command parsing.

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

Any resulting failure is determined by the actual behavior of the command pipeline and exit-status mapping.

### 9.5 Synthesized Resources

Synthesized resources are allowed in the same namespace as files and directories.

Precedence:

1. Exact filesystem resource wins first.
2. Command parse wins over synthesized resource.
3. Synthesized resource may resolve if no exact filesystem resource exists and command parsing does not apply or does not win.

Therefore, if /docs/index is synthesized and /docs/index can also parse as a command pipeline, the command parse wins over the synthesized resource.

## 10. Error Reporting Rules

### 10.1 400 Bad Request

Return 400 Bad Request when command parsing starts but the URL is invalid for command metadata, query rules, arity rules, pipeline rules, or default metadata-free behavior.

Examples include:

text /wc/-l/file.txt 

when wc is metadata-free.

text /grep/-i?arg=needle/file.txt 

because query argv and path argv are mixed for the same command.

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

For nonzero command exits, the response may include:

- command name,
- exit status,
- limited sanitized stdout,
- limited sanitized stderr,
- effective pipeline.

The response should not be generic-only unless an implementation intentionally suppresses detail for safety or policy reasons.

### 10.4 500 Internal Server Error

The exact classification of runtime failures as 500 is not fully normative.

Reasonable 500 cases include:

- command executable could not be invoked despite being resolved,
- pipe setup failure,
- internal interpreter exception,
- runtime filesystem failure,
- implementation bug.

Whether malformed metadata is 400 or 500 is implementation-defined unless specified elsewhere.

### 10.5 Error Response Format

Error responses are content-negotiated via the HTTP Accept header.

Plain text and JSON are both reasonable supported formats.

## 11. Optional Execution Metadata Headers

Successful command responses may expose execution metadata through headers.

These headers are suggested, not required.

Examples:

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

### 13.3 Mixing Query Argv and Path Argv Is Invalid

text /grep/-i?arg=needle/file.txt 

returns 400 Bad Request.

Use one style:

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
- query argv overrides metadata path arity.
- mixing query argv and path argv returns 400.

### 14.5 Pipeline Boundaries

- normal |
- /& as |&
- /& affects one boundary only.
- /& before rightmost command modifies that command’s connection leftward, not the implied cat.

### 14.6 Error Handling

- no resource and no command parse returns 404.
- command parse starts but arity fails returns 400.
- nonzero command exit defaults to 400.
- content negotiation controls error response format.

### 14.7 Synthesized Resources

- synthesized resources may exist in the namespace.
- exact filesystem resources beat synthesized resources.
- command parse beats synthesized resources.

## 15. Remaining Open Questions

1. Whether variable arity forms beyond arity * are supported, such as:

text arity 0..* arity 1..3 

2. The exact reserved query namespace:
   - arg is core.
   - Whether argv is also core remains unresolved.
   - Other names remain command-specific unless reserved elsewhere.

3. Exact metadata grammar for quoting, escaping, comments, duplicate fields, and invalid fields.

4. Full normative list of metadata fields beyond arity, input, output, methods, stderr, and exit.

5. Whether malformed metadata returns 400, 500, or an implementation-defined status.

6. Exact stderr/stdout sanitization limits for error responses.

7. Exact behavior of cat over directories:
   - The current rule is that a directory suffix may be passed to implied cat.
   - The resulting command behavior is allowed to fail naturally.

8. Whether command names literally beginning with & require escaping or are simply discouraged.

9. Whether synthesized resources should be able to report why they lost precedence to a command parse.

10. Whether optional execution metadata headers should have standardized names or remain implementation-defined suggestions.