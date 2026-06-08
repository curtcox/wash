# Remaining Spec Issues

Last updated: 2026-06-08

This document consolidates the unresolved issues that remain after the earlier audit passes. The
historical audit files have been removed; active normative behavior lives in `runtime.md` and
`pipeline_parsing.md`.

## 1. Exec Interpreter Rule Syntax

Severity: medium

`runtime.md` defines `root/exec` as a line-oriented interpreter rule file with "shell-like quoting"
and an approximate format:

```text
<pattern> <interpreter> [args...]
```

The exact grammar is still open: pattern syntax, matching order, quoting/escaping, comments,
duplicate handling, malformed-rule behavior, and whether rules can be command-specific or only
glob/path based.

Proposed resolution: define an `exec` grammar parallel to command metadata: one rule per line,
`#` line comments, ASCII whitespace tokenization, explicit quoting rules or no quoting in v1,
first-match-wins or last-match-wins, and malformed recognized rules as 500.

## 2. Conventional Parse/Explain/Debug Command

Severity: low/medium

The specs allow commands such as `explain` and support `parse-mode raw`, but do not decide whether
there should be a conventional command name or output format for parse/debug information.

Proposed resolution: keep `explain` optional in v1, but reserve a conventional output contract for a
future extension. If standardized, define whether it emits plain text, JSON, or both.

## 3. Reusable Non-command URL Fragments

Severity: low

`runtime.md` currently models reusable aliases as commands on the command path. Non-command reusable
URL fragments are left as a possible future feature.

Proposed resolution: keep out of v1. If added later, specify whether fragments are plain files,
expanded before parsing, or explicit command inputs.

## 4. Package-like Distribution for Command Directories

Severity: low

The specs intentionally exclude a package manager and do not define package metadata, dependency
resolution, trust, or installation flows for command directories.

Proposed resolution: keep out of core. If standardized later, do it as a separate package/trust
spec rather than as part of URL parsing.

## 5. Synthesized Resource Discovery and Scope

Severity: medium

The specs define synthesized resources and precedence, and allow an optional diagnostic header when
a synthesized resource loses to a command parse. They do not define broader discovery or the scope
of synthesized resources after partial directory traversal.

Open cases:

```text
/docs/index
/docs/grep/needle/file.txt
```

If `/docs` is a real directory but `/docs/index` is not a real file, it is unclear whether a
synthesized `/docs/index` may resolve. Likewise, when command lookup is disabled after ordinary
directory traversal, the specs do not say whether synthesized resources are also disabled there.

Proposed resolution: define synthesized resources as either global, directory-local, or explicitly
implementation-defined after partial directory traversal. Also decide whether discovery should be
limited to optional headers or include a conventional command/resource.

## 6. Input and Output Modes Beyond stdin/stdout

Severity: medium

`pipeline_parsing.md` names `input file`, `input none`, and `output file`, but leaves the complete
set and semantics implementation-defined. `arity *` also says it consumes the rest of the URL as
argv "unless another explicit rule overrides this behavior," but no override mechanism is defined.

Proposed resolution: keep v1 normative behavior limited to `input stdin` and `output stdout`.
Treat other modes as reserved until specified, and remove or define the `arity *` override language.

## 7. Directory Input Suffix Semantics

Severity: medium

The addendum allows a directory to appear as the suffix supplied through implied `cat`, while the
core runtime also defines direct directory behavior such as default files and directory listings.

For:

```text
/wc/docs
```

the intended behavior appears to be an OS-level attempt to read `docs` through the implied-cat
operation, which may fail naturally. The specs should say explicitly that direct HTTP directory
behavior (`index.html` or listing) does not apply when the directory is used as a pipeline input
suffix.

Proposed resolution: implied-cat suffix evaluation uses filesystem file bytes only. A directory
suffix is passed to the implied cat operation as a filesystem path and may fail naturally; direct
directory listing/default-file behavior applies only to direct directory resource requests.

## 8. Relative Path Interpretation for Literal Argv

Severity: medium

The specs now say argument segments are literal strings and are not resolved to file contents by the
runtime. Some commands, such as `diff`, may still treat argv strings as paths and open them.

The command execution environment is not precise enough to tell implementers whether relative argv
paths are interpreted relative to the root, the command file's directory, the server process working
directory, or something command-specific.

Proposed resolution: set the default command working directory to the configured root, so literal
path argv such as `a.txt` behaves like a shell command run from the project root. Allow metadata or
implementation policy to override this later if needed.

## 9. Intermediaries and URL Fragments

Severity: low

The multi-`?` per-command query design assumes the runtime receives the raw request-target. Browsers
and curl preserve the target for direct local connections, but proxies, gateways, and other
intermediaries may normalize, reject, or rewrite unusual request-targets. URL fragments (`#...`) are
never transmitted to the server.

Proposed resolution: document the assumption that v1 targets direct local runtime connections, and
state explicitly that URL fragments cannot participate in pipeline syntax.

