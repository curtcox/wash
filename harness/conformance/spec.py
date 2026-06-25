"""Spec clause registry — stable ids mapped to source sections and tiers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

SPEC_VERSION = "1"

Tier = Literal["MUST", "SHOULD", "optional"]


@dataclass(frozen=True, slots=True)
class Clause:
    id: str
    source: str
    tier: Tier
    requirement: str


CLAUSE_REGISTRY: dict[str, Clause] = {
    # runtime §4
    "RT-4.2-root-valid": Clause(
        "RT-4.2-root-valid", "runtime §4.2", "MUST", "empty root directory is valid"
    ),
    # runtime §6
    "RT-6.1-literal-file": Clause(
        "RT-6.1-literal-file",
        "runtime §6.1",
        "MUST",
        "plain URL path maps literally to root file",
    ),
    "RT-6.2-precedence": Clause(
        "RT-6.2-precedence",
        "runtime §6.2",
        "MUST",
        "exact file > command > synthesized > 404",
    ),
    "RT-6.3-direct-cmd-file": Clause(
        "RT-6.3-direct-cmd-file",
        "runtime §6.3",
        "MUST",
        "concrete filesystem path serves command file bytes",
    ),
    "RT-6.4-missing-path": Clause(
        "RT-6.4-missing-path",
        "runtime §6.4",
        "MUST",
        "no valid parse and no resource resolves to 404 Not Found",
    ),
    "RT-6.5-dir-index": Clause(
        "RT-6.5-dir-index",
        "runtime §6.5",
        "MUST",
        "index file takes precedence over directory listing",
    ),
    "RT-6.1-mime-fallback": Clause(
        "RT-6.1-mime-fallback",
        "runtime §6.1",
        "MUST",
        "literal file Content-Type from built-in fallback table when env/mime absent",
    ),
    # runtime §7
    "RT-7.1-command-path": Clause(
        "RT-7.1-command-path",
        "runtime §7.1",
        "MUST",
        "command search path from env/path line-oriented entries",
    ),
    "RT-7.2-exec-rules": Clause(
        "RT-7.2-exec-rules",
        "runtime §7.2",
        "MUST",
        "interpreter rules first-match-wins; malformed rule → 500",
    ),
    "RT-7.4-env-mime": Clause(
        "RT-7.4-env-mime",
        "runtime §7.4",
        "MUST",
        "env/mime suffix and default entries set literal-file Content-Type",
    ),
    "RT-7.4-env-mime-malformed": Clause(
        "RT-7.4-env-mime-malformed",
        "runtime §7.4",
        "MUST",
        "malformed env/mime → 500 for responses resolved through it",
    ),
    "RT-7.5-env-index": Clause(
        "RT-7.5-env-index",
        "runtime §7.5",
        "MUST",
        "env/index names directory index candidates, first existing wins",
    ),
    "RT-7.6-env-listing": Clause(
        "RT-7.6-env-listing",
        "runtime §7.6",
        "MUST",
        "env/listing off disables listings; index-less directory → 404",
    ),
    # runtime §9 lifecycle
    "RT-9.1-get-no-mutate": Clause(
        "RT-9.1-get-no-mutate",
        "runtime §9.1",
        "MUST",
        "GET must not mutate local state",
    ),
    "RT-9.2-put-literal": Clause(
        "RT-9.2-put-literal",
        "runtime §9.2",
        "MUST",
        "PUT targets literal filesystem path without command parsing",
    ),
    "RT-9.3-post-plain-405": Clause(
        "RT-9.3-post-plain-405",
        "runtime §9.3",
        "MUST",
        "POST to plain file/directory without governing command → 405",
    ),
    "RT-9.4-delete-literal": Clause(
        "RT-9.4-delete-literal",
        "runtime §9.4",
        "MUST",
        "DELETE targets literal filesystem path without command parsing",
    ),
    "RT-9.5-head-from-get": Clause(
        "RT-9.5-head-from-get",
        "runtime §9.5",
        "MUST",
        "GET permitted implies HEAD answered with body omitted",
    ),
    "RT-9.5-methods-405": Clause(
        "RT-9.5-methods-405",
        "runtime §9.5",
        "MUST",
        "request method not in methods metadata → 405",
    ),
    "RT-9.5-head-explicit": Clause(
        "RT-9.5-head-explicit",
        "runtime §9.5 / audit R8",
        "optional",
        "HEAD for explicit methods list with GET but no HEAD (not asserted)",
    ),
    # runtime §10 composition
    "RT-10.4-invalid-parse": Clause(
        "RT-10.4-invalid-parse",
        "runtime §10.4",
        "MUST",
        "client-controlled parse errors return 400 Bad Request",
    ),
    "RT-10.5-multi-resource": Clause(
        "RT-10.5-multi-resource",
        "runtime §10.5",
        "MUST",
        "commands may consume multiple root-relative resources via arity",
    ),
    "RT-10.6-request-body": Clause(
        "RT-10.6-request-body",
        "runtime §10.6",
        "MUST",
        "request body feeds rightmost stage stdin; suffix wins over body",
    ),
    "RT-10.7-url-expr": Clause(
        "RT-10.7-url-expr",
        "runtime §10.7",
        "MUST",
        "parse-mode raw command consumes remaining URL expression and stops parsing",
    ),
    # runtime §12 architecture
    "RT-12.2-request-handling": Clause(
        "RT-12.2-request-handling",
        "runtime §12.2",
        "MUST",
        "runtime parses raw request-target without library normalization",
    ),
    "RT-12.2-root-escape": Clause(
        "RT-12.2-root-escape",
        "runtime §12.2 / pipeline §9.1",
        "MUST",
        "literal file serving rejects paths escaping configured root",
    ),
    "RT-12.3-cwd-root": Clause(
        "RT-12.3-cwd-root",
        "runtime §12.3",
        "MUST",
        "command working directory defaults to root for root-relative argv",
    ),
    # runtime §13 security
    "RT-13.1-cors-default": Clause(
        "RT-13.1-cors-default",
        "runtime §13.1",
        "SHOULD",
        "cross-origin access disabled by default (no Access-Control-Allow-Origin)",
    ),
    "RT-13.2-mutating-methods": Clause(
        "RT-13.2-mutating-methods",
        "runtime §13.2",
        "MUST",
        "mutating operations require explicit method/metadata opt-in",
    ),
    # runtime §15 error handling
    "RT-15.1-not-found": Clause(
        "RT-15.1-not-found",
        "runtime §15.1",
        "MUST",
        "no resource and no command parse → 404",
    ),
    "RT-15.2-invalid-parse": Clause(
        "RT-15.2-invalid-parse",
        "runtime §15.2",
        "MUST",
        "invalid client-controlled parse → 400 with diagnostic information",
    ),
    "RT-15.3-exit-status": Clause(
        "RT-15.3-exit-status",
        "runtime §15.3",
        "MUST",
        "nonzero command exit mapped to error HTTP status with diagnostics",
    ),
    "RT-15.5-interpreter-fail": Clause(
        "RT-15.5-interpreter-fail",
        "runtime §15.5",
        "MUST",
        "unresolved interpreter → 500 Internal Server Error",
    ),
    "RT-15.6-cmd-http-errors": Clause(
        "RT-15.6-cmd-http-errors",
        "runtime §15.6",
        "MUST",
        "command-generated HTTP errors surfaced per implementation contract",
    ),
    # audit R7
    "RT-R7-case": Clause(
        "RT-R7-case",
        "audit R7",
        "optional",
        "case sensitivity behavior consistent with declared capability",
    ),
    # runtime §6.6 name resolution
    "RT-6.6-resolve-scope": Clause(
        "RT-6.6-resolve-scope",
        "runtime §6.6.2",
        "MUST",
        "name with no literal child resolves via c file to its target path",
    ),
    "RT-6.6-literal-precedence": Clause(
        "RT-6.6-literal-precedence",
        "runtime §6.6.2",
        "MUST",
        "literal child shadows a same-named c entry",
    ),
    "RT-6.6-nearest-wins": Clause(
        "RT-6.6-nearest-wins",
        "runtime §6.6.2",
        "MUST",
        "nearest (deepest) c definition shadows an ancestor definition of the same name",
    ),
    "RT-6.6-jump-scope": Clause(
        "RT-6.6-jump-scope",
        "runtime §6.6.2",
        "MUST",
        "resolved name jumps the walk to its target and rebuilds scope from the target",
    ),
    "RT-6.6-chain": Clause(
        "RT-6.6-chain",
        "runtime §6.6.3",
        "MUST",
        "a target that is itself a name resolves iteratively to a fixpoint",
    ),
    "RT-6.6-loop-bound": Clause(
        "RT-6.6-loop-bound",
        "runtime §6.6.3",
        "MUST",
        "name+symlink hops share one depth budget; overflow or cycle → 508",
    ),
    "RT-6.6-dangling": Clause(
        "RT-6.6-dangling",
        "runtime §6.6.2",
        "MUST",
        "name matching no entry or with only dangling targets → 404",
    ),
    "RT-6.6-escape-policy": Clause(
        "RT-6.6-escape-policy",
        "runtime §6.6.4",
        "MUST",
        "name/symlink target outside root rejected by default escape policy → 403",
    ),
    "RT-6.6-c-graceful": Clause(
        "RT-6.6-c-graceful",
        "runtime §6.6.1",
        "MUST",
        "absent/empty/malformed c file is ignored at runtime; never 500",
    ),
    "RT-6.6-provenance": Clause(
        "RT-6.6-provenance",
        "runtime §6.6.5",
        "optional",
        "X-WebShell-Resolved-Path reports the final resolved path through name/symlink hops",
    ),
    # pipeline §2
    "PP-2-parse-algo": Clause(
        "PP-2-parse-algo",
        "pipeline §2",
        "MUST",
        "normative left-to-right parse algorithm and precedence ladder",
    ),
    # pipeline §4
    "PP-4-arity0-default": Clause(
        "PP-4-arity0-default",
        "pipeline §4",
        "MUST",
        "metadata-free command has arity 0 and closed-empty stdin when no suffix/body",
    ),
    "PP-4-implied-cat": Clause(
        "PP-4-implied-cat",
        "pipeline §4",
        "MUST",
        "rightmost suffix fed via implied cat primitive",
    ),
    "PP-4-implied-cat-nested": Clause(
        "PP-4-implied-cat-nested",
        "pipeline §4",
        "MUST",
        "metadata-free command accepts a multi-segment implied-cat suffix when "
        "the whole suffix resolves to an existing filesystem path",
    ),
    # pipeline §5 metadata
    "PP-5.1-arity-n": Clause(
        "PP-5.1-arity-n",
        "pipeline §5.1",
        "MUST",
        "arity N consumes N path segments as argv",
    ),
    "PP-5.2-arity-star": Clause(
        "PP-5.2-arity-star",
        "pipeline §5.2",
        "MUST",
        "arity * consumes rest of URL as argv leaving no input suffix",
    ),
    "PP-5.3-input-stdout": Clause(
        "PP-5.3-input-stdout",
        "pipeline §5.3",
        "MUST",
        "v1 input stdin and output stdout modes; reserved modes → 500",
    ),
    "PP-5.4-exit-map": Clause(
        "PP-5.4-exit-map",
        "pipeline §5.4",
        "MUST",
        "exit→status mapping with pipefail aggregation (first in URL order wins)",
    ),
    "PP-5.5-malformed-500": Clause(
        "PP-5.5-malformed-500",
        "pipeline §5.5",
        "MUST",
        "malformed recognized metadata field → 500",
    ),
    "PP-5.7-parse-raw": Clause(
        "PP-5.7-parse-raw",
        "pipeline §5.7",
        "MUST",
        "parse-mode raw takes encoded suffix and stops parsing",
    ),
    "PP-5.7-method-all-stages": Clause(
        "PP-5.7-method-all-stages",
        "pipeline §5.7",
        "MUST",
        "every pipeline stage must permit the request method",
    ),
    "PP-5.7-mutates-get-invalid": Clause(
        "PP-5.7-mutates-get-invalid",
        "pipeline §5.7",
        "MUST",
        "GET permitted with mutates true is invalid metadata → 500",
    ),
    "PP-5.8-mime-final": Clause(
        "PP-5.8-mime-final",
        "pipeline §5.8",
        "MUST",
        "mime sets final-stage Content-Type; ignored mid-pipeline",
    ),
    "PP-5.9-stderr-field": Clause(
        "PP-5.9-stderr-field",
        "pipeline §5.9",
        "MUST",
        "stderr discard/merge semantics for response body",
    ),
    # pipeline §6 query
    "PP-6-query-delim": Clause(
        "PP-6-query-delim",
        "pipeline §6",
        "MUST",
        "per-command query ends at next raw /",
    ),
    "PP-6.1-core-arg": Clause(
        "PP-6.1-core-arg",
        "pipeline §6.1",
        "MUST",
        "arg is the only core query parameter",
    ),
    "PP-6.2-query-disables-arity": Clause(
        "PP-6.2-query-disables-arity",
        "pipeline §6.2",
        "MUST",
        "query argv disables metadata path arity for that command",
    ),
    "PP-6.3-arg-noncmd-400": Clause(
        "PP-6.3-arg-noncmd-400",
        "pipeline §6.3",
        "MUST",
        "core arg on non-command segment → 400",
    ),
    # pipeline §7 boundaries
    "PP-7-mid-noncmd-400": Clause(
        "PP-7-mid-noncmd-400",
        "pipeline §7",
        "MUST",
        "non-command middle segment with metadata-free commands → 400",
    ),
    # pipeline §8 stderr prefix
    "PP-8-stderr-prefix": Clause(
        "PP-8-stderr-prefix",
        "pipeline §8",
        "MUST",
        "/& prefix merges exactly one pipeline boundary",
    ),
    "PP-8.1-amp-name": Clause(
        "PP-8.1-amp-name",
        "pipeline §8.1",
        "MUST",
        "leading & stripped pre-decode; %26 is a name character",
    ),
    # pipeline §9 precedence
    "PP-9.1-trailing-q": Clause(
        "PP-9.1-trailing-q",
        "pipeline §9.1",
        "MUST",
        "trailing ? in final segment is resource query before command reinterpretation",
    ),
    "PP-9.1-slash-collapse": Clause(
        "PP-9.1-slash-collapse",
        "pipeline §9.1",
        "MUST",
        "leading/trailing/repeated / collapse; trailing slash insignificant",
    ),
    "PP-9.1-invalid-segment": Clause(
        "PP-9.1-invalid-segment",
        "pipeline §9.1",
        "MUST",
        "decoded / and NUL invalid in filesystem lookup segments",
    ),
    "PP-9.2-no-cmd-in-dir": Clause(
        "PP-9.2-no-cmd-in-dir",
        "pipeline §9.2",
        "MUST",
        "no command lookup after directory traversal",
    ),
    "PP-9.3-args-before-suffix": Clause(
        "PP-9.3-args-before-suffix",
        "pipeline §9.3",
        "MUST",
        "metadata arity path arguments consumed before input suffix",
    ),
    "PP-9.4-dir-suffix": Clause(
        "PP-9.4-dir-suffix",
        "pipeline §9.4",
        "MUST",
        "directory suffix evaluated through implied cat not direct HTTP directory behavior",
    ),
    "PP-9.5-synth": Clause(
        "PP-9.5-synth",
        "pipeline §9.5",
        "optional",
        "synthesized resource behavior consistent with declaration",
    ),
    "PP-9.5-parse-terminal": Clause(
        "PP-9.5-parse-terminal",
        "pipeline §9.5",
        "MUST",
        "started command parse failure is terminal; no synthesized fallback",
    ),
    # pipeline §10 errors
    "PP-10.1-400-diagnostics": Clause(
        "PP-10.1-400-diagnostics",
        "pipeline §10.1",
        "SHOULD",
        "400 responses include helpful parse failure diagnostics",
    ),
    "PP-10.2-404": Clause(
        "PP-10.2-404",
        "pipeline §10.2",
        "MUST",
        "404 when no filesystem resource, no synth, no command parse can start",
    ),
    "PP-10.3-exit-diagnostics": Clause(
        "PP-10.3-exit-diagnostics",
        "pipeline §10.3",
        "SHOULD",
        "nonzero exit responses include command/exit/pipeline diagnostics",
    ),
    "PP-10.4-500": Clause(
        "PP-10.4-500",
        "pipeline §10.4",
        "MUST",
        "malformed metadata and server-side failures return 500",
    ),
    "PP-10.5-error-format": Clause(
        "PP-10.5-error-format",
        "pipeline §10.5",
        "SHOULD",
        "error responses content-negotiated via Accept header",
    ),
    # pipeline §11 optional headers
    "PP-11-headers": Clause(
        "PP-11-headers",
        "pipeline §11",
        "optional",
        "X-WebShell-* execution metadata headers when declared",
    ),
    # pipeline §13 invalid examples
    "PP-13.1-mf-path-args": Clause(
        "PP-13.1-mf-path-args",
        "pipeline §13.1",
        "MUST",
        "metadata-free path arguments are invalid → 400",
    ),
    "PP-13.2-mf-multi-path-args": Clause(
        "PP-13.2-mf-multi-path-args",
        "pipeline §13.2",
        "MUST",
        "metadata-free multi-command path args invalid → 400",
    ),
}


def get_clause(clause_id: str) -> Clause | None:
    return CLAUSE_REGISTRY.get(clause_id)


def must_clauses() -> list[Clause]:
    return [c for c in CLAUSE_REGISTRY.values() if c.tier == "MUST"]


def resolve_spec_commit(repo_root: str | None = None) -> str:
    """Resolve specs/ git commit for reproducible reporting."""
    import subprocess
    from pathlib import Path

    root = Path(repo_root) if repo_root else _find_repo_root()
    if root is None:
        return "unknown"
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain", "--", "specs/"],
            cwd=root,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if dirty:
            commit += "+dirty"
        return commit
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def spec_label(repo_root: str | None = None) -> str:
    commit = resolve_spec_commit(repo_root)
    return f"{SPEC_VERSION}@{commit}"


def _find_repo_root() -> Path | None:
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "specs" / "runtime.md").is_file():
            return parent
    return None
