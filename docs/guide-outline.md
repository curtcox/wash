# The wash Programming Environment — Guide Outline

> An outline for a book-length guide to `wash` and its companion projects
> (SDT, TPC, gripeline), in the spirit of Kernighan & Pike's *The Unix
> Programming Environment* (1984).
>
> **Method, borrowed from TUPE.** Start at the keyboard, not the architecture.
> Introduce one idea at a time, always with a small *complete* example the
> reader can type and run. Let a single running project grow across chapters so
> that each new mechanism earns its place by solving a problem the reader just
> hit. Prefer "here is why it works this way" over "here is the rule." Keep the
> tone of two practitioners showing a colleague their environment.
>
> **The running example (our `hoc`).** TUPE grew a calculator, `hoc`, across the
> book. We grow a **lab notebook for a working programmer**: viewing a project's
> files, then searching and reshaping them with pipelines, then saving those
> pipelines as commands, then making the browser a real surface — rendering
> documents (Markdown), driving commands from forms (formdown), and navigating by
> relative link — then accumulating *results* as a navigable, human-nameable tree
> (SDT) whose nodes record how they were produced, then generating those trees
> from commands (TPC), then drawing and running the whole workflow as a graph
> (gripeline). By the last chapter the reader has a reusable, shareable,
> Git-tracked working environment built entirely from ordinary files, browsable
> in the address bar and replayable from the command line.
>
> **Scope decision (full ecosystem).** wash is the spine, but SDT, TPC, and
> gripeline are treated as co-equal members of one environment and are woven in
> from the middle of the book onward, not bolted on at the end.
>
> **Conventions used in the samples below**
> - `local` is the conceptual origin; in practice `http://localhost:PORT`.
> - A line like `GET /wc/notes.txt` is an HTTP request against the runtime.
> - `root/...` denotes a path inside the served project directory.
> - `≈ sh: ...` gives the approximate shell equivalent of a URL.
> - Samples are written to match the actual repo conventions
>   (`env/path`, `env/meta/<cmd>`, `exec`, ordinal SDT nodes, `Created Node`
>   manifests, `dot` graphs).

---

## Front Matter

- **Title page / colophon.** "The wash Programming Environment." Note that the
  book is itself a wash project: every figure is a file under a root, every
  pipeline is a real URL.
- **Preface.**
  - What this book is: a guide to *using* wash to build composable workflows,
    not a re-statement of the normative specs (`specs/runtime.md`,
    `specs/pipeline_parsing.md`). The specs are the law; this book is the
    apprenticeship.
  - Who it's for: programmers comfortable with a shell who want the same
    composability in the browser, on their own machine, over their own files.
  - The single-user stance, stated up front and without apology: *security,
    scalability, and multi-user concerns are explicit non-goals.* Why that
    constraint is liberating rather than reckless (it is your machine, your
    files, your OS permissions — the same trust model as your shell).
  - How to read it: type the examples. Keep a scratch root open.
  - A note on stability: wash is a work in progress; the book tracks the v1
    contract and flags where behavior is implementation-defined.
- **A map of the environment** (one-page diagram, reproduced as a gripeline
  graph later): browser/`curl` → wash runtime → root directory → commands →
  (optionally) SDT trees ← produced by TPCs; rendered documents and formdown
  forms as the browser-facing surface over the same commands; gripeline as the
  visual notation over the whole thing.

---

# Part I — Getting Started

## Chapter 1. wash for the Impatient

*Goal: a working runtime and a felt sense of "the browser is my shell" within
ten minutes.*

- **1.1 What problem wash solves.**
  - The everyday split: a shell gives you composition (`|`, paths, scripts) but
    no shareable surface; a web app gives you a shareable surface (URLs) but
    hides composition behind application UI.
  - wash's bet: make the *URL* almost as readable and reusable as a shell
    pipeline, pointed at files on the same machine as the browser.
  - The one example that says it all:
    ```
    GET /grep/needle/jq/haystack.json
    ≈ sh: cat haystack.json | jq | grep needle
    ```
- **1.2 Starting a runtime.**
  - One root, one origin, one server instance — the core mental model
    (runtime.md §4.1–§4.2).
  - First run against an empty directory (an empty root is valid):
    ```
    python -m wash.server --root ./notebook --port 8080
    ```
  - "Multiple projects → multiple servers." Why there's no multiplexing.
- **1.3 Your first three requests.**
  - View a file: `GET /notes.txt` → raw bytes of `root/notes.txt`.
  - Count it: `GET /wc/notes.txt`.
  - Write one: `curl -X PUT --data 'hello' local/greeting.txt`.
- **1.4 The browser and `curl` as equal citizens.**
  - Everything is an ordinary GET unless you say otherwise; the browser is a
    fine client, `curl` is a fine client (runtime.md §11.4).
  - Bookmarkable, shareable, inspectable: a URL *is* the saved workflow.
- **1.5 What we just relied on (forward pointers).** A quick list of the
  mechanisms about to be unpacked: literal file mapping, the command path,
  arity, the implied `cat` (Part II). And further out: rendering and forms as a
  browser surface (Part V), result trees with readable names and provenance
  (Part VI). Sets the table for the rest of the book.

## Chapter 2. The Root, the Filesystem, and the URL

*Goal: internalize "the filesystem is the immediate source of truth," the TUPE
"File System" chapter rendered for wash.*

- **2.1 URLs are paths.** Literal mapping: `GET /a/b/c.txt → root/a/b/c.txt`
  (runtime.md §6.1). The URL space *is* the directory tree until you ask for
  more.
- **2.2 Content types come from the file, then the root, then defaults.**
  - The four-step resolution order (suffix entry in `env/mime` → `default` line
    → built-in table → `application/octet-stream`) (runtime.md §6.1, §7.4).
  - Sample `root/env/mime`:
    ```
    .log    text/plain
    default application/octet-stream
    ```
- **2.3 Directories.** Index file vs. listing vs. 404 (runtime.md §6.5).
  - `root/env/index` to choose index names; empty file disables indexing.
  - `root/env/listing` holding exactly `on` or `off`.
  - Worked sample: same directory, three behaviors, toggled by two tiny files.
- **2.4 Writing and deleting plain files.** `PUT` creates/replaces, `DELETE`
  removes; both target the *literal* path and never trigger command parsing
  (runtime.md §9.2, §9.4). The contrast that surprises newcomers:
  `PUT /wc/file.txt` writes a file literally named `root/wc/file.txt`.
- **2.5 GET never mutates — a contract, not a convention** (runtime.md §9.1,
  §13.2). Why this single rule makes the browser safe to point at your files.
- **2.6 Staying inside the root.** Dot-segment normalization, rejection of
  escaping paths, the default "reject escaping symlinks" policy
  (pipeline_parsing.md §9.1). What "the root is not a hard sandbox for *command
  search*" does and doesn't mean.
- **Exercises.** Serve a small static site from a root; flip `env/listing`;
  add a `.log → text/plain` rule and observe the change.

---

# Part II — The URL as a Command Line

## Chapter 3. Commands and the Command Path

*Goal: the moment a path segment stops being a file and becomes a verb.*

- **3.1 What makes a segment a command.** A command is just a file found on the
  command search path; "command" is not a reserved word (runtime.md §4.4). The
  shell-PATH analogy made explicit.
- **3.2 `env/path`: the search path.** Line-oriented, may point outside the root
  (runtime.md §7.1). Sample:
  ```
  bin
  vendor/bin
  ../shared/bin
  ```
- **3.3 Our first command.** A real `root/bin/wc`-style script (modeled on the
  repo's fixture commands), read from stdin:
  ```sh
  #!/bin/sh
  # root/bin/count — lines, words, bytes of stdin
  exec wc
  ```
  Then `GET /count/notes.txt ≈ sh: cat notes.txt | wc`.
- **3.4 The implied `cat`.** The rightmost suffix is fed in by a runtime
  primitive, not a PATH command; a user-defined `cat` does not change it
  (pipeline_parsing.md §4). Why there is no `cat` segment in the URL.
- **3.5 Exact files win first: the precedence ladder.** Exact filesystem
  resource → command parse → synthesized resource → 404 (runtime.md §6.2,
  pipeline_parsing.md §9.5). Walk the classic case:
  - `/wc` when `root/wc` exists as a file → the file is served.
  - `/wc/foo.txt` when no `root/wc/foo.txt` exists → `wc` runs.
- **3.6 No command lookup inside directory traversal.** `/docs/grep/needle/x`
  when `/docs` is a real directory and the full path is missing → 404, *not* a
  pipeline (pipeline_parsing.md §9.2). The rule that keeps file browsing
  predictable.
- **Exercises.** Add `bin` to `env/path`; shadow a file with a command and
  observe the ladder; reach a command's own source via its literal path.

## Chapter 4. Arguments and Arity

*Goal: where a command's arguments end and its input begins — the single most
important parsing idea in wash.*

- **4.1 The default is arity 0.** A metadata-free command takes *no* path
  arguments and reads stdin (pipeline_parsing.md §4). This is the rule that
  trips up shell users, so it is taught first and loudly.
- **4.2 The canonical "wrong" URL.**
  ```
  GET /wc/-l/notes.txt        → 400 Bad Request   (wc is metadata-free)
  ```
  Why: `-l` is an unexpected segment, because `wc` consumes zero arguments
  (pipeline_parsing.md §13.1).
- **4.3 Two ways to fix it.**
  - Query argv (no metadata needed): `GET /wc?arg=-l/notes.txt`
    (pipeline_parsing.md §6.1).
  - Declared arity (metadata): give `grep` arity 1 and write
    `GET /grep/needle/notes.txt ≈ sh: cat notes.txt | grep needle`.
- **4.4 Declaring arity.** `root/env/meta/grep`:
  ```
  arity 1
  ```
  Boundaries are determined by arity *alone*, never by guessing which segments
  look like commands (runtime.md §10.3, pipeline_parsing.md §7).
- **4.5 Arguments are opaque strings.** Passed verbatim, never resolved to file
  contents; may even contain a decoded `/` via `%2F` (pipeline_parsing.md §5.1).
  Only the implied-cat suffix is read as bytes.
- **4.6 Fixed N, and `arity *`.** `arity *` swallows the rest of the URL as argv,
  leaving no input suffix (pipeline_parsing.md §5.2). Range forms are reserved
  and treated as malformed in v1.
- **4.7 Multi-resource commands without an "input file" mode.** `diff` with
  `arity 2`: both names arrive as argv and `diff` opens them itself, relative to
  the root working directory (runtime.md §10.5, §12.3):
  ```
  GET /diff/a.txt/b.txt ≈ sh: diff a.txt b.txt
  ```
- **Exercises.** Convert a metadata-free `grep` into an arity-1 grep; express
  the same pipeline two ways (query argv vs. metadata).

## Chapter 5. Per-Command Query Strings

*Goal: the escape hatch for flags, named arguments, and disambiguation.*

- **5.1 A URL may carry more than one `?`.** Each query attaches to its own
  command segment; valid per RFC 3986 §3.4, parsed directly from the raw
  request-target (runtime.md §4.7, §12.2).
- **5.2 The one reserved core parameter: `arg`.** Repeatable, ordered
  (pipeline_parsing.md §6.1):
  ```
  GET /grep?arg=-i&arg=needle/file.txt ≈ sh: cat file.txt | grep -i needle
  ```
- **5.3 Command-specific parameters are the command's business.** `pattern=`,
  `filter=`, `ignore-case=` are interpreted by the command, not the core parser
  (runtime.md §8.5). When to prefer them over positional `arg`.
- **5.4 Query argv disables metadata arity.** Using `arg` makes a command consume
  zero path segments; following segments become pipeline/input
  (pipeline_parsing.md §6.2). The interaction shown as a before/after.
- **5.5 `arg` only attaches to a real command segment.** `/grep/-i?arg=needle/x`
  → 400 (pipeline_parsing.md §6.3). Diagnose and rewrite.
- **5.6 Encoding rules inside queries.** Literal `/ ? & =` must be
  percent-encoded; a query ends at the next raw `/` (pipeline_parsing.md §6).
- **5.7 The trailing-`?` special case.** A `?` in the final segment with no `/`
  after it is an ordinary-resource query first (`/file.txt?download=1` can match
  the file); a `?` with any `/` after it is always per-command syntax
  (pipeline_parsing.md §9.1).
- **Exercises.** Build the same JSON query two ways; trigger and read a 400;
  pass a pattern containing `/`.

---

# Part III — Pipelines: The Heart of wash

*This is the "Filters" chapter of TUPE, expanded — composition is wash's reason
to exist.*

## Chapter 6. Building Pipelines

- **6.1 Two directions at once.** Resolution is left-to-right; data flows
  right-to-left (runtime.md §10.1). The diagram that makes it click, with a
  worked trace of `/grep/needle/jq/haystack.json`.
- **6.2 Known commands inside the suffix create stages** (pipeline_parsing.md
  §7). Each recognized command is another `|`.
- **6.3 Longer pipelines, fully worked.**
  ```
  GET /wc/-l/grep/needle/jq/.items%5B%5D/haystack.json
  ≈ sh: cat haystack.json | jq '.items[]' | grep needle | wc -l
  ```
  with `wc`, `grep`, `jq` each `arity 1`; and the same URL's **400** when all are
  metadata-free (pipeline_parsing.md §12.4, §13.2). The lesson: metadata is what
  turns a flat URL into a pipeline.
- **6.4 Argument/command collisions.** `/grep/jq/haystack.txt` with `grep`
  arity 1 → `jq` is a literal pattern, not a stage (runtime.md §8.6). When the
  parser cannot help you, *define a clearer command* (`/find_jq/...`)
  (runtime.md §8.7).
- **6.5 Directories as pipeline input.** `/wc/docs` cats a directory path and
  lets the command fail or succeed naturally; HTTP directory behavior does not
  apply to a pipeline suffix (pipeline_parsing.md §9.4).
- **Exercises.** Reproduce the four-stage example; deliberately collide an
  argument with a command name and fix it by defining a command.

## Chapter 7. Standard Error and the `/&` Boundary

- **7.1 By default stderr stays out of the body** (runtime.md §15.4). It may
  still be captured for diagnostics — "discard" means the response stream only.
- **7.2 The `/&` prefix.** Written on the *downstream* command segment; merges
  exactly one boundary, analogous to shell `|&` (runtime.md §8.8,
  pipeline_parsing.md §8):
  ```
  GET /wc/-l/&grep/error/file.txt
  ≈ sh: cat file.txt | grep error |& wc -l
  ```
- **7.3 One boundary, not a mode.** `/count/&filter/&noisy/file.txt` — each `/&`
  marks only its own boundary (pipeline_parsing.md §8). The `/&` on the rightmost
  stage marks its output-leftward connection, never the implied-cat input
  (pipeline_parsing.md §8, example `/wc/&grep/file.txt`).
- **7.4 The metadata equivalent: `stderr merge`.** Same single-merge effect as a
  `/&` prefix on that stage's output boundary (pipeline_parsing.md §5.9).
- **7.5 Commands literally named `&`.** Percent-encode the leading `&` as `%26`
  (pipeline_parsing.md §8.1). A rare gotcha, noted for completeness.
- **Exercises.** Capture a noisy command's diagnostics into the body two ways
  (URL token and metadata); confirm only one boundary is affected.

## Chapter 8. Exit Status and HTTP Status

- **8.1 The default mapping.** exit 0 → 200, nonzero → 400 (runtime.md §15.3,
  pipeline_parsing.md §5.4).
- **8.2 When nonzero is normal.** `grep` exits 1 on "no match." Remap it:
  ```
  # root/env/meta/grep
  arity 1
  exit 0=200 1=404 *=400
  ```
- **8.3 The `exit` grammar.** `code=status` pairs; explicit code beats `*`; an
  unmatched nonzero with no `*` falls back to 400 (pipeline_parsing.md §5.4).
- **8.4 Pipefail across stages.** Every stage is mapped; the first failing stage
  *in URL order* (the most downstream stage) wins — exactly shell
  `set -o pipefail` (pipeline_parsing.md §5.4, §10.3). Worked example with two
  failing stages.
- **8.5 What a good error body contains.** Command, exit status, sanitized
  stdout/stderr (≤8 KiB default, truncation flagged), effective pipeline;
  content-negotiated as text or JSON via `Accept` (pipeline_parsing.md §10.3,
  §10.5).
- **Exercises.** Make `grep`-no-match return 404; build a two-stage failure and
  predict the status before running it.

---

# Part IV — Writing and Reusing Commands

## Chapter 9. Anatomy of a wash Command

*Goal: the reader can write, install, and debug their own commands fluently.*

- **9.1 A command is an ordinary file.** Shell script, Python, binary, symlink,
  or a plain file run via an interpreter rule; no exec bit or shebang required
  (runtime.md §4.4, §4.6).
- **9.2 The execution contract.** Child process per request; cwd is the root;
  argv are the literal argument segments; stdin is the evaluated suffix or the
  request body or empty (runtime.md §12.3–§12.4). The "commands see only their
  local arguments" principle.
- **9.3 stdin / stdout, the common case.** A complete filter, end to end:
  ```sh
  #!/bin/sh
  # root/bin/upper — uppercase stdin
  exec tr '[:lower:]' '[:upper:]'
  ```
  `GET /upper/notes.txt`.
- **9.4 Setting output type.** `mime` in metadata for the final stage; or emit a
  full HTTP response to control status/headers (runtime.md §12.5,
  pipeline_parsing.md §5.8).
- **9.5 Reading the request body.** `POST /grep/needle/sort` with a body →
  `sort` reads the body on stdin (runtime.md §10.6). Suffix beats body when both
  are present.
- **Exercises.** Write `upper`; add a `mime text/plain`; write a body-consuming
  command.

## Chapter 10. Interpreter Rules (`exec`)

- **10.1 Why `exec` exists.** Run command files that are not directly
  executable, lack a shebang, or need an external interpreter (runtime.md §7.2).
- **10.2 Grammar and matching.** `<pattern> <interpreter> [args...]`, first match
  wins; bare patterns match the basename; glob patterns (`* ? []`) match
  basename and relative path (runtime.md §7.2). Sample, mirroring the fixtures:
  ```
  # root/exec
  *.py  /usr/bin/python3
  grep  sh
  ```
- **10.3 Comments, whitespace, and the no-quoting rule.** Inline `#` is not a
  comment; whitespace-significant; quoting is out of scope in v1 (runtime.md
  §7.2).
- **10.4 Failure modes.** Unresolvable interpreter → 500; a malformed rule makes
  the whole file invalid → 500 for requests that need it (runtime.md §7.2,
  §15.5).
- **Exercises.** Run a `.py` command with no shebang; break a rule on purpose and
  read the 500.

## Chapter 11. Command Metadata in Depth

- **11.1 The file and its grammar.** `root/env/meta/<command>`, line-oriented;
  blanks and `#` comments ignored; last duplicate wins; unknown fields ignored;
  malformed *recognized* value → 500 (runtime.md §7.3, pipeline_parsing.md §5.5).
- **11.2 The normative field list.** `arity input output methods mime mutates
  parse-mode stderr exit` (pipeline_parsing.md §5.6). A reference table, each
  with default and one-line effect.
- **11.3 `input`/`output`.** v1 defines only `stdin`/`stdout`; `input file`,
  `input none`, `output file` are reserved and currently → 500
  (pipeline_parsing.md §5.3). Why wash deliberately keeps the surface tiny.
- **11.4 `methods` and `mutates`.** Default `GET`, `mutates false`; every stage
  must permit the request method; GET that declares `mutates true` is invalid
  metadata → 500 (runtime.md §9.5, pipeline_parsing.md §5.7). The safety
  invariant restated.
- **11.5 A complete mutating command.** Modeled on the repo's `sort` fixture:
  ```
  # root/env/meta/sort
  methods POST
  mutates true
  arity 1
  ```
  with `POST /sort/output.txt/input.txt` and the warning that output redirection
  is *command-specific*, not a core feature (runtime.md §9.3, §16.7).
- **11.6 Metadata as documentation.** Plain text, Git-diffable; reading a root's
  `env/meta/*` tells you what the project's verbs do.
- **Exercises.** Add a `mime`; convert a filter into a POST mutator; trigger each
  500 case once to learn its shape.

## Chapter 12. Commands That Read the URL: `parse-mode raw`

- **12.1 The idea.** Some commands operate on the *expression*, not its result —
  the leftmost command consumes the still-encoded suffix and parsing stops
  (runtime.md §10.7, pipeline_parsing.md §5.7).
- **12.2 `explain`, the motivating case.**
  ```
  # root/env/meta/explain
  parse-mode raw
  GET /explain/grep/needle/jq/haystack.json   → explains; grep/jq do NOT run
  ```
  Note: `explain` is *optional* in v1; there is no required name or output format
  yet (runtime.md §16.8).
- **12.3 Rules and limits.** Raw-parse is only valid leftmost; elsewhere → 500
  (pipeline_parsing.md §5.7). A raw command is a parser, a formatter, a linter —
  anything that wants the text.
- **12.4 Execution-metadata headers.** `X-WebShell-Command`,
  `X-WebShell-Pipeline`, `X-WebShell-Source` as a non-raw way to inspect what
  ran (pipeline_parsing.md §11). Build a tiny "what did that do?" workflow.
- **Exercises.** Write a `linkify` raw command that turns a pipeline URL into an
  HTML page of clickable sub-pipelines.

## Chapter 13. Reuse: Aliases, Saved Expressions, and Project Vocabulary

*Goal: the TUPE "Shell Programming" turn — from running commands to building a
vocabulary.*

- **13.1 Aliases are just commands on the path** (runtime.md §14.1):
  ```sh
  #!/bin/sh
  # root/bin/errors — show error lines of a log
  exec grep -i error
  ```
  `GET /errors/logs/app.log`.
- **13.2 Composing commands from commands.** A command whose body is itself a
  small pipeline; the reuse pattern wash is built to encourage.
- **13.3 Saved URL expressions.** A `root/saved/errors.url` file is just a file
  until placed on the path with an interpreter (runtime.md §14.2). The pattern
  for "bookmark a workflow as a file."
- **13.4 The design discipline: name your verbs.** Echoing §8.7 — ambiguity is a
  signal to define a clearer command, not to memorize parser edge cases.
- **13.5 Sharing a root through Git.** Plain text, line-oriented config, explicit
  files; portability is "frequent but not guaranteed"; adding a cloned `bin/` to
  `env/path` is exactly like extending your shell `PATH` — powerful and
  dangerous (runtime.md §13.3, §14).
- **Exercises.** Turn the four-stage pipeline from Chapter 6 into a single named
  command; commit the root and clone it elsewhere.

---

# Part V — The Browser as a Surface

*Until now the browser has been a thin client: it shows bytes and follows links.
This part makes the browser a **surface** — documents that render, forms that
act, links that navigate a project — without giving up the rule that a URL is
still just a path or a pipeline. None of this is new runtime machinery: rendering
and forms are ordinary commands (Part IV) and links are ordinary URLs. This is
where "the browser is my shell" becomes "the browser is my shell **and** my
notebook page," and where the round trip to the command line stays honest.*

## Chapter 14. Rendering Documents: Markdown and Beyond

*Goal: turn raw files into readable pages without leaving the file model.*

- **14.1 Raw bytes vs. a rendered view.** `GET /notes.md` returns the file as
  `text/markdown` (runtime.md §6.1 mime table); *rendering* is a command, not a
  runtime feature. The file stays the source of truth; rendering is a lens over
  it. The two URLs coexist: `/notes.md` (read the source) and `/render/notes.md`
  (read the page).
- **14.2 The `render` command pattern.** A command that reads Markdown on stdin
  and emits HTML, declaring `mime text/html` for its stage (Chapter 9 §9.4,
  runtime.md §12.5). Modeled on the book's own `book/bin/render`:
  ```
  GET /render/ch01.md   ≈ sh: cat ch01.md | render
  ```
- **14.3 Offering both surfaces is the wash way.** Same file, two URLs: source
  for transparency, rendered for reading. A rendered page links back to its own
  raw form, and vice versa — nothing is hidden, presentation is additive.
- **14.4 Rendering generalizes.** A `view` command that dispatches by suffix
  (Markdown → HTML, JSON → pretty HTML, `.dot` → an SVG via gripeline, an SDT
  node → a formatted card). One small renderer per format, each composable like
  any other stage; reach for a clearer command rather than a cleverer one
  (echoing §8.7).
- **14.5 The book is a wash project.** The chapter you are reading is
  `book/ch01.md`, served raw and rendered by exactly these mechanisms; every
  figure is a real file under a root (callback to the colophon). Rendering is how
  a project documents *itself* from inside.
- **Exercises.** Write a Markdown `render`; add a suffix-dispatching `view`; serve
  one document both raw and rendered and cross-link the two.

## Chapter 15. formdown: Forms as the Interface to Commands

*Goal: a zero-to-light-JS interactive surface where filling in a form runs a
pipeline.*

- **15.1 The problem.** A rendered document can *show* results, but a notebook
  needs *input*: ask a question, set a flag, name a node. The browser already has
  the control for this — the HTML form — but hand-writing forms and wiring each
  to a pipeline is tedious and easy to get subtly wrong.
- **15.2 The formdown idea.** Markdown extended with form fields. A formdown
  document renders (via a renderer, Chapter 14) to an HTML form whose submission
  is an *ordinary wash request* — a `GET` or `POST` to a pipeline assembled from
  the field values. formdown is a **book-defined authoring format layered on
  commands, not a runtime feature**; the runtime sees only the resulting request.
- **15.3 A field maps to argv, a path segment, or the body.** How each control
  becomes a query `arg` (Chapter 5 §5.2), a path argument under a declared arity
  (Chapter 4), or the request body (Chapter 9 §9.5). The form's `action` is a
  wash URL; its `method` must satisfy the command's declared `methods`
  (Chapter 11 §11.4):
  ```
  <!-- ask.formdown -->
  # Ask the notebook
  question: [_______________]      → POST /ask        (body = question)
  pattern:  [_____]  ignore-case ☐ → GET  /grep?arg=…  (argv from fields)
  ```
- **15.4 A submission is a request you could have typed.** The defining property:
  a formdown submit produces exactly the URL (and body) you would build by hand —
  the form is a convenience over the URL, never a hidden side channel. You can
  inspect it, bookmark it, and replay it with `curl` (forward link to §16.6).
- **15.5 Forms that drive TPCs.** When a form's action is a tree-producing command
  (Chapter 18), submitting it is how a conversation takes its next turn — this is
  the seam from this part into Part VI. Where the response goes (the new leaf) is
  the adapter/PRG question handled in Chapter 18; on a runtime without
  command-issued redirects it is a small client-side hop (see authoring notes).
- **15.6 Progressive enhancement, single-user style.** A bare `<form>` works with
  zero JavaScript because the submission is just a request; light JS only adds
  redirect-to-new-leaf and live result panels. Your machine, one user — keep the
  surface thin and the request legible.
- **Exercises.** Write an `ask.formdown` that POSTs a question and appends a node;
  build a form that assembles a two-stage pipeline from two fields; submit the
  same action by hand with `curl` and confirm it is byte-identical.

## Chapter 16. Links, Navigation, and the Browser as Tree Viewer

*Goal: move through a project — files, pipelines, and result trees — by clicking,
and carry the same workflow back and forth to the command line.*

- **16.1 A link is a URL is a path-or-pipeline.** Relative links resolve against
  the current request path by ordinary URL rules (RFC 3986 §5); because wash URLs
  *are* paths, clicking through a project *is* walking the directory tree. The
  browser's address bar is a prompt; the page is the output.
- **16.2 Relative links inside rendered documents.** A link in a rendered
  Markdown/formdown page can point at a sibling file, a command, or a whole
  pipeline — the document becomes a launchpad. Authoring links so a moved or
  cloned root still resolves: prefer root-relative links for stability (callback
  to §13.5 Git sharing). *(documents → pipelines)*
- **16.3 What a relative link resolves against under a pipeline.** The subtle
  case: when the current URL is itself a pipeline
  (`/grep/x/jq/y/data.json`), a relative link resolves against the *request path*
  per RFC 3986, **not** against any command segment — there is no "current
  command directory." The discipline: link to files and roots, not into the
  middle of a pipeline; use root-relative links when in doubt. *(Flag: exact
  base-URL behavior for pipeline requests is implementation-defined / not yet
  normatively specified — state the discipline, not one server's rule.)*
- **16.4 Navigating an SDT tree by link.** Node → child (`/0/0/0`), node → parent
  (`..`), node → sibling (`../1`); a directory listing or a small `view` command
  (Chapter 14) turns an SDT tree into a clickable conversation or experiment
  browser. Human-readable names (Chapter 17 §17.8) make these links readable
  instead of ordinal soup. *(between SDT nodes)*
- **16.5 The browser as command shell *and* tree viewer at once.** Type a pipeline
  in the address bar to run it; click a listing to browse results; a bookmark is
  a saved command (callback to §13.3 saved expressions). The same window is both
  REPL and file browser.
- **16.6 Moving back and forth with the command line.** Every URL is a `curl`
  invocation and back again: copy a pipeline from the address bar into a terminal,
  or paste a constructed URL into the browser. The `X-WebShell-*` execution
  headers and a `parse-mode raw` explainer (Chapter 12) let you see what a clicked
  link *would* run before running it — the safe bridge between pointing and
  shooting. Round-trip a workflow: address bar → `curl` → saved command
  (Chapter 13) → bookmark.
- **Exercises.** Build an index page of relative links into an SDT tree; click
  from a rendered doc straight into a four-stage pipeline; take a URL from the
  browser, run it with `curl`, then save it as a named command and bookmark it.

---

# Part VI — Trees of Results: SDT and TPC

*Here the ecosystem widens. wash gives us composition over files; now we want to
**accumulate** results — histories, conversations, explored alternatives — as
navigable structure. This is the book's "big program" arc, the equivalent of
TUPE growing `hoc`.*

## Chapter 17. The Sequential Directory Tree (SDT)

- **17.1 The problem.** Pipelines are ephemeral (runtime.md §9.7). But a lab
  notebook wants to *keep* results, ordered, branchable, and diffable — without
  inventing a database (a wash non-goal, runtime.md §3).
- **17.2 The SDT idea.** A tree of *unnamed* files laid out by ordinal directory
  names: `0`, `1`, …, then `A`, `B`, … — a dense, sortable address space.
- **17.3 Node anatomy.** `a` holds the node's text; an optional `b` holds
  metadata; child directories are the next ordinals. A worked tree:
  ```
  root/
    0/
      a            # "Hello."
      0/
        a          # "What is 2+2?"
        0/
          a        # "4"
          b        # created 2026-06-19T14:00:00Z
  ```
- **17.4 Sidecars and portability.** `.0` sidecar files track state and let
  `sdt check` verify a tree is well-formed and portable.
- **17.5 The `sdt` tool, by verb.** `code` (encode/decode/validate indices),
  `read` (classify entries), `check` (verify sidecars/portability *and* lint
  name resolution per `tools/sdt/` — cycles and dangling targets are errors,
  escapes and malformed `c` lines warnings), `sidecar`, `name` (next ordinal —
  distinct from the human-name `c`-file layer of §17.8), `add` (write a node),
  `compact` (densify ordinals), `pack` (bundle/extract). One tiny example per
  verb.
- **17.6 Why ordinals instead of names.** Stable addresses, cheap appends,
  natural branching; the same reason URLs in wash are paths.
- **17.7 SDT *through* wash.** Because a tree is just files, a wash root can
  serve it directly: `GET /0/0/a` returns a node's text; a listing browses the
  tree. SDT needs no special runtime support — it rides on Chapter 2.
- **17.8 A human-readable naming layer over ordinals.** Ordinals are stable
  addresses but unreadable, so a *names* layer maps readable names to ordinal
  paths **without moving the nodes**. This is settled, normative behavior:
  name resolution is specified in `runtime.md` §6.6 and implemented in the
  reference server. The mechanism is a directory's `c` file — the §5.5 metadata
  line grammar, one `name target...` entry per line — mapping a human name to a
  target path. Resolution is universal (every root) and consulted only on a
  literal-child miss, so real entries (including the reserved `a`/`b`/`c` and
  symlinks) always shadow names; it is prefix-scoped, nearest-(deepest)-scope
  winning, and a resolved name jumps the walk to its target as if the URL had been
  the target path. A name is usable directly in a URL for any method (GET/HEAD/
  POST/DELETE resolve; PUT overwrites a resolved existing target, else creates
  literally), so `/notebook/pipes-question` resolves to `/notebook/0/3`.
  Distinguish two senses of "name": `sdt name` (§17.5) allocates the next
  *ordinal*; the `c`-file layer maps a human name to an *existing* ordinal path —
  an indirection, like a bookmark or a symlink. Properties: the ordinal tree
  stays the ground truth; names are an additive overlay, may be many-to-one
  (targets are alternatives tried in order), and can be added, changed, or dropped
  without rewriting history (a name is metadata, not structure). Targets may be
  root-relative, node-relative, or chained (name→name to a fixpoint); name and
  symlink hops share one depth budget (508 on overflow/cycle, 404 dangling), and
  escapes leaving the root are governed by the `escape_policy` capability
  (default `reject-escaping` → 403). Provenance is reported via the
  `X-WebShell-Resolved-Path` header. Relative links (§16.4) written against names
  read as prose instead of ordinal soup.
- **Exercises.** Build a three-node tree by hand; `sdt add` a fourth; `sdt
  compact`; add a `c`-file entry giving one node a human-readable name and reach
  it both ways (by name and by ordinal path); serve the tree from a wash root and
  navigate it in the browser.

## Chapter 18. Tree-Producing Commands (TPC)

- **18.1 The bridge.** A TPC is *a wash command that writes node files into an
  SDT tree and emits a `Created Node <path>` manifest on stderr.* It joins
  Chapter 9 (commands) to Chapter 17 (trees).
- **18.2 The shape of a TPC.** POST-only, `mutates true`, takes a target node as
  context, writes a response subtree beneath it:
  ```
  # root/env/meta/ask
  methods POST
  mutates true
  parse-mode raw        # or arity, depending on how the target is addressed
  ```
- **18.3 A turn.** One POST = an input node plus the response subtree written
  under it. Worked end to end:
  ```
  POST /tree/0
  Content-Type: text/plain

  What is 2+2?
  ```
  resulting tree and the manifest:
  ```
  Created Node 0/0
  Created Node 0/0/0
  ```
  "The last marker line names the redirect leaf."
- **18.4 Continuations and alternatives.** *Continuation* = a reader-level gloss
  over successive nodes sharing an `author` metadata value (not structural);
  *alternatives* = sibling branches (≥2 children) recording explored variations.
  How a notebook grows a tree of tries.
- **18.5 HTTP-ignorance by design.** A TPC knows nothing about HTTP; a separate
  *adapter* command consumes the stderr manifest to synthesize a
  Post/Redirect/Get response and cache headers. Keep the producer pure
  (runtime.md §6, §10 referenced by the TPC spec).
- **18.6 "The LLM is not special."** Deterministic TPCs (`wc`, a shell command)
  and nondeterministic ones (a model call, an Eliza script) are treated
  identically — same contract, same manifest. Why this uniformity matters for
  reproducibility and testing.
- **18.7 Our notebook becomes a workspace.** Wire `ask` + an adapter so that
  posting a question appends a node and redirects the browser to the new leaf —
  a conversation, command history, or experiment log that *is* a directory tree.
  The input itself can come from a formdown form (§15.5): submit the form, take a
  turn, land on the new leaf.
- **18.8 Tracing a node back to what made it.** Provenance is not new machinery —
  it is the node's `b` metadata (§17.3) and the `Created Node` manifest (§18.3)
  read together. A well-behaved TPC records in `b` the command, the *effective
  pipeline*, the input node(s), and a timestamp, so any node can answer "what
  command, over what data, produced me?" The `X-WebShell-Command` / `-Pipeline` /
  `-Source` headers (§12.4) carry the same facts at request time. Because both are
  plain text under the root, lineage is greppable and Git-diffable, never hidden
  state — the provenance face of "the LLM is not special" (§18.6): deterministic
  and nondeterministic producers leave the identical trail.
- **Exercises.** Write a deterministic TPC (`echo`-as-node); add an adapter that
  redirects to the leaf; have the TPC record its command and inputs into `b`;
  branch an alternative and view both in the browser.

## Chapter 19. Patterns for Accumulating and Tracing Work

*Synthesis chapter: SDT + TPC + wash composition as one discipline.*

- **19.1 Append-only thinking.** Results accumulate; you navigate history by URL.
- **19.2 Branching to explore.** Alternatives as siblings; comparing two leaves
  with a wash `diff` command (Chapter 4) over their `a` files.
- **19.3 Reading a tree back.** `sdt read` for classification/stats; serving the
  tree for human browsing; pipelines *over* node text (`/grep/TODO/0/3/a`).
- **19.4 Git as the time machine.** SDT trees are plain files; commit them, diff
  them, share them — the persistence story from Chapter 13 applied to results.
- **19.5 Tracing lineage end to end.** Put the provenance trail (§18.8) to work:
  walk a leaf up its parents reading each `b`, or write a `trace` command (a
  `view`, Chapter 14) that renders a node's full ancestry — command, inputs,
  output, names (§17.8) — as one page. "How did this result get here?" becomes a
  link you follow, not an excavation. Provenance plus naming is what keeps an
  accumulating tree legible as it grows.
- **Exercises.** Build a small experiment log with three branches and write a
  one-command "show me all leaves containing X"; add a `trace` command that prints
  a leaf's full lineage from its `b` metadata.

---

# Part VII — Seeing the Whole: gripeline

## Chapter 20. A Graph Is a Pipeline

- **20.1 The motivation.** Long linear pipelines (URL or shell) get hard to read;
  a graph shows data flow at a glance. gripeline's thesis: *the same file you
  draw is the file you run.*
- **20.2 The notation.** A Graphviz `dot` digraph where nodes carry commands:
  ```
  digraph {
    a [label="cat access.log"]
    b [label="grep 404"]
    c [label="wc -l"]
    a -> b -> c
  }
  ```
  ≈ `cat access.log | grep 404 | wc -l`.
- **20.3 The three verbs.** `gripeline build foo.dot` (emit bash), `run` (emit +
  execute), `check` (static validation/executability). One example each.
- **20.4 What gripeline validates.** Node-role resolution, static checks before
  execution — catch a broken graph before it runs.
- **Exercises.** Draw the Chapter 6 four-stage pipeline as a graph; `build` it;
  `run` it; render it with `dot -Tpng`.

## Chapter 21. gripeline and wash Together

- **21.1 Two surfaces for one pipeline.** The URL form is great for ad-hoc and
  bookmarking; the graph form is great for branching, documentation, and review.
  Map a wash pipeline URL to its gripeline graph and back, side by side.
- **21.2 Visualizing wash workflows.** Treat a saved URL expression (Chapter 13)
  and a `.dot` graph as two encodings of the same workflow; when to reach for
  which.
- **21.3 Branching graphs vs. linear URLs.** Where graphs earn their keep:
  fan-out/fan-in that a single left-to-right URL cannot express cleanly.
- **21.4 Serving and running graphs through wash.** A `gripeline` command on the
  path so `GET /gripeline/check/flow.dot` validates and `POST /gripeline/run/...`
  executes — visualization and execution behind ordinary URLs.
- **Exercises.** Build a branching graph, validate it through a wash command, and
  render the diagram into the project's served docs.

---

# Part VIII — Putting It All Together

## Chapter 22. A Complete Project: The Lab Notebook

*The capstone, in TUPE's "build something real" spirit — every prior mechanism
appears once, in service of one coherent root.*

- **22.1 The root layout.** A single annotated tree showing `env/path`,
  `env/meta/*`, `exec`, `env/mime`, `bin/` commands, an SDT `tree/`, and `.dot`
  graphs — the whole environment on one page.
- **22.2 Day in the life.** A narrative sequence of real requests: browse files →
  search with a pipeline → save it as a command → POST a question that appends an
  SDT node via a TPC → branch an alternative → draw the workflow as a graph and
  run it → commit everything to Git.
- **22.3 Reuse audit.** Trace how each command reuses earlier ones; show the
  dependency graph (as a gripeline diagram, naturally).
- **22.4 Sharing it.** Clone the root elsewhere; what travels, what is
  machine-local (interpreters, binaries), and how to tell (runtime.md §14).

## Chapter 23. Debugging and Diagnostics

- **23.1 Reading status codes as a language.** 400 (your URL), 404 (nothing
  there), 405 (wrong method), 500 (the *project's* config is wrong) — a decision
  table (runtime.md §15, pipeline_parsing.md §10).
- **23.2 "Why did my pipeline not parse?"** The arity-0 trap, command/argument
  collisions, `arg` on a non-command segment — each with the fix.
- **23.3 Inspecting without running.** `parse-mode raw` explainers and
  `X-WebShell-*` headers (Chapter 12).
- **23.4 Malformed-config 500s.** Bad `exec`, bad `env/meta`, bad `env/mime`,
  bad `env/index`, bad `env/listing` — find them fast.
- **23.5 SDT/TPC pitfalls.** Non-dense ordinals (`sdt compact`), missing/extra
  sidecars (`sdt check`), a TPC that forgets its manifest line.

## Chapter 24. The wash Way (Epilog)

*The TUPE epilog, restated for wash.*

- **24.1 Small pieces, composed.** The Unix philosophy, relocated to URLs and the
  browser.
- **24.2 The filesystem as the only database.** Why plain files beat hidden state
  for a single user (runtime.md §3, §14).
- **24.3 Transparency as a feature.** A URL you can read is a workflow you can
  trust, share, and modify; commands can still shadow behavior, just like a
  shell (runtime.md §5, "Transparent URL").
- **24.4 Constraints that liberate.** No multi-user, no sandbox, no package
  manager — and how dropping those let wash stay legible.
- **24.5 Where wash is going.** A measured note on v1's reserved-but-undefined
  surface (range arity, `input file`/`output file`, synthesized-resource
  discovery, a standardized `explain`) and the project's "work in progress"
  status — pointers, not promises (runtime.md §19, pipeline_parsing.md §15).

---

# Appendices

- **Appendix A — Quick reference: the precedence ladder.** Exact file → command
  parse → synthesized → 404, with the PUT/DELETE "literal path only" carve-out
  (runtime.md §6.2, §9.2, pipeline_parsing.md §9.5).
- **Appendix B — Metadata field reference.** Every field, default, legal values,
  and the malformed → 500 rule, in a single table (pipeline_parsing.md §5).
- **Appendix C — `env/` file reference.** `path`, `meta/<cmd>`, `mime`, `index`,
  `listing`, and the root `exec` file: grammar, defaults, invalid-content
  behavior (runtime.md §7).
- **Appendix D — HTTP method semantics.** GET/HEAD/PUT/POST/DELETE/OPTIONS, the
  per-command `methods` gate, the every-stage rule, and the GET-cannot-mutate
  invariant (runtime.md §9, §13.2).
- **Appendix E — URL encoding cheat sheet.** When to encode `/ ? & = &(lead)`;
  the multi-`?` request-target; the trailing-`?` filesystem case
  (pipeline_parsing.md §6, §8.1, §9.1).
- **Appendix F — Status-code decision table.** 200/400/404/405/500 with the
  triggering condition and the usual fix.
- **Appendix G — `sdt` command summary.** All eight verbs, one line each, with
  node/sidecar layout recap.
- **Appendix H — gripeline `dot` cheat sheet.** Node-as-command, edge-as-pipe,
  the three verbs, and the linear-URL ↔ graph correspondence.
- **Appendix I — Glossary.** Root, corpus, command path, command segment,
  argument segment, input suffix, arity, implied cat, pipeline boundary,
  parse-mode, synthesized resource, transparent URL (runtime.md §5,
  harness/AGENTS.md glossary), plus SDT/TPC/gripeline terms (node, ordinal,
  sidecar, TPC, turn, continuation, alternative, adapter, gripeline graph), plus
  surface/tree terms (render command, formdown, formdown field, relative link,
  human-readable name vs. ordinal, name layer, provenance, lineage).
- **Appendix J — From shell to wash.** A translation table: `|`, redirection,
  flags, `grep`/`jq`/`wc`, `|&`, `set -o pipefail` → their wash URL forms (and
  where wash deliberately differs, e.g. no core output redirection).
- **Appendix K — Building a runtime / conformance.** Pointer to the MVP checklist
  (runtime.md §18), the spec→clause→vector→impl propagation chain, and how to run
  the conformance harness for a new implementation (AGENTS.md).
- **Appendix L — formdown reference.** The field syntax, how each field maps to a
  query `arg` / path segment / request body, the `action`/`method` rules against a
  command's `methods`, and the invariant that a submission equals a hand-typed
  request (Chapters 14–15). Marked as a book-defined authoring format over
  commands, not a runtime feature.
- **Appendix M — Links and navigation.** Relative-link resolution against the
  request path (RFC 3986 §5), the root-relative-for-stability discipline, SDT node
  navigation (`..`, `../1`, child ordinals), and the under-specified case of a
  base URL under a pipeline request (Chapter 16). Flags what is RFC-defined vs.
  implementation-defined.
- **Appendix N — The naming layer.** Human-readable names as an additive overlay
  on ordinal paths: the `c`-file resolution model, many-to-one, add/change/drop
  without rewriting structure, and the distinction from `sdt name` (next-ordinal
  allocation) (Chapter 17 §17.8). Normative in `runtime.md` §6.6; statically
  linted by `sdt check` (`tools/sdt/`); escapes governed by the `escape_policy`
  capability.
- **Appendix O — Provenance and tracing.** What a node's `b` should record
  (command, effective pipeline, input node(s), timestamp), the `Created Node`
  manifest, the `X-WebShell-*` headers, and how the three line up so lineage stays
  greppable and Git-diffable (Chapters 18 §18.8, 19 §19.5).

---

## Notes for the author (not part of the finished book)

- **Sample fidelity.** Every URL/metadata/exec sample above is written to match
  the v1 contract and the repo's fixture conventions (e.g. `arity 1`,
  `methods POST` + `mutates true`, `exit 0=200 1=404 *=400`, `grep sh` in
  `exec`). Verify each against `specs/` and a live reference run before printing.
- **Running example continuity.** The "lab notebook" root should be a single
  evolving directory checked into the book's repo; each chapter adds exactly the
  files it introduces, so a reader can `git checkout` the state at any chapter.
- **TUPE cadence to preserve.** (1) lead with a problem, (2) smallest complete
  example, (3) generalize, (4) one gotcha, (5) exercises. Keep prose between
  samples tight.
- **Ecosystem weave.** Per the full-ecosystem decision, the browser surface
  (rendering/formdown/links, Part V) and SDT/TPC/gripeline (Parts VI–VII) are
  introduced as soon as the motivating need appears and then reused in the
  capstone, rather than quarantined in a closing survey.
- **Book-introduced models to flag, not over-claim.** Two topics in Parts V–VI
  are presented by the book ahead of (or alongside) the normative specs and must
  be flagged as such, per the policy below: **formdown** (an authoring format
  layered on commands, not a runtime feature); and **node provenance** (a
  discipline over the `b` metadata + `Created Node` manifest + `X-WebShell-*`
  headers, not a new mechanism — though the resolved-path side now has a real
  header, `X-WebShell-Resolved-Path`, per `runtime.md` §6.6.5). The
  **human-readable naming layer** over SDT ordinals is *not* in this list: it is
  normative in `runtime.md` §6.6 (the `c` file) and should be taught as settled
  behavior, distinct from `sdt name`. Relative-link resolution under a *pipeline*
  request is likewise implementation-defined and should be taught as a
  discipline.
- **Open spec questions to track.** Where v1 marks something implementation-
  defined (OPTIONS/CORS, whether `escape_policy` permits out-of-root escapes and
  the resolution-depth budget — note the default `reject-escaping` → 403 is
  itself normative per `runtime.md` §6.6.4 — synthesized resources, directory-listing
  format, base-URL for a pipeline request) or reserved (range arity, `input
  file`/`output file`, standardized `explain`), the book should say
  "implementation-defined / not yet specified" rather than document one server's
  behavior as law.
```
