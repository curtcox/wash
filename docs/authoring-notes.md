# Authoring notes

Working notes about the book that are *not* meant for readers. The served
chapters under `book/` are reader-facing and carry no author notes; anything an
author needs to remember about a chapter lives here instead.

The book app is canonical under `book/` (served by `./start`, link-checked by
`./check`). `docs/` holds planning material only: [the outline](guide-outline.md)
and these notes.

---

## Chapter 1 — Getting Started

**Runnable scaffold.** The chapter is runnable end to end. At the repo root:
`./start` puts `impls/reference` on `PYTHONPATH`, launches
`python -m wash.server --root book`, and opens the browser. The served root
`book/` holds the home console (`index.html`), the chapter (`ch01.md`), the
`render`/`view`/`ask` commands under `book/bin/` with metadata under
`book/env/meta/` (and an `exec` interpreter-rule safety net), and a seeded
`notebook/0/`. Verified against the reference server: landing page, raw +
rendered chapter, `POST /ask`, rendered `/view/...`, and nodes written on disk.
`./check` (also `make check-book`, wired into the CI `validate` job) crawls the
served book and fails on any link returning ≥ 400.

**PRG is client-side.** The reference runtime does not let commands emit
redirects or custom headers (`command_full_http_response` disabled), so `ask`
prints the leaf URL and the home page's JS navigates there. A spec-conformant
server that supports full HTTP responses could do the redirect server-side via a
TPC adapter, as the TPC spec describes. Flag for Ch15.

**Spec/impl finding (resolved).** `pipeline_parsing.md` §4/§12.1 shows a
metadata-free command taking a *multi-segment* nested input suffix
(`cat b/c.txt | a`). The reference parser previously rejected *any* metadata-free
command followed by more than one suffix segment, using segment count rather than
filesystem resolution as the test — so a nested suffix that genuinely resolved to
a file (e.g. `/identity/nested/data.txt`) was wrongly 400. Fixed in favor of the
spec (Option A): the parser now allows a multi-segment suffix when the whole
suffix resolves to an existing path (implied cat), and only returns 400 when it
does not (`/identity/extra/data.txt` → 400, vector `mf-path-args-400`). A single
missing segment is still a 404 missing-resource (`/wc/missing-input.json`, vector
`prec-missing-suffix-404`). §4 now states the resolution-based rule normatively,
and vectors `mf-implied-cat-nested` / `mf-pipeline-nested` cover the positive
case. The previously cited vector id was a slip: `mf-multi-path-args-400` is
`/identity/grep/needle/data.txt`; the `/identity/extra/data.txt` case is
`mf-path-args-400`.

Because nested suffixes now work, book chapters could live in subdirectories;
they are still kept flat under `book/` by choice, not by constraint, and `render`
is addressed as `/render/ch01.md` for simplicity.

**Spec fidelity checkpoints exercised by the scaffold:** URL→path mapping
(runtime.md §6.1), directory index-vs-listing (§6.5), GET-never-mutates (§9.1),
PUT writes the literal path (§9.2), command parse + `mime`/`parse-mode raw`
metadata (pipeline_parsing.md §5), implied cat over a file (§4), and the SDT node
layout (`a` text, `b` metadata, ordinal dirs) written by a TPC with a
`Created Node` manifest.

**Naming-model spine.** The "two kinds of file" framing (read vs. run) is the
agreed naming model; the human-readable indirection layer is deliberately
deferred (noted in §1.4 and §1.5).

**Live panel.** A plain `fetch` POST + JS redirect — needed because PRG is
client-side here. A pure zero-JS `<form>` would post fine but could not then
redirect to the new leaf on the reference server.
