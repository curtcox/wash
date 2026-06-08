# Spec Audit: Ambiguities, Inconsistencies, and Open Questions

> Historical note: this audit records the initial reconciliation pass. The active normative rules are
> in `runtime.md` and `pipeline_parsing.md`; follow-up decisions from 2026-06-08 are tracked in
> `followup_audit.md`. Items below may describe issues that have since been resolved in the active
> specs.

Audit date: 2026-06-08
Documents reviewed:
- `specs/runtime.md` — *URL Filesystem Router Runtime Specification* (core spec)
- `specs/pipeline_parsing.md` — *Addendum: URL Pipeline Parsing and Metadata-Free Command Arity*

> **Author decisions (2026-06-08).** Four blocking questions were resolved:
> - **A (input model):** implied `cat` to stdin is the single normative model.
> - **C (boundary inference):** drop runtime §10.3; arity alone splits args/boundaries.
> - **D (metadata field names):** short forms (`input`, `output`, `exit`, `stderr`) are canonical.
> - **E (query syntax):** the multi-`?` form is accepted as valid; see item E for the implementation note.

This document records contradictions **between** the two specs, contradictions **within** a
single spec, and genuine ambiguities. Each item cites the relevant sections, states the problem,
and proposes a resolution. The most consequential items are surfaced as direct questions at the end.

Throughout, "runtime" = `runtime.md`, "addendum" = `pipeline_parsing.md`.

---

## A. The central inconsistency: file-as-argument vs. implied-`cat` to stdin

**Severity: high (forks the execution model).**

The two documents disagree on how the rightmost file (the "input suffix") reaches a command.

The runtime consistently shows the file passed as a **direct argument** to the adjacent command:

| Section | URL | Shown equivalent |
|---|---|---|
| runtime §4.5 / §8.3 / §16.3 | `/grep/needle/jq/haystack.json` | `jq haystack.json \| grep needle` |
| runtime §8.2 / §16.2 | `/wc/arbitrary.txt` | `wc arbitrary.txt` |
| runtime §6.2 | `/wc/foo.txt` | `wc foo.txt` |
| runtime §10.5 | `/diff/a.txt/b.txt` | `diff a.txt b.txt` |

The addendum consistently inserts an **implied `cat`**, feeding the file via stdin:

| Section | URL | Shown equivalent |
|---|---|---|
| addendum §4 / §12.1 | `/a/b/c.txt` (a metadata-free) | `cat b/c.txt \| a` |
| addendum §9.4 | `/wc/docs` | `cat docs \| wc` |
| addendum §12.3 | `/grep?arg=needle/jq?arg=.items[]/haystack.json` | `cat haystack.json \| jq '.items[]' \| grep needle` |

These are **not** approximations of the same thing. `wc arbitrary.txt` makes `arbitrary.txt`
an argv element (wc prints the filename); `cat arbitrary.txt | wc` feeds bytes on stdin (no
filename). For `jq`, `jq haystack.json` vs `cat haystack.json | jq` differ in argv and in whether
jq opens the file itself. The runtime softens every example with "approximate shell equivalent,"
but the difference is semantic, not cosmetic.

Note the runtime's own §8.4/§16.4 example *does* use an explicit `cat` command in the URL
(`/wc/-l/grep/needle/jq/.items[]/cat/haystack.json` → `cat haystack.json | jq … | wc -l`),
implying `cat` is something the author writes explicitly — which contradicts the addendum's
*implied* `cat`.

**Resolution (decided — implied `cat`):** The implied-`cat` model is the single normative rule:
the rightmost non-command suffix is always supplied via an implied `cat` to the leftmost command
of the suffix's downstream stage, never as a positional argument. **Action:** rewrite all runtime
examples (§4.5, §6.2, §8.2, §8.3, §10.5, §16.2, §16.3) to match
(e.g. `cat haystack.json | jq '.items[]' | grep needle`). The genuine "command wants the path /
multiple files as arguments" case (e.g. `diff a.txt b.txt`) must be expressed explicitly via
metadata (`arity`, and `input` mode) rather than as a default — see item J.

---

## B. Default arity for metadata-free commands

**Severity: high.**

- Runtime §10.2: "Arity may be supplied through metadata. If missing, **default shell-like
  behavior applies**." Runtime §17 lists "Exact default arity rules for metadata-free commands"
  as an **open question**.
- Addendum §4 resolves it definitively: a metadata-free command has **arity 0, input stdin**.

The addendum answers the runtime's open question, which is good — but it invalidates the runtime's
headline examples. `/grep/needle/jq/haystack.json` (runtime §8.3, §16.3) requires `grep` to have
arity 1. Under the addendum, metadata-free `grep` has arity 0, so `needle` is not consumed as an
argument and the URL is **400 Bad Request** (cf. addendum §13.1, §13.2). The runtime never states
that its examples assume metadata is present.

**Proposed resolution:** Keep arity 0 as the metadata-free default (per addendum). Update runtime
§17 to remove the open question and reference the addendum. Annotate every runtime example that
relies on arity ≥ 1 with an explicit note that `grep`/`wc`/etc. have `arity 1` metadata, or rewrite
them in the metadata-free `?arg=` form so they work out of the box.

---

## C. "Next known command boundary" inference (runtime §10.3) directly contradicts addendum §7

**Severity: high.**

Same URL, opposite outcomes:

- Runtime §10.3: `/foo/bar/baz/file.txt` — "If foo and baz are commands and bar is an argument to
  foo, this **may parse as** `baz file.txt | foo bar`."
- Addendum §7: `/foo/bar/baz/file.txt` — "If foo and baz are commands, bar is not, and no metadata
  exists, the URL is **invalid and returns 400**. It does **not** parse as `baz file.txt | foo bar`."

The reconciling factor is metadata (runtime assumes `foo` has arity ≥ 1; addendum assumes arity 0),
but the runtime presents boundary-by-next-known-command as a general parser capability ("The parser
**may** treat the next known command … as a pipeline boundary"), whereas the addendum forbids any
arity inference absent metadata. They cannot both be the default.

**Resolution (decided — drop inference):** Remove the speculative "next known command boundary"
inference from runtime §10.3. Arity is the *only* thing that determines argument/boundary splitting
(addendum §5.1): a command's arguments are exactly its declared arity, and the next stage begins
immediately after. Metadata-free commands have arity 0 (item B), so `/foo/bar/baz/file.txt` with no
metadata is 400, per addendum §7.

---

## D. Metadata field names differ between the two specs

**Severity: medium (concrete, easy to fix).**

| Concept | runtime §7.3 field | addendum §5 field |
|---|---|---|
| input mode | `input-mode` | `input` |
| output mode | `output-mode` | `output` |
| exit→HTTP map | `exit-status-mode` | `exit` |
| stderr handling | `stderr-mode` | `stderr` |
| arity | `arity` | `arity` ✓ |
| methods | `methods` | `methods` ✓ |

A parser written to one spec will not read metadata files written to the other.

**Resolution (decided — short forms):** The addendum's short forms (`input`, `output`, `exit`,
`stderr`) are canonical. **Action:** update runtime §7.3 to use them. Reconcile the runtime-only
fields into the same convention — recommend `mime`, `mutates`, `parse-mode` (already short) stay
as-is, giving the canonical field set: `arity`, `input`, `output`, `methods`, `mime`, `mutates`,
`parse-mode`, `stderr`, `exit` (see Q-table #4).

---

## E. Per-command (multi-`?`) query strings: valid, but require runtime-side request-target parsing

**Severity: medium (implementation note, not a validity defect).** *Initially flagged as "invalid
URL syntax"; corrected below — the author confirms these URLs are valid and constructed directly.*

Both specs attach query strings to individual path segments:

- runtime §4.7 / §8.5 / §16.5: `/grep?pattern=needle&ignore-case=true/jq?filter=.items[]/haystack.json`
- addendum §6: `/foo?x=1/bar/baz.txt`, `/grep?arg=needle/jq?arg=.items[]/haystack.json`

**These are well-formed URIs.** RFC 3986 §3.4 defines `query = *( pchar / "/" / "?" )` — `?` and `/`
are *legal characters within* the query component. So the string violates no syntax rule. The only
consequence of the rule is **decomposition**: the first `?` starts the single query component, and a
*stock* URL parser will report path = `/grep` and query = `arg=needle/jq?arg=.items[]/haystack.json`
(the entire tail as one opaque query string). It does **not** split into multiple path segments and
multiple queries on its own.

This is fine for this system because browsers and curl transmit the full **origin-form
request-target** (`absolute-path [ "?" query ]`) unchanged — the server receives the entire string
`/grep?arg=needle/jq?arg=.items[]/haystack.json` and re-parses it with its own rules. The author's
point stands: such URLs don't arise from existing HTML pages; they are constructed directly, and
nothing is lost in transit.

**Resolution (accepted with implementation notes):** Keep the multi-`?` per-segment design. The
specs should add these notes so implementers don't trip on stock libraries:
1. The runtime **MUST parse the raw request-target itself** and not rely on a stock URL library's
   path/query split (which would lump everything after the first `?` into one query string).
2. Intermediaries/proxies/CDNs may normalize, reorder, or reject multiple `?`; document that the
   system assumes a direct connection to the runtime.
3. A `#` fragment is never transmitted to the server, so fragments cannot appear in a pipeline.
4. Characters such as `[` `]` are percent-encoded by browsers (already shown as `%5B%5D`); the
   runtime decodes per-segment after splitting.
5. Reconcile with runtime goal #3 / §12.2: "ordinary URL rules" should be reworded to "ordinary URL
   *syntax*, with runtime-defined decomposition of the request-target," to set expectations.

---

## F. Core query parameter name: `arg` vs `pattern`/`filter`

**Severity: medium.**

The addendum §6.1 declares `arg` the **core** argv parameter and explicitly classifies `pattern`,
etc. as command-specific and *not interpreted by the core parser*. But every runtime query-string
example (§4.7, §8.5, §16.5) uses `pattern=`, `filter=`, `ignore-case=` — none of which the core
parser would act on. The runtime never mentions `arg`. So the runtime's marquee "named arguments"
examples do not actually exercise any core mechanism.

**Proposed resolution:** Add `arg` to the runtime (it is the core contract) and rewrite the
runtime query examples using `arg`, or clearly relabel the `pattern`/`filter` examples as
"command-specific parameters interpreted by the command itself, not by the core parser."

---

## G. `/&` stderr marker: placement, terminology, and an internal contradiction

**Severity: medium.**

1. **Different mental models.** Runtime §8.8 / §15.4: "`/&` may be used **instead of** `/`" (a
   separator replacement), with example `/grep/needle/& noisy-command/input.txt` — which also
   contains a literal **space** (`/& noisy-command`), invalid in a URL path. Addendum §8: `/&` is
   "**attached as a prefix** to the command segment," example `/wc/-l/&grep/error/file.txt`.
   Separator-replacement vs. command-prefix are different syntaxes.

2. **Internal contradiction in the addendum.** §8 says the token is "attached as a prefix to the
   command segment **on the left side of the boundary** in URL order," but the example `/&grep`
   attaches `&` to `grep`, which is on the **right** side of the wc↔grep boundary in URL order.

3. **Overloaded "left."** §8 then says `/&grep` "modifies that command's connection to the next
   command **to its left**," and that `/wc/&grep/file.txt` "marks the boundary between grep and wc,
   not the boundary between `cat file.txt` and grep." In the data-flow pipeline
   `cat file.txt | grep | wc`, `wc` is *downstream* (right) of `grep`, but it is *left* of `grep`
   in URL order. The word "left" is used for both URL order and pipeline order without
   disambiguation, making the rule hard to apply.

**Proposed resolution:** Pick one syntax (recommend the addendum's prefix form, `/&cmd`). State the
rule purely in URL order with no "left/right" pipeline language: "`&` prefixed to a command segment
makes that command's input boundary (the connection from the preceding/upstream stage in URL order)
a `|&` merge." Fix the addendum's self-contradictory "left side of the boundary" sentence. Remove
the stray space from runtime §8.8. Provide one worked example shared by both docs.

---

## H. "Command shadows file" (runtime §6.2) vs. "exact filesystem path wins" (addendum §9.1/§3)

**Severity: medium (reconcilable, but the principles read as opposites).**

- Runtime §6.2: a command "takes precedence over an ordinary file of the same name"
  (`/wc/foo.txt` runs the `wc` command even if `root/wc` exists as a file).
- Addendum §2 step 2, §3, §9.1: "An exact filesystem path has precedence over command parsing."

These reconcile *only* because in `/wc/foo.txt` the exact path would be `root/wc/foo.txt`, which
cannot exist when `root/wc` is a regular file — so the exact-path check fails and command parsing
proceeds. But the two stated *principles* ("command wins over same-named file" vs. "exact path
always wins") sound contradictory and will confuse implementers, especially for the single-segment
case `/wc` where `root/wc` exists as a file and `wc` is also a command (addendum → serve file;
runtime §6.2's spirit → run command).

**Proposed resolution:** State one precedence ladder in both docs (addendum §9.5 already has the
right shape): (1) exact full-path filesystem resource; (2) command parse; (3) synthesized resource;
(4) 404. Then clarify that §6.2's "shadowing" only applies when the exact full path does **not**
exist, and give the single-segment `/wc` case explicitly.

---

## I. Request body input, output redirection, and the implied-`cat` suffix

**Severity: medium. The addendum does not mention HTTP request bodies at all.**

1. **Body vs. suffix.** Runtime §10.6: `POST /grep/needle/sort` with a body → `sort | grep needle`,
   body on stdin. But the addendum's algorithm (§2 step 8) always supplies the rightmost suffix via
   implied `cat`. If a request has *both* a file suffix and a body, which feeds the pipeline?
   Undefined.

2. **Output redirection not derivable from arity.** Runtime §9.3 / §16.7:
   `POST /sort/output.txt/input.txt` → `sort input.txt > output.txt`. Under the addendum's generic
   arity model, `sort` with arity 2 receives argv `["output.txt","input.txt"]` → `sort output.txt
   input.txt`, a completely different command (no redirection; both treated as inputs). The
   `out > file` semantics are command-specific and not expressible by `arity` alone. How does a URL
   express "write stdout to this path"? Undefined.

**Proposed resolution:** Add a section to the addendum covering request bodies: define precedence
between body-as-stdin and suffix-as-implied-`cat` (recommend: an explicit file suffix wins; body is
available only when no suffix is present, or via an explicit `body`/`stdin` command). Specify that
output redirection is **not** a core URL feature; `/sort/output.txt/input.txt` semantics belong to a
command-specific definition of `sort`, not the core parser — and fix runtime §16.7 to say so.

---

## J. Path argument as string vs. file contents

**Severity: medium (an ambiguity the specs never resolve explicitly).**

When a path segment is consumed as a command argument (`arity`), is the command given the **literal
segment string** or the **contents of the file** it names? `/grep/needle/file.txt` clearly wants
`needle` as a literal string. But `/diff/a.txt/b.txt` (runtime §10.5) wants `a.txt` and `b.txt` as
**file paths the command opens** (or their contents?). The specs use "argument segment" for both
the literal-string case (`needle`, `-l`) and the file case (`a.txt`), without distinguishing.

**Proposed resolution:** Define argv segments as **literal strings** always (so `diff` receives the
strings `"a.txt" "b.txt"` and opens them itself, exactly like a shell). Clarify that the runtime
does not resolve argv segments to file contents — only the implied-`cat` input suffix is resolved to
bytes. Document how relative paths in argv are interpreted (relative to root? see also §7.1's
out-of-root command paths).

---

## K. "Ambiguity → 400" framing vs. a deterministic parser

**Severity: low/medium.**

Runtime §8.7, §10.4, §15.2 describe parsing as potentially producing "multiple possible parses"
resolved (or not) into 400 Bad Request. The addendum's algorithm (§2) is **deterministic**: given
the filesystem, PATH, and metadata, exactly one parse results; failures are arity/boundary/query
*violations*, not "ambiguity." Under the addendum there is no genuine multiple-parse ambiguity left.

**Proposed resolution:** Reframe runtime §10.4/§15.2: 400 is returned for *invalid* parses
(arity/boundary/query/metadata violations per addendum §10.1), not for unresolved ambiguity. Remove
or rewrite the "multiple possible parses" language, or keep it only as a description of *why* the
deterministic rules were chosen.

---

## L. Commands that consume the raw URL (`explain`, `parse-mode`) are outside the addendum's algorithm

**Severity: medium.**

Runtime §10.7 / §16.8 / §12.3: some commands (e.g. `explain`) "opt out of normal URL parsing" and
receive the remaining URL expression verbatim; downstream commands are **not** executed. Runtime
§7.3 lists a `parse-mode` metadata field, presumably the opt-out switch — but it is never specified.
The addendum's normative algorithm (§2) has no step for "command consumes remaining URL," so a
strict implementation of the addendum would still parse and execute `/explain/grep/needle/…`
as a pipeline.

**Proposed resolution:** Specify `parse-mode` (e.g. `parse-mode raw` = command receives the
undecoded remaining URL suffix and the runtime does not parse it further). Add a step to the
addendum's §2 algorithm: after resolving a command, if its metadata sets raw parse mode, hand the
remaining suffix to it and stop parsing. Confirm whether a `raw` command can itself appear anywhere
or only in leftmost position.

---

## M. HTTP method handling gaps

**Severity: low.**

Both specs list a `methods` metadata field (runtime §7.3, addendum §5) but never define what
happens when a request method is not in the command's allowed set. Neither spec mentions **405
Method Not Allowed**. Runtime §9.5 says "Normal HTTP semantics should be preserved," which would
imply 405, but it is not stated. Also unspecified: how `methods` filtering interacts with multi-stage
pipelines (does each stage's `methods` apply, or only the leftmost?).

**Proposed resolution:** Specify 405 for a method not permitted by a command's `methods` metadata,
and state that in a pipeline the request method must be permitted by all stages (or define which
stage governs).

---

## N. stderr "discarded by default" vs. captured for error responses

**Severity: low.**

Runtime §15.4 and addendum §5 default `stderr` to **discard**. But addendum §10.3 says nonzero-exit
error responses "may include limited sanitized **stderr**," and §10.1 lists stderr among reportable
diagnostics. If stderr is discarded, it is not available to include in the error body.

**Proposed resolution:** Clarify that "discard" means stderr is not merged into the response stdout
stream, but the runtime still *captures* stderr internally so it can be surfaced in error
diagnostics. Or state that stderr in error responses is only available under non-default `stderr`
modes.

---

## O. Synthesized resources

**Severity: low (largely resolved by the addendum).**

Runtime §6.4, §15.1 mention synthesized/implementation-defined responses for missing paths but give
no precedence rules. Addendum §9.5 supplies them (exact file > command parse > synthesized). This is
a gap the addendum fills; just ensure the runtime references it. Addendum open question §15.9 (should
a synthesized resource report why it lost to a command parse?) remains open.

---

## P. Stale / overlapping open-question lists

**Severity: low (housekeeping).**

Runtime §17 lists open questions, several of which the addendum already answers:
- Runtime §17.3 ("default arity rules") → answered by addendum §4 (arity 0).
- Runtime §17.5 ("syntax/semantics of `/&`") → partially answered by addendum §8 (but see item G).
- Runtime §17.1 ("metadata syntax") → partially answered by addendum §5 (but see item D naming).

The two open-question lists (runtime §17, addendum §15) overlap and are not cross-referenced. The
title "Addendum" implies a relationship, but neither doc links to the other.

**Proposed resolution:** Add a cross-reference header to both docs. Prune runtime §17 of questions
the addendum resolves; mark partially-resolved ones with a pointer.

---

## Q. Carried-forward questions (ratified and applied)

These come mostly from addendum §15 and runtime §17. The resolutions below have been ratified and
applied to the specs (pipeline_parsing.md §§5.2, 5.5, 5.6, 6.1, 8.1, 9.5, 10.3, 10.4, 11, 15; and
runtime.md §§6.5, 7.3, 9.3, 17).

| # | Question | Source | Proposed resolution |
|---|---|---|---|
| 1 | Variable arity beyond `arity *` (`0..*`, `1..3`)? | addendum §15.1 | Defer; support only `N` and `*` in v1. Ranges are a future extension. |
| 2 | Is `argv` (in addition to `arg`) a reserved core query key? | addendum §15.2 | Reserve only `arg`; `argv` stays unreserved/command-specific in v1. |
| 3 | Metadata grammar: quoting, escaping, comments, duplicate/invalid fields. | addendum §15.3, runtime §17.1 | Define: `#` line comments; whitespace-separated tokens; last-wins for duplicates; unknown field = ignore (warn); malformed value → 500 (see #5). |
| 4 | Full normative list of metadata fields. | addendum §15.4 | Settle the union of both docs under one naming convention (item D): `arity`, `input`, `output`, `methods`, `mime`, `mutates`, `parse-mode`, `stderr`, `exit`. |
| 5 | Malformed metadata → 400, 500, or impl-defined? | addendum §15.5, runtime | Recommend **500** (server-side config error, not a client error). |
| 6 | stderr/stdout sanitization limits in error bodies. | addendum §15.6 | Impl-defined with a recommended byte cap (e.g. 8 KiB each); document the default. |
| 7 | `cat` over a directory. | addendum §15.7 | Keep: allowed to fail naturally per the command's real behavior; no special-casing. |
| 8 | Command names literally beginning with `&`. | addendum §15.8 | Discourage; require `%26`-escaping the leading `&` if such a command must be addressed. |
| 9 | Should a synthesized resource report losing to a command parse? | addendum §15.9 | Optional diagnostic header only; not required. |
| 10 | Standardized vs. impl-defined names for `X-WebShell-*` headers. | addendum §15.10 | Standardize the three names in the addendum (`X-WebShell-Command/Pipeline/Source`) as the recommended convention. |
| 11 | Directory listing vs. `index.html` precedence. | runtime §17.6, §6.5 | Recommend `index.html`/default file wins; fall back to listing if none. |
| 12 | Default behavior for POST to ordinary files/directories. | runtime §17.4 | Define explicitly (see item I); recommend 405 unless a command governs the path. |

---

## Summary of the highest-impact decisions (all resolved)

1. **Input model** (item A) — **decided: implied `cat` to stdin.** Rewrite runtime examples.
2. **Per-command query syntax** (item E) — **decided: multi-`?` accepted as valid**; runtime parses
   the raw request-target itself (RFC 3986 §3.4 confirms validity).
3. **Canonical metadata field names** (item D) — **decided: short forms** (`input`, `output`,
   `exit`, `stderr`).
4. **Next-known-command boundary inference** (item C, §10.3 vs §7) — **decided: drop it**; arity
   alone splits args/boundaries.

Lower-risk items (B, F, G, H, I, J, K, L, M, N, O, P) have proposed resolutions above and can
proceed; none are blocked now that 1–4 are settled. The Q-table (section Q) items have been ratified
and applied to the specs.
