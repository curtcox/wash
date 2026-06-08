# URL Filesystem Router Runtime Specification

> This core spec is extended by pipeline_parsing.md (URL pipeline parsing and metadata-free arity).

## 1. Problem Statement

Programmers routinely compose shell commands, filesystem paths, pipes, aliases, scripts, and environment-driven behavior into powerful reusable workflows. Browsers and URLs provide a universal, inspectable, bookmarkable interface, but ordinary web applications usually hide composition behind application-specific UI and server-side routing.

This specification defines a runtime behavior contract for a local, browser-accessible environment where URLs map transparently to a project directory and where URL path segments can compose commands, files, arguments, and pipelines in a shell-like way.

The core idea is that a URL should be almost as readable and reusable as a shell pipeline. For example:

text http://local/grep/needle/jq/haystack.json 

corresponds approximately to (given grep has arity 1):

sh cat haystack.json | jq | grep needle 

The system is intended for programmers, should work in an ordinary browser with no extension, and should also provide a reasonable experience through tools such as curl.

## 2. Goals

The system should:

1. Map local URLs to a single project/root directory.
2. Treat the filesystem as the immediate source of truth.
3. Preserve ordinary URL and HTTP semantics unless explicitly specified otherwise.
4. Allow path segments to represent files, commands, command arguments, and pipeline composition.
5. Resolve commands through a shell-like ordered search path.
6. Allow commands to be ordinary files interpreted through configurable runtime rules.
7. Allow command metadata, but not require it.
8. Support raw file access by default.
9. Support command composition without requiring browser extensions or custom browser shells.
10. Make URL expressions readable, bookmarkable, shareable, and inspectable.
11. Support Git-friendly persistence and sharing through ordinary files and directories.
12. Support at least GET, PUT, POST, and DELETE.
13. Ensure that GET does not mutate local state by contract.
14. Keep visual composition tools, package management, distributed execution, and browser extensions out of the core specification.

## 3. Non-goals

The specification does not require or define:

1. A browser extension.
2. A custom browser-like shell.
3. A visual URL builder.
4. Live filesystem watching.
5. Distributed or multi-machine execution.
6. Command signing, trust prompts, quarantine, or package trust management.
7. A package manager.
8. Guaranteed portability of command directories across machines.
9. Database-backed resources.
10. A required Git integration.
11. A required explain command.
12. A required editor UI.
13. A required directory layout.
14. A required root-selection mechanism.
15. A required bind address or network exposure policy.

## 4. Core Concepts

### 4.1 Runtime

A runtime is a local HTTP server that maps one configured root directory to one local URL origin.

Examples:

text http://local/ http://localhost:PORT/ 

local is a conceptual placeholder. Implementations may use localhost, 127.0.0.1, a custom local hostname, or another local origin.

### 4.2 Root Directory

The root directory is the default content root for URL resolution. The filesystem is the immediate source of truth. The root may be empty and still valid.

A server instance maps one root directory. Multiple projects should generally use multiple server instances.

### 4.3 Resource

A resource is anything addressable by URL. A resource may be:

1. A plain file.
2. A directory.
3. The output of a command.
4. A synthesized response produced by implementation-defined behavior.
5. A result of a composed URL pipeline.

Not every URL result must correspond to a concrete backing file. However, ordinary non-command file paths should map literally to filesystem paths under the configured root unless implementation-defined behavior applies.

### 4.4 Command

A command is a file resolved through the command search path. A command segment is not a reserved runtime primitive. If a segment appears in command position and a command by that name exists on the path, the runtime treats it as a command.

Commands may be shell scripts, Python scripts, compiled binaries, symlinks, plain files interpreted by external interpreters, or other runnable artifacts.

A command does not need to have its host OS executable bit set. It does not need a shebang. It may be executable only by virtue of runtime interpreter rules.

### 4.5 URL Pipeline

A URL pipeline is a composed URL expression where leftward command prefixes apply to rightward suffixes.

Example:

text /grep/needle/jq/haystack.json 

maps approximately to (given grep has arity 1):

sh cat haystack.json | jq | grep needle 

Command resolution proceeds left-to-right, even though data flow is generally right-to-left. The rightmost file is supplied to the pipeline through an implied cat (see pipeline_parsing.md §4), not as a positional argument.

### 4.6 Argument Segment

Some URL path segments are literal command arguments rather than files or commands.

Example:

text /grep/needle/file.txt 

Given grep with arity 1, needle is a literal argument.

### 4.7 Per-command Query String

A command segment may carry a query string to supply named arguments or disambiguate parsing.

Example:

text /grep?pattern=needle&ignore-case=true/jq?filter=.items[]/haystack.json 

Per-command query strings are explicitly supported. The core argv parameter is arg (repeatable); names such as pattern, filter, and ignore-case shown here are command-specific and are interpreted by the command itself, not by the core parser (pipeline_parsing.md §6.1). A URL may carry more than one ? — one per command segment. This is valid URI syntax (RFC 3986 §3.4 permits ? and / within a query), and browsers and curl transmit the full request-target unchanged, so the runtime parses it directly; see §12.2.

## 5. Terminology

Root  
The configured filesystem directory served by one runtime instance.

Command path  
An ordered list of directories used to resolve command names.

Command segment  
A URL path segment that resolves to a command in command position.

Argument segment  
A URL path segment consumed as an argument to a command.

Input suffix  
The remaining right-hand URL expression consumed by a command as input.

Pipeline boundary  
The point where one command’s arguments end and the next command or input resource begins.

Metadata  
Optional command-specific information such as arity, input mode, output mode, methods, MIME hints, mutation behavior, and parse mode.

Interpreter rule  
A rule defining how a command file should be executed.

Transparent URL  
A URL whose path structure lets a programmer infer the likely command/resource composition by inspection, while acknowledging that command definitions may shadow or redefine behavior just as shell commands can.

## 6. URL-to-directory Mapping Rules

### 6.1 Literal File Mapping

A plain URL path maps literally to a path under the root directory.

Example:

text GET /arbitrary.txt 

maps to:

text root/arbitrary.txt 

and returns the raw file.

### 6.2 Command Shadowing

An exact full-path filesystem resource always wins first (see §6.3). Command parsing begins only when the complete request path does not resolve to a file. The resolution precedence ladder is (see also pipeline_parsing.md §9.5):

1. Exact full-path filesystem resource.
2. Command parse.
3. Synthesized resource.
4. 404 Not Found.

Once command parsing has begun, if a segment appears in command position and a command by that name exists on the command path, the command takes precedence over an ordinary file of the same name.

Example:

text /wc/foo.txt 

If no file root/wc/foo.txt exists and wc exists on the command path, this executes approximately:

sh cat foo.txt | wc 

even if root/wc also exists as a regular file. (Because root/wc is a regular file, root/wc/foo.txt cannot exist, so the exact-path check fails and command parsing proceeds.)

For the single-segment case /wc, if root/wc exists as a file the exact filesystem path wins and the file is served, even though wc is also a command.

### 6.3 Direct File Access to Commands

Command files can still generally be viewed by addressing their concrete filesystem path.

Example:

text /bin/wc 

views:

text root/bin/wc 

unless some earlier path segment such as bin itself resolves as a command or implementation-defined behavior overrides ordinary file serving.

Commands such as cat, raw, or file may also be defined:

text /cat/bin/wc /raw/bin/wc /file/bin/wc 

These work only if the corresponding commands are present and appropriately defined.

### 6.4 Missing Paths

If no valid parse exists and no file/resource can be resolved, the default response is:

text 404 Not Found 

Implementations may synthesize responses for missing paths through implementation-defined directory or resource behavior. Synthesized resources rank below command parses in the precedence ladder (see §6.2 and pipeline_parsing.md §9.5).

### 6.5 Directories

When a request resolves to a directory, the default behavior is:

1. If an index.html (or analogous configured default file) is present, serve it.
2. Otherwise, produce a directory listing.
3. Implementations may substitute other implementation-defined behavior.

A configured default file takes precedence over a directory listing when both are possible.

## 7. Directory Layout

No directory layout is mandatory. A root may be empty.

The following is a simple conventional example, not a required structure:

text root/   env/     path     meta/       jq       grep       wc   exec   bin/     wc     grep     jq     explain   arbitrary.txt   haystack.json 

### 7.1 Command Search Path

If present, the command search path may be stored at:

text root/env/path 

The file is line-oriented. Each non-empty line names a command directory.

Example:

text bin vendor/bin ../shared/bin 

Paths may point outside the root. The root is the default content root, not necessarily a hard filesystem sandbox boundary for command search.

### 7.2 Interpreter Rules

If present, interpreter rules may be stored at:

text root/exec 

The file is line-oriented. Each rule has the form:

text <pattern> <interpreter> [args...] 

Rules are evaluated from top to bottom. The first matching rule wins.

Grammar and matching rules:

1. One rule per line.
2. Blank lines are ignored.
3. A line whose first non-whitespace character is # is a comment and is ignored. Inline # is not a comment.
4. Tokens are separated by ASCII whitespace. Quoting and escaping are not defined in v1; values requiring whitespace are out of scope.
5. A rule must contain at least a pattern and an interpreter.
6. A pattern with no glob metacharacters matches the command basename exactly.
7. A pattern containing glob metacharacters (*, ?, or []) matches both the command basename and the command path relative to the matched command directory.
8. If no rule matches and the command cannot otherwise be executed, interpreter resolution fails (§15.5).
9. A malformed rule makes interpreter-rule evaluation invalid; a request that needs interpreter-rule evaluation returns 500 Internal Server Error.

Example:

text for_this_command_only sh *.py /usr/bin/python3 

Interpreter rules determine how command files are executed when they are not directly executable, lack a shebang, or require an external interpreter.

### 7.3 Command Metadata

If present, command metadata may be stored under:

text root/env/meta/<command> 

Example:

text root/env/meta/jq 

Metadata is plain line-oriented text. No metadata is required. Defaults apply for unspecified fields.

The defined metadata fields are (see pipeline_parsing.md §5.6):

text arity input output methods mime mutates parse-mode stderr exit 

The line-oriented grammar (comments, whitespace-separated tokens, duplicate handling, and malformed-value behavior) and the normative field list are specified in pipeline_parsing.md §5.5 and §5.6. The format remains readable and Git-friendly.

## 8. URL Grammar and Examples

### 8.1 Basic Resource

text /arbitrary.txt 

Returns:

text root/arbitrary.txt 

### 8.2 Unary Command Over File

text /wc/arbitrary.txt 

Approximate shell equivalent:

sh cat arbitrary.txt | wc 

### 8.3 Pipeline

text /grep/needle/jq/haystack.json 

Approximate shell equivalent (given grep has arity 1):

sh cat haystack.json | jq | grep needle 

### 8.4 Longer Pipeline

text /wc/-l/grep/needle/jq/.items%5B%5D/haystack.json 

Approximate shell equivalent (given wc, grep, and jq each have arity 1):

sh cat haystack.json | jq '.items[]' | grep needle | wc -l 

Flags are ordinary argument segments. The input file is supplied through an implied cat; no explicit cat segment is needed.

### 8.5 Per-command Query Strings

text /grep?pattern=needle&ignore-case=true/jq?filter=.items[]/haystack.json 

This supplies named arguments to individual command segments. Here pattern, filter, and ignore-case are command-specific parameters; the core argv parameter is arg. The metadata-free core form is:

text /grep?arg=-i&arg=needle/jq?arg=.items%5B%5D/haystack.json 

### 8.6 Argument Collision With Command Name

Given grep with arity 1:

text /grep/jq/haystack.txt 

means (given grep has arity 1):

sh cat haystack.txt | grep jq 

Here jq is a literal pattern argument, not a command, because grep consumes one argument before its input suffix. Argument segments are passed verbatim as strings; the runtime does not resolve them to file contents. Only the implied-cat input suffix is read as bytes.

### 8.7 Ambiguous Cases

Ambiguous cases should use query strings. Defining clearer commands is often preferable.

For example, instead of relying on an ambiguous interpretation of:

text /grep/jq/haystack.txt 

a user could define:

text /find_jq/haystack.txt 

as a command.

### 8.8 Standard Error Pipeline Marker

The token /& marks a single pipeline boundary as a stdout+stderr merge, analogous to shell |&. It is written as a prefix on a command segment (pipeline_parsing.md §8); it merges that command's output boundary — the connection to the stage appearing immediately before it in URL order (its downstream consumer in data-flow order).

Example:

text /wc/-l/&grep/error/file.txt 

parses as (given wc and grep have arity 1):

sh cat file.txt | grep error |& wc -l 

The & prefixes grep and merges only the grep→wc boundary. It does not affect the implied-cat connection feeding grep, and it does not place the rest of the pipeline into stderr-merge mode.

## 9. Resource Lifecycle

### 9.1 GET

GET must not mutate local state.

Examples:

text GET /file.txt GET /wc/file.txt GET /grep/needle/file.txt 

These may read files, execute commands, and compute output, but must not intentionally modify local state.

### 9.2 PUT

PUT creates or replaces an ordinary file resource in the core contract unless an implementation policy disables file writes. If disabled by policy, the runtime must reject the request with an appropriate HTTP error such as 403 Forbidden or 405 Method Not Allowed.

PUT targets the literal filesystem path only; it does not trigger command parsing or the command-shadowing ladder of §6.2. Writing the computed output of a pipeline is not meaningful, so PUT /wc/file.txt writes the literal file root/wc/file.txt (creating parent directories per implementation policy) rather than resolving wc as a command. The same applies to DELETE (§9.4).

Example:

text PUT /file.txt 

writes the request body to:

text root/file.txt 

### 9.3 POST

POST may trigger command-specific behavior or write results through command-defined semantics.

Example:

text POST /sort/output.txt/input.txt 

means approximately:

sh sort input.txt > output.txt 

Output redirection is not a core URL feature. The generic arity model would pass both segments as arguments (sort output.txt input.txt). The "write stdout to output.txt" behavior above must be supplied by a command-specific definition of sort, not inferred by the core parser.

A POST whose path resolves to an ordinary file or directory with no command governing it has no defined write semantics in the core spec and returns 405 Method Not Allowed. Writing to a plain file path is the role of PUT (§9.2).

### 9.4 DELETE

DELETE deletes an ordinary filesystem resource in the core contract unless an implementation policy disables deletion. If disabled by policy, the runtime must reject the request with an appropriate HTTP error such as 403 Forbidden or 405 Method Not Allowed.

Like PUT (§9.2), DELETE targets the literal filesystem path only and does not trigger command parsing.

Example:

text DELETE /file.txt 

deletes:

text root/file.txt 

### 9.5 Other HTTP Methods

Implementations may support additional standard HTTP methods such as:

text HEAD PATCH OPTIONS 

Normal HTTP semantics should be preserved. A request method not permitted by a command's methods metadata returns 405 Method Not Allowed. If methods metadata is absent, a command permits GET only. In a multi-stage pipeline, the request method must be permitted by every stage.

A command that permits GET also answers HEAD: the response is computed as for GET and the body is omitted. HEAD is suppressed only by listing methods that include GET but exclude HEAD. OPTIONS handling, including CORS preflight responses, is implementation-defined in v1 and is not governed by per-command methods metadata; see §13.1 for the cross-origin default.

GET must not mutate. The metadata-free default is mutates false. A command that mutates must opt into a non-GET method with methods metadata. A metadata file that permits GET and declares mutates true is invalid metadata and returns 500 for requests resolving to that command.

### 9.6 Refresh Behavior

When files change while a URL is open, browser refresh recomputes from the current filesystem state.

The specification does not require live updates, snapshots, or persistent caching.

### 9.7 Generated Results

Generated command results do not need stable materialized URLs. Implementations may cache results internally, but caching is not part of the core contract unless exposed explicitly.

## 10. Composition Model

### 10.1 Resolution Direction

Command resolution proceeds left-to-right.

Data flow usually proceeds right-to-left.

Example:

text /grep/needle/jq/haystack.json 

Resolution sees grep first, then determines that grep consumes needle as an argument and receives the evaluated suffix:

text /jq/haystack.json 

Data flow evaluates (given grep has arity 1):

sh cat haystack.json | jq | grep needle 

### 10.2 Arity

Command arity determines where command arguments end and the input suffix begins.

For example, if grep has arity 1:

text /grep/needle/jq/haystack.json 

means:

sh cat haystack.json | jq | grep needle 

Arity may be supplied through metadata. If missing, the command has arity 0 and receives input on stdin (pipeline_parsing.md §4). Argument segments are passed to the command as literal strings; the runtime does not resolve them to file contents. Only the implied-cat input suffix is read as bytes.

### 10.3 Boundaries Are Determined by Arity Alone

A command's argument segments are exactly its declared arity; the next pipeline stage begins immediately after. The parser does not infer a boundary from which segments happen to name commands on the command path (pipeline_parsing.md §7).

Example:

text /foo/bar/baz/file.txt 

If foo and baz are commands, bar is not, and no metadata exists, every command has arity 0, so foo consumes no arguments and bar is an unexpected segment. The URL is invalid and returns 400 Bad Request. It does not parse as:

sh baz file.txt | foo bar 

To express that pipeline, give foo arity 1 (so it consumes bar) via metadata, or use query argv.

### 10.4 Invalid Parses

Given the filesystem, command path, and metadata, parsing is deterministic (pipeline_parsing.md §2); there is no genuine multiple-parse ambiguity to resolve. The default response for client-controlled parse errors is:

text 400 Bad Request 

returned when command parsing begins but the URL violates arity, query, or boundary rules. Malformed recognized metadata is a server-side configuration error and returns 500. The response should include information about why the parse failed.

### 10.5 Commands Consuming Multiple Resources

Commands are not restricted to unary stream transforms. A command may consume multiple resources.

Example:

text /diff/a.txt/b.txt 

may mean:

sh diff a.txt b.txt 

if diff is given arity 2. This works through arity alone: a.txt and b.txt are passed as literal argv strings, and because the default working directory is the root (§12.3), diff opens them itself as root-relative paths. No non-stdin input mode is involved; in v1 the input metadata field selects only stdin (pipeline_parsing.md §5.3).

### 10.6 Request Body Input

For methods such as POST and PUT, the HTTP request body may become stdin for the rightmost command or input position, subject to command metadata or defaults.

Example:

text POST /grep/needle/sort 

with body input is approximately:

sh sort | grep needle 

where sort receives the request body on stdin.

When both a request body and a file input suffix are present, the explicit file suffix feeds the pipeline through implied cat; the request body is used as pipeline input only when no input suffix is present, or when a command explicitly captures it.

When there is no input suffix and no request body, stdin is closed and empty by default.

Users may define commands specifically for capturing, decoding, or transforming request bodies.

### 10.7 Commands That Consume URL Expressions

Some commands may operate on a URL expression rather than executing the suffix.

Example:

text /explain/grep/needle/jq/haystack.json 

Only explain is executed. It receives or consumes the remaining URL expression:

text /grep/needle/jq/haystack.json 

and explains it.

grep and jq are not executed in this case.

A command opts out of normal URL parsing by declaring parse-mode raw in its metadata. When the parser resolves such a command, it hands the command the remaining (still-encoded) URL suffix and stops parsing; downstream segments are neither resolved nor executed. A raw-parse command is only meaningful in leftmost command position, since it consumes everything to its right.

## 11. Browser Interaction Model

The system targets an ordinary browser with no extension.

### 11.1 Plain Files

A plain file request returns the raw file.

Example:

text GET /arbitrary.txt 

returns the content of:

text root/arbitrary.txt 

No inspector page is inserted by default.

### 11.2 Command Output

Command output is returned directly. There is no required shell-like UI wrapper.

MIME type may be specified by the command or inferred heuristically.

Example:

text GET /wc/arbitrary.txt 

likely returns text/plain.

### 11.3 Browser Affordances as Commands

Browser affordances should be composed as URL commands rather than injected globally.

Example:

text /edit/arbitrary.txt 

may invoke an edit command if defined.

### 11.4 curl Compatibility

Many URLs should also behave reasonably through curl.

Example:

sh curl http://localhost:PORT/grep/needle/file.txt 

should return the command output directly.

The v1 request-target model assumes a direct local connection to the runtime. Proxies, gateways, CDNs, or other intermediaries may normalize, reject, or rewrite unusual request-targets such as per-command multi-? URLs and are outside the v1 compatibility contract. URL fragments (#...) are never transmitted to the server and cannot participate in pipeline syntax.

### 11.5 History and UI

The runtime may keep its own history, logs, saved pipelines, or local browser-visible state, but none are required.

Autocomplete, command palettes, previews, drag-and-drop segment composition, and saved snippets are outside the core specification.

## 12. Runtime Architecture

### 12.1 Server

The runtime is a local HTTP server.

It maps one project/root directory to one local origin.

Root selection is implementation-dependent and outside this specification.

### 12.2 Request Handling

For each request, the runtime:

1. Parses the raw request-target itself using ordinary URL syntax, decomposing it into per-segment paths and query strings. A per-command query starts at a raw ? in a segment and ends at the next raw / or the end of the request-target; literal /, ?, &, and = inside query values must be percent-encoded. The runtime must not rely on a stock URL library's single path/query split, which would treat everything after the first ? as one opaque query string (see §4.7 and pipeline_parsing.md §6).
2. Maps the URL path to a candidate filesystem path and/or command expression. Raw path segments are split before percent-decoding; decoded / and NUL are invalid in ordinary filesystem path segments. Dot segments are normalized for filesystem lookup, and ordinary literal file serving rejects any path that escapes the configured root. Symlink escape behavior is implementation-defined; the default policy should reject symlinks that expose files outside the root for direct file serving.
3. Resolves command segments left-to-right using the command search path.
4. Uses command metadata and defaults to determine arity, input mode, parse mode, and output behavior.
5. Evaluates the rightmost input resource or request body as needed.
6. Executes commands as child processes per request.
7. Returns the resulting bytes, file, metadata, or HTTP response.

### 12.3 Command Execution

Command execution is child-process-per-request.

Commands normally see only their local arguments and local input. They do not automatically see the entire original URL or full parsed pipeline.

The default working directory for command execution is the configured root. Therefore, literal argv strings that a command interprets as relative paths are normally interpreted relative to the project root, as if the command were run from that directory. Implementations may expose a policy or future metadata extension to override the working directory.

A command may opt out of normal parsing and consume the remaining URL expression itself.

### 12.4 Command Input

Depending on metadata or defaults, a command may receive:

1. stdin bytes from the evaluated suffix,
2. filesystem paths,
3. request body bytes,
4. request metadata,
5. structured parse information,
6. URL suffix text,
7. no input.

This list describes what a command may consume through its argv, working directory, request body, and parse mode — not modes selectable through the input metadata field. In v1 the input field selects only stdin (pipeline_parsing.md §5.3): filesystem paths reach a command as literal argv strings interpreted relative to the root (§12.3), URL suffix text reaches a parse-mode raw command (§10.7), and request body bytes arrive on stdin per §10.6.

For the common pipeline case, commands receive bytes/stdin from the evaluated suffix.

If the common pipeline case has neither an input suffix nor a request body, stdin is closed and empty.

### 12.5 Command Output

A command may return:

1. raw bytes plus inferred or specified MIME type (specified via the mime metadata field; pipeline_parsing.md §5.8),
2. a full HTTP response,
3. structured metadata,
4. a generated filesystem artifact,
5. implementation-defined output.

Most commands will simply write bytes to stdout.

Commands that return full HTTP responses may set status code, headers, MIME type, redirects, cookies, and caching headers.

## 13. Security Model

The default security model is:

text local developer tool; commands run with the user’s OS permissions 

Commands may read files, write files, execute subprocesses, and make network requests to the extent permitted by the user’s operating system permissions.

### 13.1 Cross-origin Access

Cross-origin access should be disabled by default for all methods, including GET.

Cross-origin access should be easy to enable.

### 13.2 Mutating Operations

Mutating operations are controlled by HTTP method discipline and command-author responsibility.

GET must not mutate.

Commands default to methods GET and mutates false. A command that mutates must declare an appropriate non-GET method. Metadata that allows GET while declaring mutates true is invalid.

No confirmation mechanism is required by the specification for destructive operations.

Examples:

text DELETE /important.txt POST /rm/-rf/something 

The runtime is not required to prompt, sandbox, or prevent these beyond method discipline and whatever implementation policy it chooses.

### 13.3 Trust

Trust prompts, signatures, quarantine, command verification, and cloned-directory trust management are outside this specification.

A directory cloned from Git and added to env/path should be treated like adding scripts to a shell PATH: powerful and potentially dangerous.

## 14. Persistence and Sharing Model

The filesystem is the immediate source of truth.

Commands, metadata, interpreter rules, saved URL expressions, and project files are ordinary files and directories.

Git is an intended persistence and sharing mechanism, but orthogonal to the runtime contract.

The system should be friendly to Git by favoring plain text, line-oriented metadata, and explicit files. However:

1. Git is not required.
2. No source control system is required.
3. Portability across machines is frequent but not guaranteed.
4. Command directories may depend on machine-local interpreters, OS paths, environment variables, installed binaries, and permissions.

Package-like distribution of command directories is outside the core specification. If standardized later, it should be defined by a separate package/trust specification rather than by the URL parsing contract.

### 14.1 Aliases and Reuse

Reusable aliases are normally commands on the command path.

Example:

text root/bin/errors 

enables:

text /errors/logs/app.log 

There is no separate required mechanism for non-command reusable URL snippets in v1. Reusable partial expressions may be modeled as commands. Future non-command URL-fragment support, if added, must specify whether fragments are plain files, pre-parse expansions, or explicit command inputs.

### 14.2 Saved URL Expressions

A saved URL expression is just a file unless it is also on the command path and has an interpreter.

Example:

text root/saved/errors.url 

If not executable/resolved as a command:

text /saved/errors.url 

displays the file.

If placed on the command path and interpreted by suitable rules, it may execute.

## 15. Error Handling

### 15.1 Not Found

If no file/resource/command parse resolves, return:

text 404 Not Found 

### 15.2 Invalid Parse

Parsing is deterministic given the filesystem, command path, and metadata (pipeline_parsing.md §2). When command parsing begins but the URL violates client-controlled arity, query, or boundary rules, return:

text 400 Bad Request 

The response should include information about why the parse failed.

Malformed recognized metadata returns 500 Internal Server Error because it is a server-side configuration error.

### 15.3 Command Exit Status

By default, a nonzero command exit maps to:

text 400 Bad Request 

This behavior may be overridden through command metadata under env/meta.

Some commands, such as grep, may use nonzero exit codes for ordinary domain outcomes such as “no matches.” Metadata can define how those statuses map to HTTP responses.

In a multi-stage pipeline, every stage's exit status is mapped through its metadata or defaults. If any stage maps to a non-2xx HTTP status, the whole response is an error. If multiple stages fail, the first failing stage in URL order determines the HTTP status and primary diagnostic.

### 15.4 stderr

By default, stderr is not merged into the response body. The runtime may still capture stderr internally so it can be surfaced in error diagnostics (see pipeline_parsing.md §10.3); "discard" refers to the response stream, not to error reporting.

The /& token (written as a prefix on a command segment; see §8.8) merges a stage's stdout and stderr, analogous to shell |&.

Command metadata may define alternative stderr behavior through the stderr field, whose v1 values are discard (the default) and merge (pipeline_parsing.md §5.9). stderr merge is the metadata-level equivalent of a /& prefix on that stage's output boundary.

### 15.5 Interpreter Resolution Failure

If a command is found but its interpreter cannot be resolved, return:

text 500 Internal Server Error 

with diagnostic information.

### 15.6 Command-generated HTTP Errors

Commands that produce full HTTP responses may define their own status codes and error bodies.

## 16. Examples and User Workflows

### 16.1 View a File

text GET /arbitrary.txt 

Returns the raw contents of:

text root/arbitrary.txt 

### 16.2 Count a File

text GET /wc/arbitrary.txt 

Approximate shell equivalent:

sh cat arbitrary.txt | wc 

### 16.3 Query JSON and Search Output

text GET /grep/needle/jq/haystack.json 

Approximate shell equivalent (given grep has arity 1):

sh cat haystack.json | jq | grep needle 

### 16.4 Count Matching JSON Items

text GET /wc/-l/grep/needle/jq/.items%5B%5D/haystack.json 

Approximate shell equivalent (given wc, grep, and jq each have arity 1):

sh cat haystack.json | jq '.items[]' | grep needle | wc -l 

### 16.5 Use Named Arguments

text GET /grep?pattern=needle&ignore-case=true/jq?filter=.items[]/haystack.json 

Supplies command-specific named arguments. The core argv parameter is arg (pipeline_parsing.md §6.1); pattern/filter/ignore-case are interpreted by the commands themselves.

### 16.6 Write a File

sh curl -X PUT --data 'hello' http://localhost:PORT/greeting.txt 

Writes:

text root/greeting.txt 

### 16.7 Run a Mutating Command

text POST /sort/output.txt/input.txt 

Approximate shell equivalent:

sh sort input.txt > output.txt 

The redirection semantics here are command-specific (see §9.3); the core parser does not interpret a path segment as an output target.

### 16.8 Explain a URL

If an explain command exists:

text /explain/grep/needle/jq/haystack.json 

Only explain is executed. It explains the URL expression:

text /grep/needle/jq/haystack.json 

A runtime is not required to provide explain.

If a future specification standardizes an explain/debug command, it must define the conventional command name and output contract, including whether the command emits plain text, JSON, or both. Until then, explain-style commands are ordinary optional commands.

### 16.9 Define an Alias

Create a command:

text root/bin/errors 

Then use:

text /errors/logs/app.log 

The alias behavior is whatever errors implements.

## 17. Resolved Design Decisions

Many questions originally listed here are now resolved by pipeline_parsing.md or by the sections above:

- Default arity for metadata-free commands → arity 0 (pipeline_parsing.md §4).
- Syntax and semantics of /& → prefix form (pipeline_parsing.md §8 and §8.8 above).
- Command metadata grammar and normative field list → pipeline_parsing.md §5.5, §5.6.
- Default behavior for POST to ordinary directories or files → 405 unless a command governs the path (§9.3).
- Directory listing vs. index.html precedence → default file wins, fallback listing (§6.5).
- Exec interpreter-rule grammar and matching → §7.2.
- Conventional explain/debug command → optional in v1 (§16.8).
- Non-command reusable URL fragments → outside v1 (§14.1).
- Package-like command-directory distribution → outside the core specification (§14).
- Synthesized-resource discovery and scope → pipeline_parsing.md §9.5.
- PUT and DELETE target the literal filesystem path only and do not trigger command parsing (§9.2, §9.4).
- A command permitting GET also answers HEAD; OPTIONS/CORS preflight is implementation-defined in v1 (§9.5).
- The input metadata field selects only stdin in v1; multi-file commands such as diff work through arity plus root-relative argv (§10.5, §12.4).
- stderr field (discard/merge) and mime field semantics → pipeline_parsing.md §5.9 and §5.8.

## 18. Minimal Viable Implementation

Although the specification is not limited to an MVP, a minimal useful implementation could provide:

1. Local HTTP server.
2. One root directory per server instance.
3. Literal file serving for GET.
4. Basic directory behavior.
5. PUT and DELETE for ordinary files.
6. env/path as a line-oriented command search path.
7. exec as line-oriented interpreter rules.
8. Optional env/meta/<command> metadata.
9. Left-to-right command resolution.
10. Right-to-left pipeline data flow.
11. Child process per request.
12. Basic stdin/stdout command execution.
13. MIME inference for raw command output.
14. 400 for invalid command parses.
15. 404 for unresolved resources.
16. 500 for command/interpreter runtime failures.
17. Cross-origin requests disabled by default.
18. No browser extension and no special UI.

## 19. Future Extensions

Possible future extensions include:

1. Browser extension for autocomplete, previews, and command palettes.
2. Visual URL pipeline builder.
3. Saved non-command URL fragments.
4. Package format for command directories.
5. Trust/signature model for shared commands.
6. Live filesystem watching.
7. Snapshot URLs or content-addressed results.
8. Distributed execution.
9. Rich metadata schemas.
10. Integration with editor protocols.
11. Structured explain/parse output.
12. Command discovery pages.
13. Standard library of common commands.
14. Enhanced stderr/stdout routing.
15. Better affordances for request body transformation.
