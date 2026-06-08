# URL Filesystem Router Runtime Specification

## 1. Problem Statement

Programmers routinely compose shell commands, filesystem paths, pipes, aliases, scripts, and environment-driven behavior into powerful reusable workflows. Browsers and URLs provide a universal, inspectable, bookmarkable interface, but ordinary web applications usually hide composition behind application-specific UI and server-side routing.

This specification defines a runtime behavior contract for a local, browser-accessible environment where URLs map transparently to a project directory and where URL path segments can compose commands, files, arguments, and pipelines in a shell-like way.

The core idea is that a URL should be almost as readable and reusable as a shell pipeline. For example:

text http://local/grep/needle/jq/haystack.json 

corresponds approximately to:

sh jq haystack.json | grep needle 

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

maps approximately to:

sh jq haystack.json | grep needle 

Command resolution proceeds left-to-right, even though data flow is generally right-to-left.

### 4.6 Argument Segment

Some URL path segments are literal command arguments rather than files or commands.

Example:

text /grep/needle/file.txt 

Given grep with arity 1, needle is a literal argument.

### 4.7 Per-command Query String

A command segment may carry a query string to supply named arguments or disambiguate parsing.

Example:

text /grep?pattern=needle&ignore-case=true/jq?filter=.items[]/haystack.json 

Per-command query strings are explicitly supported.

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

If a segment appears in command position and a command by that name exists on the command path, the command takes precedence over an ordinary file of the same name.

Example:

text /wc/foo.txt 

If wc exists on the command path, this executes approximately:

sh wc foo.txt 

even if root/wc also exists as a regular file.

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

Implementations may synthesize responses for missing paths through implementation-defined directory or resource behavior.

### 6.5 Directories

Directories may support any of the following:

1. Directory listing.
2. index.html or analogous default file if present.
3. Implementation-defined behavior.

The specification does not require one exclusive directory behavior.

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

The file is line-oriented with shell-like quoting.

Approximate format:

text <pattern> <interpreter> [args...] 

Example:

text for_this_command_only sh *.py /usr/bin/python3 

Interpreter rules determine how command files are executed when they are not directly executable, lack a shebang, or require an external interpreter.

### 7.3 Command Metadata

If present, command metadata may be stored under:

text root/env/meta/<command> 

Example:

text root/env/meta/jq 

Metadata is plain line-oriented text. No metadata is required. Defaults apply for unspecified fields.

Possible metadata fields include:

text arity input-mode output-mode methods mime mutates parse-mode exit-status-mode stderr-mode 

Exact field syntax may be implementation-defined, but the format should remain readable and Git-friendly.

## 8. URL Grammar and Examples

### 8.1 Basic Resource

text /arbitrary.txt 

Returns:

text root/arbitrary.txt 

### 8.2 Unary Command Over File

text /wc/arbitrary.txt 

Approximate shell equivalent:

sh wc arbitrary.txt 

### 8.3 Pipeline

text /grep/needle/jq/haystack.json 

Approximate shell equivalent:

sh jq haystack.json | grep needle 

### 8.4 Longer Pipeline

text /wc/-l/grep/needle/jq/.items%5B%5D/cat/haystack.json 

Approximate shell equivalent:

sh cat haystack.json | jq '.items[]' | grep needle | wc -l 

Flags are ordinary argument segments.

### 8.5 Per-command Query Strings

text /grep?pattern=needle&ignore-case=true/jq?filter=.items[]/haystack.json 

This supplies named arguments to individual command segments.

### 8.6 Argument Collision With Command Name

Given grep with arity 1:

text /grep/jq/haystack.txt 

means:

sh grep jq haystack.txt 

Here jq is a literal pattern argument, not a command, because grep consumes one argument before its input suffix.

### 8.7 Ambiguous Cases

Ambiguous cases should use query strings. Defining clearer commands is often preferable.

For example, instead of relying on an ambiguous interpretation of:

text /grep/jq/haystack.txt 

a user could define:

text /find_jq/haystack.txt 

as a command.

### 8.8 Standard Error Pipeline Marker

The separator /& may be used instead of / to combine stdout and stderr, analogous to shell |&.

Example form:

text /grep/needle/& noisy-command/input.txt 

The exact URL grammar for /& should preserve normal URL parsing constraints while allowing a pipeline stage to receive combined stdout and stderr.

## 9. Resource Lifecycle

### 9.1 GET

GET must not mutate local state.

Examples:

text GET /file.txt GET /wc/file.txt GET /grep/needle/file.txt 

These may read files, execute commands, and compute output, but must not intentionally modify local state.

### 9.2 PUT

PUT may create or replace a file resource.

Example:

text PUT /file.txt 

writes the request body to:

text root/file.txt 

where supported.

### 9.3 POST

POST may trigger command-specific behavior or write results through command-defined semantics.

Example:

text POST /sort/output.txt/input.txt 

means approximately:

sh sort input.txt > output.txt 

### 9.4 DELETE

DELETE may delete a filesystem resource where supported.

Example:

text DELETE /file.txt 

deletes:

text root/file.txt 

### 9.5 Other HTTP Methods

Implementations may support additional standard HTTP methods such as:

text HEAD PATCH OPTIONS 

Normal HTTP semantics should be preserved.

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

Data flow evaluates:

sh jq haystack.json | grep needle 

### 10.2 Arity

Command arity determines where command arguments end and the input suffix begins.

For example, if grep has arity 1:

text /grep/needle/jq/haystack.json 

means:

sh jq haystack.json | grep needle 

Arity may be supplied through metadata. If missing, default shell-like behavior applies.

### 10.3 Next Known Command Boundary

The parser may treat the next known command on the command path as a pipeline boundary when compatible with the current command’s arity.

Example:

text /foo/bar/baz/file.txt 

If foo and baz are commands and bar is an argument to foo, this may parse as:

sh baz file.txt | foo bar 

### 10.4 Ambiguity

If a URL has multiple possible parses and neither metadata nor query strings resolve the ambiguity, the default response is:

text 400 Bad Request 

The response should include information about the ambiguity.

### 10.5 Commands Consuming Multiple Resources

Commands are not restricted to unary stream transforms. A command may consume multiple resources.

Example:

text /diff/a.txt/b.txt 

may mean:

sh diff a.txt b.txt 

if diff is defined with suitable arity/input behavior.

### 10.6 Request Body Input

For methods such as POST and PUT, the HTTP request body may become stdin for the rightmost command or input position, subject to command metadata or defaults.

Example:

text POST /grep/needle/sort 

with body input is approximately:

sh sort | grep needle 

where sort receives the request body on stdin.

Users may define commands specifically for capturing, decoding, or transforming request bodies.

### 10.7 Commands That Consume URL Expressions

Some commands may operate on a URL expression rather than executing the suffix.

Example:

text /explain/grep/needle/jq/haystack.json 

Only explain is executed. It receives or consumes the remaining URL expression:

text /grep/needle/jq/haystack.json 

and explains it.

grep and jq are not executed in this case.

Commands may opt out of normal URL parsing and handle the remaining URL themselves when the command author requires that behavior.

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

1. Parses the URL using ordinary URL rules.
2. Maps the URL path to a candidate filesystem path and/or command expression.
3. Resolves command segments left-to-right using the command search path.
4. Uses command metadata and defaults to determine arity, input mode, parse mode, and output behavior.
5. Evaluates the rightmost input resource or request body as needed.
6. Executes commands as child processes per request.
7. Returns the resulting bytes, file, metadata, or HTTP response.

### 12.3 Command Execution

Command execution is child-process-per-request.

Commands normally see only their local arguments and local input. They do not automatically see the entire original URL or full parsed pipeline.

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

For the common pipeline case, commands receive bytes/stdin from the evaluated suffix.

### 12.5 Command Output

A command may return:

1. raw bytes plus inferred or specified MIME type,
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

### 14.1 Aliases and Reuse

Reusable aliases are normally commands on the command path.

Example:

text root/bin/errors 

enables:

text /errors/logs/app.log 

There is no separate required mechanism for non-command reusable URL snippets. Reusable partial expressions may be modeled as commands.

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

### 15.2 Ambiguous Parse

If multiple parses are possible and ambiguity is not resolved by metadata or query strings, return:

text 400 Bad Request 

The response should include information about the ambiguity.

### 15.3 Command Exit Status

By default, a nonzero command exit maps to:

text 400 Bad Request 

This behavior may be overridden through command metadata under env/meta.

Some commands, such as grep, may use nonzero exit codes for ordinary domain outcomes such as “no matches.” Metadata can define how those statuses map to HTTP responses.

### 15.4 stderr

By default, stderr is discarded.

The /& separator may be used instead of / to combine stdout and stderr, analogous to shell |&.

Command metadata may define alternative stderr behavior.

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

sh wc arbitrary.txt 

### 16.3 Query JSON and Search Output

text GET /grep/needle/jq/haystack.json 

Approximate shell equivalent:

sh jq haystack.json | grep needle 

### 16.4 Count Matching JSON Items

text GET /wc/-l/grep/needle/jq/.items%5B%5D/cat/haystack.json 

Approximate shell equivalent:

sh cat haystack.json | jq '.items[]' | grep needle | wc -l 

### 16.5 Use Named Arguments

text GET /grep?pattern=needle&ignore-case=true/jq?filter=.items[]/haystack.json 

Supplies command-specific named arguments.

### 16.6 Write a File

sh curl -X PUT --data 'hello' http://localhost:PORT/greeting.txt 

Writes:

text root/greeting.txt 

where supported.

### 16.7 Run a Mutating Command

text POST /sort/output.txt/input.txt 

Approximate shell equivalent:

sh sort input.txt > output.txt 

### 16.8 Explain a URL

If an explain command exists:

text /explain/grep/needle/jq/haystack.json 

Only explain is executed. It explains the URL expression:

text /grep/needle/jq/haystack.json 

A runtime is not required to provide explain.

### 16.9 Define an Alias

Create a command:

text root/bin/errors 

Then use:

text /errors/logs/app.log 

The alias behavior is whatever errors implements.

## 17. Open Questions

1. Exact line-oriented syntax for command metadata.
2. Exact line-oriented syntax for exec quoting and matching.
3. Exact default arity rules for metadata-free commands.
4. Exact default behavior for POST to ordinary directories or files.
5. Exact syntax and semantics of /& within valid URL grammar.
6. Whether directory listing or index.html should take precedence when both are possible.
7. How synthesized responses should be advertised or discovered.
8. Whether there should be a conventional command for parse/explain/debug output.
9. Whether a future spec should define reusable non-command URL fragments.
10. Whether a future spec should define package-like distribution for command directories.

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
14. 400 for ambiguous parses.
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