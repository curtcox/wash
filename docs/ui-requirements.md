# wash Web UI — Requirements (v1)

> Output of a requirements interview with the maintainer. The UI ships *with*
> wash as a drop-in bundle served by the runtime itself. This document is the
> agreed scope; it is not normative spec text. Where it implies changes to
> `specs/`, those are called out in §E.
>
> Citations like §6.6 / §11.4 refer to `specs/runtime.md`; PP §x refers to
> `specs/pipeline_parsing.md`; ch.17/18 refer to `docs/guide-outline.md` (SDT).

---

## 0. Framing & non-negotiables

**What the UI is.** An *alternate, more convenient surface* over the same
facilities the user already has via the shell. It is served by the runtime as
ordinary files under a root (§11.1, §11.3), addressed by URL, like any other
resource. It is a **bundled application built only from existing spec
primitives** — it introduces **no new normative runtime behavior** and is **not
conformance-tested** itself.

**Hard constraints (decided before the interview, designed around — not
relitigated):**

1. The UI runs ON wash, served as files under a root.
2. URLs are deep links: any state worth returning to is a bookmarkable,
   shareable, `open(1)`-able URL.
3. The UI does **not** sandbox, gate, or restrict host access. The user already
   has full shell access; the UI is a convenience over the same power.
4. Dangerous operations — including ones that can change or break the UI itself
   — are in scope and must be supported. The escape hatch is the command line.

**Priority ranking (maintainer, §7.6).**

- *Must get right, ranked:* (1) **URL/deep-link fidelity**, (2) **"see the
  past"** (durable, append-only history), (3) **never act on the wrong target**.
- *Failure modes to avoid, ranked:* (1) **dishonest freshness / hidden state**,
  (2) **silent wrong-target mutation**, (3) **the UI bricks itself
  irrecoverably**.

**The spine.** #1 fear (dishonest freshness) and #2 value ("see the past")
unify into one design rule that governs everything: **the UI is an honest window
onto the real filesystem + URL state.** It never becomes the source of truth, it
never fakes freshness, and it always reveals what actually ran and what will
actually be touched.

---

## A. Prioritized requirements

Tiers: **P0** = MVP must; **P1** = MVP should / strongly wanted; **P2** = later.
Each item cites the interview section that fixed it.

### A.1 Honesty, fidelity & history (the spine)

- **P0** Every meaningful state is a real URL — bookmarkable, shareable,
  `open(1)`-able. The filesystem + URL remain the source of truth; the UI is a
  skin. (§2.1, §7.6)
- **P0** Staleness is a feature, not a bug. No live updates, websockets, or
  filesystem watching. **Refresh = recompute = a deliberate step forward in
  time** (§9.6). The UI must never present a stale view as current. (§2.5)
- **P0** Durable history *is* the SDT tree (ch.17–18): append-only nodes,
  provenance in each node's `b` file plus the `Created Node` manifest. History is
  reconstructable from the tree itself. (§3.7, ch.18.8)
- **P0** SDT `a`/`b` are **never overwritten by the UI**. "Changing" a node's
  value = appending a new sibling (alternative) or child (continuation). (§4.2,
  §5.1, §5.4)
- **P1** A non-persistent, in-session action list is a convenience layer over
  the durable SDT history. (§3.7)

### A.2 Navigation & the tree model

- **P0** **Notebook mode is the default.** The primary surface is
  *thread-centric* (current node + predecessor + path to root), the way
  ChatGPT/Claude conversations are trees. The tree is a **mental / navigational
  / URL structure**, not an always-visible sidebar. (§4.1, §4.4)
- **P0** SDT understanding is MVP: the UI reads `a` (content), `b` (provenance),
  and children-as-branches; renders continuations and sibling alternatives.
  (§4.1, §4.2)
- **P0** A secondary **Files** view (raw filesystem browser) exists for
  commands, `env/*`, and repair. (§4.1)
- **P0** **Node kind is computed live and is contextual/dynamic** — plain file /
  directory / SDT node (`a` present) / command (on `env/path`) / `env/*` config.
  A file's *role* is emergent (`env/path` + naming + `exec` rules) and can change
  without editing the file. The UI reflects current role and lets any file be
  wired up/down as a command after the fact. (§4.2, §5.2)
- **P1** Collapse everything off the main line; default-expand the deep-linked
  path. Don't pre-optimize for scale; simple + clear first. (§4.4)
- **P2** Full-tree content search = a server-side **bundle command** the UI
  calls and renders (not client-side; not P0). (§4.4)

### A.3 Name resolution (where the browser beats the shell)

- **P0** Render `sdt check --json` for the static picture (names → targets,
  cycles, dangling, escapes, malformed `c` lines, duplicates) — **reuse the
  linter's severities verbatim** so UI and linter never disagree. (§4.3)
- **P0** Show the **live `X-WebShell-Resolved-Path`** on each navigation —
  "where did I actually land." (§4.3, §6.6.5)
- **P0** Show only the **winning target** for names with alternatives. (§4.3)
- **P1** Mark a name **inert** (shadowed by a literal child) — *quiet /
  informational*, not alarming (it does nothing). (§4.3, §6.6.2)
- **P0** Loops (508/error), dangling (404/error), escapes (403/warning); escapes
  link to their resolved path (intended disclosure, §6.6.4–.5). (§4.3)

### A.4 Issuing commands & rendering responses

- **P0** Command input = a **wash URL/pipeline text box** as the spine. (§3.1)
- **P0** **Reversible query sugar** in `?…` segments: split on spaces honoring
  `"double quotes"`; bare token `x` → `arg=<enc>`; `k=v` → `k=<enc>`
  (named param preserved). Reverse renders `arg=x` as a bare/quoted token. The
  **canonical encoded URL stays the artifact** (deep links, history, copy); sugar
  is input-only. (§3.1)
- **P0** **Decode-preview** always shows the canonical URL as you type. Auto-encode
  reserved bytes inside query values. (§3.2)
- **P0** Response rendering by `Content-Type`: text (raw/pretty toggle), JSON
  (pretty + collapsible), markdown (rendered + source), images/PDF (inline),
  binary/octet-stream (summary + download, never auto-render), errors (status +
  runtime diagnostic body + effective pipeline). (§3.3)
- **P0** `text/html` output renders in a **sandboxed iframe by default**, with an
  explicit "render full/trusted" toggle. (§3.3, §7.5)
- **P0** Merged stderr (`/&`, `stderr merge`) is rendered as one stream (it *is*
  one stream); the chrome shows that the boundary was merged. No fake stderr
  coloring. (§3.3)
- **P0** Large output: cap the rendered preview with a "view raw / download"
  escape; never block the tab. No streaming. (§3.4)
- **No streaming / no in-progress job URLs.** A request is pending until its HTTP
  response arrives; the deep link is the request URL; reopening re-runs. (§2.3)

### A.5 Mutation & authoring (first-class v1)

- **P0** Explicit **method control** per action (Save = PUT, Delete = DELETE,
  Run = POST) — never inferred. (§3.5)
- **P0** One lightweight, non-modal confirm for **DELETE** and **PUT-over-existing**
  that shows the **resolved path** that will actually be touched (defends against
  name-resolution surprises). Not a trust gate. (§3.5)
- **P0** **Mutates / destructive methods render as a loud, consistent badge**
  everywhere a command appears (tree row, detail panel, confirm). (§4.2)
- **P0** Request bodies authored via **inline editor + file upload**; the editor
  is the same component used for command authoring. (§3.6)
- **P0** **SDT append** (the core authoring act): **server-side atomic ordinal
  allocation** via a bundle command (wrapping `sdt add`/`sdt name`); writes `b`
  provenance automatically; both child (continuation) and sibling (alternative)
  first-class; **after append, navigate to the new node** (Post/Redirect/Get).
  (§5.1)
- **P0** **Command authoring** = a coordinated (but not mandatory) multi-file
  operation: body + `env/meta` + `env/path` wiring + an `exec` interpreter rule.
  Executability via **interpreter rules** by default (PUT can't set the exec bit;
  no bit needed per §4.4). Disconnected saves are allowed; command-ness is
  emergent. (§5.2)
- **P0** Command metadata authored via a **validating form** over the normative
  field list (`arity input output methods mime mutates parse-mode stderr exit`),
  enforcing cross-field rules (GET + `mutates true` is invalid → 500) before
  save; raw-edit escape hatch retained. (§5.2)
- **P0** Auto-wire a new command's dir into `env/path` (offer it). (§5.2)
- **P0** **`c` name** create/retarget/drop via bundle commands
  (`name-new`/`name-set`/`name-rm`); scope defaults to nearest enclosing dir with
  a visible override; **live resolution preview before save** (refuse
  loop/dangling, warn escape, quiet inert); **single target** in v1. Raw `c`
  editing retained. (§5.3)
- **P0** Edit-in-place (PUT) for non-SDT files; SDT content stays append-only.
  (§5.4)
- **P1** Rename-as-move for **single plain files** (PUT-new + DELETE-old, shown
  honestly as two ops). "Rename a node" in notebook mode = change a `c` name, not
  move ordinals. (§5.4)
- **Shell-only (not in UI):** SDT node deletion (keep notebook append-only by
  construction), directory move, `sdt compact`. (§5.4)
- **P0** Deleting plain files/dirs/commands via DELETE, behind the resolved-path
  confirm. (§5.4)

### A.6 The editor's intelligence (made of commands)

- **P0** Command-name autocomplete from live `env/path` enumeration; name
  autocomplete from in-scope `c` files. (§4.1)
- **P0** Structural/deterministic help: a `help`/`explain` capability that
  documents commands from their `env/meta` and surfaces "what commands exist /
  how do I use X" — **no model backend**. (§4.1)
- **P0** The bundle ships the helper commands that power all of the above
  (`commands`, `names`, `name-new`/`set`/`rm`, append, search, `help`, `explain`,
  `term`, root-info) plus their `env/meta`. The UI is thin; it renders what the
  commands return. (§4.1, §5.x, §6.x)
- **P2** Natural-language "ask wash how do I X" assistant — a model-backed TPC
  (§18). Designed-for (it's just another command the editor calls); **deferred**.
  (§4.1)

### A.7 Access to underlying files & "shell here"

- **P0** A persistent **"backing files ▾"** + **"shell here"** control in the
  framed chrome on *every* page. (§6.1)
- **P0** **"Shell here"** = a bundle command `POST /term/<dir>` that launches the
  host terminal `cd`'d to `<dir>`. For command results, `<dir>` = the **execution
  cwd (root)** (faithful to §12.3); for files/nodes/dirs, the containing dir.
  (§2.4, §6.1)
- **P0** Backing-file set (MVP) derived from response headers: input source
  (`X-WebShell-Source`) + command file(s) (`X-WebShell-Command`/`Pipeline`).
  Full provenance (per-stage `env/meta`, `exec`, `env/path`) deferred to the
  explain view. (§6.1)
- **P0** Honest about no-backing-file cases (synthesized / no input suffix): say
  so plainly, still offer shell-at-root. (§6.1)
- **P0** Raw/framed toggle (a node viewed with and without chrome are both
  shareable targets) sits in the same chrome. (§2.4, §6.1)

### A.8 The UI's own files & recovery

- **P0** The UI is **not special to itself**: backing-files / view-source works
  on UI pages too; editing the UI is the ordinary edit flow. (§6.2)
- **P0** **Warn, never block** when an edit/delete targets a UI-backing file (the
  bundle ships a self-manifest of its own paths); spell out the recovery. (§5.4,
  §6.2)
- **P0** Recovery = **re-drop the bundle** over the root; the always-available
  floor is raw `curl`/`PUT` + the shell, which **never depends on the UI
  working**. The runtime underneath is untouched, so the UI can brick itself and
  you are never stuck. (§6.2)

### A.9 Explain / resolution trace

- **P0** A dedicated **`explain` bundle command** (parse-mode raw, §10.7) you
  point at a URL (`/explain/<suffix>`); the UI surfaces it **on-demand**
  ("what ran ▾"), not always expanded. Returns structured data: per-segment
  classification (command/arg/input), effective metadata/defaults, exit mapping,
  effective pipeline. (§6.3)
- **P0** Error pages request JSON (`Accept: application/json`) and render the
  **runtime's own** content-negotiated diagnostic (failing stage, exit status,
  pipeline, sanitized stdout/stderr) — no re-derivation. (§6.3, PP §10.3/§10.5)

### A.10 Tech, hosting & posture

- **P0** **Zero build step.** Plain HTML/CSS/ES-module JS; no framework, no
  bundler, no `node_modules`. The shipped bytes are what runs (portable across
  every impl). (§7.1)
- **P0** **Progressive enhancement**: JS builds the chrome; with no JS or via
  curl you still get raw bytes and a working server (the no-JS/curl floor).
  (§7.1, §11.4)
- **P0** Dependencies minimal, **vendored, no CDN, no runtime network** (works
  air-gapped on localhost). (§7.1)
- **P0** Bundle shape: `ui/` assets + helper commands in `bin/` + their
  `env/meta` + `exec` rules; self-contained "copy dir → works"; **install merges
  additively into `env/path`/`exec` but aborts and reports on any conflict**
  (never silent overwrite). (§7.1)
- **P0** Hosting: only the reference (Python) impl is validated as a host in v1;
  the design constraint is "spec'd primitives only, so any conformant impl hosts
  it unmodified." (§7.2)
- **P0** The UI **degrades gracefully** when optional behavior is absent
  (`X-WebShell-*` headers, explain, `sdt check`); runtime **feature-detection**,
  no capability-negotiation protocol. (§7.2)
- **P0** Look & feel: developer-tool minimal, monospace-forward; auto light/dark
  via `prefers-color-scheme`; theming = edit the bundle CSS (no theme engine).
  (§7.3)
- **P0** Keyboard-first + semantic HTML baseline; WCAG AA aspirational, not a v1
  gate. (§7.3)
- **P0** **Responsive across the laptop ↔ large-monitor range** (use big screens
  well, stay usable on a small laptop). **Mobile is out of scope.** (§7.3)
- **P0** One UI per root; **no multi-root switcher**, no cross-root registry.
  Show the root's filesystem path + origin/port in the chrome (don't act on the
  wrong server). A bundle **root-info command** reports the root's absolute path
  (for shell-here + honest paths). (§7.4)
- **P0** Posture: localhost-trusted, assumed + documented; UI adds no network
  policy but **warns on a non-local request**; strictly same-origin (**zero
  CORS**); **no auth** in v1. (§7.5)
- **P0** The **only** in-UI security boundary is **UI-integrity isolation**
  (sandboxed iframe for `text/html` + trusted toggle) — protecting the tool from
  hijack by command output, *not* sandboxing the user. (§7.5)

---

## B. URL / deep-link scheme

The framed UI rides on a single `parse-mode raw` command and re-uses the raw
resource URL verbatim — no double-encoding, no `?at=` wrapper.

| Purpose | URL | Notes |
|---|---|---|
| **Raw resource** (curl/`open`, no chrome) | `/<pipeline-or-path>` | Default §11.1 behavior. Always available; the no-JS / recovery floor. |
| **Framed view** (chrome) | `/ui/<same suffix>` | `ui` is a `parse-mode raw` bundle command (§10.7) that frames the suffix. Bookmarkable, shareable, `open(1)`-able. |
| Framed node | `/ui/notebook/0/3` or `/ui/notebook/pipes-question` | Ordinal or `c`-name; both resolve to the same node (§17.8). |
| Framed pipeline | `/ui/grep?-i "needle"/jq?.items[]/haystack.json` (sugar) → canonical `/ui/grep?arg=-i&arg=needle/jq?arg=.items%5B%5D/haystack.json` | Sugar is input-only; canonical is the stored artifact. |
| Explain / "what ran" | `/explain/<suffix>` | Dedicated bundle command; surfaced on-demand in chrome. |
| Shell here | `POST /term/<dir>` | Launches host terminal at `<dir>` (root for command results). |
| Editor helpers | `/commands`, `/names`, `/name-new…`, `/help`, root-info | Bundle commands; emit JSON the UI renders. |
| SDT append | `POST` to the append bundle command | Atomic allocation → `Created Node` → redirect to new node. |

**Where state lives** (§2.2, §11.4):

- **Path** = the resource / pipeline being acted on (the shareable thing).
- **Per-command query** (`?arg=…`) = real parameters that change the *server
  response*.
- **Fragment** (`#…`) = pure client view state (open panels, selection, scroll,
  focused tab). Never reaches the server (§11.4); cannot affect the pipeline.
- **Transient (not URL-addressable):** in-progress / unsaved edit buffers (lost
  on reload, honestly).

---

## C. MVP vs. later

**In MVP (P0/P1):**

- Notebook-mode thread view + secondary Files browser; live node-kind detection.
- SDT read (`a`/`b`/branches); **SDT append** (server-side alloc, auto-`b`,
  child + sibling, redirect-to-new).
- URL/pipeline input box + reversible query sugar + decode-preview.
- Response rendering matrix incl. sandboxed-iframe HTML; capped large output.
- First-class mutation: method control + resolved-path confirm + loud
  mutates badge; body via editor + upload.
- Authoring: commands (interpreter-rule executability, validating meta form,
  `env/path` auto-wire), `c` names (bundle commands, scope default + override,
  live preview, single target), edit-in-place PUT, plain-file rename-as-move.
- Name-resolution view (`sdt check --json` + live resolved-path, winner-only,
  quiet-inert, linter severities).
- Backing-files + shell-here on every page; raw/framed toggle.
- Dedicated `explain` command + runtime-diagnostic error pages.
- Editor autocomplete (commands + names) + structural `help`.
- Bundle: zero-build static + helper commands; additive-with-conflict install;
  re-droppable recovery + self-manifest warnings.
- Reference-impl hosting, graceful degradation, feature-detection.
- Dev-minimal look, auto light/dark, keyboard-first, desktop-responsive.
- One-UI-per-root, root identity in chrome, localhost posture, same-origin,
  no auth, UI-integrity isolation.

**Later (P2):**

- Natural-language "ask wash" assistant (model-backed TPC).
- Full-tree server-side content search command.
- Full backing-file provenance set (per-stage meta/exec/path) inline.
- `c`-name alternatives / multi-target authoring.
- Directory move, `sdt compact`, SDT node deletion (all shell-only for now).
- In-browser terminal (vs. launching the host terminal).
- Multi-impl host validation; multi-root switcher / known-roots registry.
- CLI→browser paste-to-navigate box (the clean-URL `open(1)` path covers the
  main need).
- Markdown/JSON/syntax-highlight renderers may start plain and grow.

---

## D. Open questions

1. **`b` provenance schema.** Rendered generically (key = first token) with
   `created`/`author` special-cased. Is there a *conventional* field set worth
   targeting (e.g. `command`, `source`, `model`), or stays freeform? (§4.2)
2. **`exec`-rule strategy for authored commands.** Default is per-command rules
   (e.g. `errors sh`) vs. extension rules (`*.py …`). Which does the
   command-authoring form prefer, and does it ever offer a `chmod` helper for
   shebang-style commands? (§5.2)
3. **Name scope default.** "Nearest enclosing dir" — need a precise rule for
   what counts as the enclosing *collection* in a notebook (the notebook root?
   the nearest dir with an existing `c`?). (§5.3)
4. **`term` command portability.** Host-terminal launch differs per OS
   (`open -a Terminal`, `$TERMINAL`, WSL…). What's the v1 support matrix, and
   what's the fallback when no terminal can be launched (copyable `cd`)? (§2.4)
5. **Non-local detection heuristic.** What signal flags "request didn't
   originate locally" reliably enough to warn without false alarms behind
   loopback proxies? (§7.5)
6. **Install conflict UX.** On an aborted merge, does the installer just report,
   or offer a guided manual-merge? (§7.1)
7. **Helper-command namespacing.** Exact names/paths for bundle helpers to
   minimize collision with a user's existing commands (and how the self-manifest
   is expressed). (§7.1, §6.2)

---

## E. specs/ + conformance vs. bundled app

**Ships as a bundled app — no spec, no conformance, no clause IDs.** The UI uses
only existing primitives (literal files, commands, `c` names, SDT layout, PUT/
POST/DELETE, optional `X-WebShell-*` headers). It is validated by ordinary
testing of the reference impl, not by the conformance harness.

**Two spec/conformance follow-ons the UI *motivates* (explicitly NOT part of the
UI's own v1 contract):**

1. **Standardize `explain`** (§16.8 leaves its name + output contract undefined).
   Because the UI now depends on `explain` in MVP, this is the **top candidate**
   to graduate into `specs/` + conformance: define the conventional command name
   and a JSON output schema. Until then, `explain` is bundle-private with a
   UI-private shape.
2. **Promote `X-WebShell-*` headers from "suggested" → required** (§11). The
   UI's backing-files (§6.1), resolved-path (§4.3), and "what ran" (§6.3) all
   lean on headers a conformant impl may currently omit. Making them required
   (with clause IDs + vectors) is what turns "the reference impl hosts the UI"
   into "every conformant impl hosts a fully-featured UI for free." The UI must
   still degrade gracefully until/unless this lands.

**Never spec'd:** the host-shell launch (`POST /term`) is OS/host-specific and
stays a pure bundle command.

If/when these two follow-ons are pursued, they follow the standard change-
propagation path: `specs/*.md` → clause IDs in `harness/conformance/spec.py` →
vectors → each impl (see `AGENTS.md` "Change Propagation").
