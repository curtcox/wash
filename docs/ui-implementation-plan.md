# wash Web UI — Implementation Plan

> Derived from [docs/ui-requirements.md](ui-requirements.md). The UI ships as a
> **drop-in bundle** (static files + helper commands) served by an unmodified
> wash runtime. This plan sequences the work, names concrete artifacts, and
> isolates the few spec/conformance follow-ons from the app itself.
>
> Citations: §x = `specs/runtime.md`; PP §x = `specs/pipeline_parsing.md`;
> ch.x = `docs/guide-outline.md`; Rq Ax = requirements doc section.

---

## 0. Approach & ground rules

- **Two independent tracks.**
  - **Track A — the bundle** (this is 95% of the work): pure app, built only from
    spec primitives, validated by ordinary testing, no conformance impact.
  - **Track B — spec follow-ons** (small, optional, decoupled): standardize
    `explain`; promote `X-WebShell-*` headers to required (Rq E). Track A must
    work *without* Track B (graceful degradation, Rq A.10).
- **Reference impl is the only validated host in v1** (Rq A.10). Touch
  `impls/reference/` only for the prerequisite gaps in §2 — never to special-case
  the UI.
- **The honest-window spine** (Rq §0) is a review gate, not a phase: every PR is
  checked against "does this ever present stale state as live, hide what ran, or
  obscure what will be mutated?"
- **Zero build** (Rq A.10): the committed bytes are what runs. No bundler, no
  transpile, no `node_modules`. CI for the bundle is shell/Python tests of the
  helper commands plus a headless smoke of the static app.

### How `/ui/...` framing works (a correctness note that drives the layout)

Exact-filesystem-path-wins (§6.2) lets static assets and deep-link framing
coexist with no conflict:

- `GET /ui/app.js` → real file `root/ui/app.js` is served (exact path wins).
- `GET /ui/` or `/ui` → directory → `root/ui/index.html` (the app shell).
- `GET /ui/grep/needle/haystack.json` → no such file → command parse → the `ui`
  command (`parse-mode raw`) returns the **same app shell**; the JS reads
  `location.pathname`, strips `/ui/`, and fetches the raw resource
  `/grep/needle/haystack.json` same-origin to render in chrome.

So the bundle ships **both** a `ui/` asset directory **and** a `bin/ui` raw
command that emits the shell for deep suffixes (it can simply stream
`ui/index.html`).

---

## 1. Bundle layout (the deliverable artifact)

```
<root>/
  ui/                      # static app (served as ordinary files)
    index.html             # app shell (also emitted by bin/ui for deep links)
    app.js                 # ES-module entry
    modules/               # router, api, render, thread, editor, panels, chrome
    vendor/                # vendored, minimal, no-CDN deps (md, json-view)
    style.css
    RECOVERY.md            # "re-drop the bundle" + raw curl/PUT floor
    .ui-manifest           # self-manifest: every path this bundle owns (Rq A.8)
  bin/                     # helper commands (emit JSON unless noted)
    ui  explain  commands  names
    name-new  name-set  name-rm
    append  search  help  term  rootinfo
  env/
    meta/                  # one metadata file per helper command
      ui  explain  commands  names  name-new  name-set  name-rm
      append  search  help  term  rootinfo
    path                   # MERGED additively to include `bin` (Rq A.10)
  exec                     # MERGED additively: interpreter rules for helpers
  bin/wash-ui-install      # installer: additive merge, abort+report on conflict
```

The installer (`wash-ui-install`, run from the shell, not the UI) copies `ui/`
and helper commands, then **merges** `env/path` / `exec` additively and
**aborts + reports on any conflict** (Rq A.10, open question #6). Recovery =
re-run it (re-drop), Rq A.8.

---

## 2. Prerequisite gaps to close first (Track A-0, small)

These are blocking and live partly in the runtime/tooling, so do them up front.

1. **SDT write verbs.** `tools/sdt` has only `check`; the SDT append command
   (Rq A.5) needs atomic next-ordinal allocation + node write. **Implement
   `sdt name` (next ordinal) and `sdt add` (write `a`, auto-write `b`
   provenance)** in `tools/sdt` (stdlib-only, implementation-agnostic, matching
   ch.17.5), with an exclusive-create/locking strategy so two tabs can't collide
   (Rq A.5). The `append` helper command shells to these.
2. **Header audit.** Confirm `impls/reference` actually emits all four headers
   the UI consumes — `X-WebShell-Source`, `-Command`, `-Pipeline`,
   `-Resolved-Path` (capabilities claim `execution_metadata_headers: true`).
   Add any missing; this is reference-impl work, not UI-specific. (Enables A.7,
   A.3, A.9 without the UI re-deriving anything.)
3. **`term` portability shim.** Decide the v1 host-terminal launch matrix
   (macOS `open -a Terminal`, `$TERMINAL`, …) and the no-terminal fallback
   (return a copyable `cd` line). (Rq open question #4.)

Exit: `sdt add`/`name` covered by `make sdt-test`; a manual `curl` shows all four
headers on a pipeline response; `term` launches a terminal on the dev machine.

---

## 3. Helper-command API surface (Track A)

All are bundle commands; the UI renders what they return. Mutating ones carry
`methods POST` + `mutates true`.

| Command | Method | parse-mode | mutates | Returns / does |
|---|---|---|---|---|
| `ui` | GET | raw | no | App shell HTML for deep links (§1). |
| `explain` | GET | raw | no | Structured parse trace JSON: per-segment role (cmd/arg/input), effective meta/defaults, exit mapping, effective pipeline (Rq A.9). |
| `commands` | GET | — | no | Verbs on `env/path` + their metadata → JSON (autocomplete + help, Rq A.6). |
| `names` | GET | — | no | `sdt check --json` output (names→targets, severities, winner) (Rq A.3). |
| `name-new` / `name-set` / `name-rm` | POST | — | yes | Edit a `c` file (scope arg); honor last-wins dedup (§6.6.1) (Rq A.5). |
| `append` | POST | raw or arity | yes | Atomic SDT append via `sdt add`; writes `b`; emits `Created Node`; 303 redirect to new node (Rq A.5). |
| `search` | GET | — | no | Server-side content search over `a` files → JSON (Rq A.2, P2). |
| `help` | GET | raw | no | Structural help over `commands`/metadata (no model) (Rq A.6). |
| `term` | POST | — | yes | Launch host terminal at `<dir>` (Rq A.7). |
| `rootinfo` | GET | — | no | Root absolute path + origin (Rq A.10). |

File mutations that are *not* SDT (commands, `env/meta`, `c`, plain files) use
**core PUT/DELETE to literal paths** — no helper command needed (Rq A.5).

---

## 4. Phased delivery (Track A)

### Phase 1 — Walking skeleton (read-only spine)
*Goal: open `/ui/<anything>`, see it framed, navigate, prove the honest-window
model end to end.*
- `bin/ui` + `ui/index.html` + `app.js` shell; router that derives the target
  from `location.pathname` (strip `/ui/`) and the fragment for view state
  (Rq B, A.1).
- `api.js`: same-origin fetch + **runtime feature-detection** (probe headers,
  methods) with graceful degradation (Rq A.10).
- `render.js`: content-type matrix — text/JSON/markdown/image/PDF/binary/error;
  sandboxed-iframe for `text/html`; capped large output + raw/download escape
  (Rq A.4).
- Chrome: root identity (path + origin via `rootinfo`), **raw⇄framed toggle**
  (Rq A.7, A.10), staleness-honest "reload to recompute" affordance (Rq A.1).
- **Exit:** `/ui/notes.txt`, `/ui/grep/.../haystack.json`, `/ui/dir/` all render
  framed; raw URLs still return raw; no-JS/curl still works.

### Phase 2 — Notebook mode + tree
*Goal: thread-centric SDT view as the default surface.*
- Node-kind detection (live, contextual) — plain/dir/SDT/command/env-config
  (Rq A.2).
- Thread view: current node `a`, generic `b` provenance (special-case
  `created`/`author`), predecessor + path-to-root, branches; collapse off the
  main line (Rq A.2, A.1).
- Secondary Files browser (Rq A.2).
- Backing-files + shell-here chrome (`term`, exec-cwd rule) on every page;
  honest no-backing-file cases (Rq A.7).
- **Exit:** an SDT notebook root renders as a readable thread; every page exposes
  backing files + shell-here.

### Phase 3 — Name resolution, explain, autocomplete, help
*Goal: the browser-beats-shell wins.*
- Names panel from `names` (`sdt check --json`): winner-only targets, linter
  severities, quiet-inert marker, escape→resolved-path links; in-tree name chips
  + "shadows name" markers (Rq A.3).
- Live `X-WebShell-Resolved-Path` shown on navigation (Rq A.3).
- `explain` integration: on-demand "what ran ▾" pointed at the current URL;
  error pages render the runtime's own JSON diagnostic (Rq A.9).
- Editor autocomplete (commands via `commands`, names via `names`) + structural
  `help` (Rq A.6).
- **Exit:** resolution surprises are visible before they bite; failures show the
  runtime diagnostic verbatim.

### Phase 4 — Mutation & authoring (first-class)
*Goal: create/edit/delete safely; the heart of "authoring is MVP."*
- Method controls (Save=PUT, Delete=DELETE, Run=POST), never inferred; the one
  lightweight confirm for DELETE / PUT-over-existing showing the **resolved
  path**; loud mutates badge everywhere (Rq A.5).
- **SDT append**: child + sibling, server-side alloc via `append`, auto-`b`,
  redirect-to-new-node; "edit a node" = append sibling (never overwrite `a`/`b`)
  (Rq A.1, A.5).
- Editor component (shared for bodies + authoring) + file upload (Rq A.4, A.5).
- Command authoring: validating `env/meta` form (enforces GET+`mutates true`
  invalid), interpreter-rule executability, `env/path` auto-wire, orchestrated
  multi-file create that still allows disconnected saves (Rq A.5).
- `c` name create/retarget/drop via `name-*` with live resolution preview;
  single target; scope default + override (Rq A.5).
- Edit-in-place PUT for non-SDT; plain-file rename-as-move (PUT-new+DELETE-old,
  shown as two ops); SDT-delete/dir-move/compact remain shell-only (Rq A.5).
- **Exit:** create a command, name it, append notebook turns, and edit/delete —
  all from the browser, with resolved-path always shown before a mutation.

### Phase 5 — Packaging, self-protection, polish
- `wash-ui-install`: additive merge, abort+report on conflict; `RECOVERY.md`;
  `.ui-manifest` (Rq A.8, A.10).
- UI-self-file warn-not-block (consult `.ui-manifest`); re-drop recovery path;
  raw-curl floor documented (Rq A.8).
- Posture: localhost-assumed + non-local warning banner; same-origin/no-CORS;
  no auth; confirm UI-integrity isolation is the only boundary (Rq A.10).
- Look/feel: dev-minimal, auto light/dark, keyboard-first + semantic HTML,
  responsive laptop↔large-monitor (Rq A.10).
- **Exit:** drop the bundle into a fresh root and a populated root; both work or
  fail loudly; breaking the UI from within is recoverable without the UI.

### Phase 6 — Deferred (P2, post-v1)
NL "ask wash" assistant (model TPC); full-tree `search` UI; full backing-file
provenance inline; `c`-name alternatives/multi-target; in-browser terminal;
multi-impl host validation; multi-root switcher; CLI→browser paste box. (Rq C.)

---

## 5. Front-end architecture (zero-build ES modules)

- **No framework.** `app.js` + `modules/`:
  - `router.js` — path (target) + fragment (view state) ↔ DOM; URL is the state
    store (Rq A.1, B).
  - `api.js` — fetch wrappers, feature-detection, header parsing, error→JSON.
  - `render.js` — content-type dispatch; iframe sandboxing; large-output caps.
  - `thread.js` / `files.js` — notebook + filesystem views.
  - `editor.js` — shared authoring/body editor + query-sugar encode/decode
    (reversible; canonical URL is the artifact; decode-preview) (Rq A.4).
  - `panels.js` — backing-files, explain, names.
  - `chrome.js` — root identity, raw/framed toggle, shell-here, confirms,
    mutates badges, staleness affordance.
- **State:** URL = navigable state; fragment = client view state; transient edit
  buffers live in memory only (not URL-addressable) (Rq A.1).
- **Vendored deps:** prefer hand-rolled or tiny no-dep markdown + JSON viewer;
  no CDN, no runtime network (Rq A.10).

---

## 6. Testing strategy

- **Helper commands:** unit tests per command (Python/shell), including
  `sdt add`/`name` under `make sdt-test`; assert `append` allocation is
  race-safe and writes `b`.
- **Conformance harness:** untouched by Track A. Used only if Track B lands
  (new clauses + vectors).
- **UI smoke:** a committed **demo root** (bundle installed into a small SDT
  notebook with commands + `c` names + an escaping/dangling name) for manual
  verification, screenshots, and an optional headless check. This doubles as the
  install/merge/conflict test fixture.
- **Honest-window review gate** on every PR (Rq §0).

---

## 7. Track B — spec/conformance follow-ons (separate, optional)

Only if/when pursued; they make the UI first-class on *every* impl rather than
just the reference. Follow the propagation path in `AGENTS.md`
(`specs/*.md` → `harness/conformance/spec.py` clause → vectors → impls):

1. **Standardize `explain`** (§16.8): conventional name + JSON output schema.
   Highest value (the UI depends on it in MVP). Until done, `explain` is
   bundle-private.
2. **Promote `X-WebShell-*` headers** suggested→required (§11): add clauses +
   vectors so backing-files/resolved-path/"what ran" are guaranteed.

Never spec'd: `term` (host/OS-specific).

---

## 8. Risks & open-question dependencies

| Risk / open question (Rq D) | Resolve by | Mitigation |
|---|---|---|
| SDT `add`/`name` don't exist yet | §2 / Phase 1 prereq | Implement in `tools/sdt`; gate `append` on it |
| `term` portability (#4) | §2 | Support matrix + copyable-`cd` fallback |
| `b` provenance schema (#1) | Phase 2 | Render generic + special-case `created`/`author`; revisit if a convention emerges |
| Name scope default (#3) | Phase 4 | Default nearest enclosing dir + visible override |
| Install conflict UX (#6) | Phase 5 | Abort + report first; guided merge is P2 |
| Non-local detection (#5) | Phase 5 | Conservative heuristic; warn-only, never block |
| Helper namespacing (#7) | §1 / Phase 5 | Document reserved helper names; `.ui-manifest` records ownership |
| Optional behavior absent on a host | All phases | Graceful degradation (Rq A.10) — Track A never hard-depends on Track B |

---

## 9. Sequencing summary

`§2 prerequisites` → `Phase 1 skeleton` → `Phase 2 notebook` →
`Phase 3 resolution/explain/help` → `Phase 4 authoring/mutation` →
`Phase 5 packaging/posture` → (`Phase 6 deferred`). Track B runs in parallel and
out-of-band; Track A ships without it.
