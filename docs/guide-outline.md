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
> pipelines as commands, then accumulating *results* as a navigable tree (SDT),
> then generating those trees from commands (TPC), then drawing and running the
> whole workflow as a graph (gripeline). By the last chapter the reader has a
> reusable, shareable, Git-tracked working environment built entirely from
> ordinary files.
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
  (optionally) SDT trees ← produced by TPCs; gripeline as the visual notation
  over the whole thing.

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
  arity, the implied `cat`. Sets the table for Part II.

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

# Part V — Trees of Results: SDT and TPC

*Here the ecosystem widens. wash gives us composition over files; now we want to
**accumulate** results — histories, conversations, explored alternatives — as
navigable structure. This is the book's "big program" arc, the equivalent of
TUPE growing `hoc`.*

## Chapter 14. The Sequential Directory Tree (SDT)

- **14.1 The problem.** Pipelines are ephemeral (runtime.md §9.7). But a lab
  notebook wants to *keep* results, ordered, branchable, and diffable — without
  inventing a database (a wash non-goal, runtime.md §3).
- **14.2 The SDT idea.** A tree of *unnamed* files laid out by ordinal directory
  names: `0`, `1`, …, then `A`, `B`, … — a dense, sortable address space.
- **14.3 Node anatomy.** `a` holds the node's text; an optional `b` holds
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
- **14.4 Sidecars and portability.** `.0` sidecar files track state and let
  `sdt check` verify a tree is well-formed and portable.
- **14.5 The `sdt` tool, by verb.** `code` (encode/decode/validate indices),
  `read` (classify entries), `check` (verify sidecars/portability), `sidecar`,
  `name` (next ordinal), `add` (write a node), `compact` (densify ordinals),
  `pack` (bundle/extract). One tiny example per verb.
- **14.6 Why ordinals instead of names.** Stable addresses, cheap appends,
  natural branching; the same reason URLs in wash are paths.
- **14.7 SDT *through* wash.** Because a tree is just files, a wash root can
  serve it directly: `GET /0/0/a` returns a node's text; a listing browses the
  tree. SDT needs no special runtime support — it rides on Chapter 2.
- **Exercises.** Build a three-node tree by hand; `sdt add` a fourth; `sdt
  compact`; serve the tree from a wash root and navigate it in the browser.

## Chapter 15. Tree-Producing Commands (TPC)

- **15.1 The bridge.** A TPC is *a wash command that writes node files into an
  SDT tree and emits a `Created Node <path>` manifest on stderr.* It joins
  Chapter 9 (commands) to Chapter 14 (trees).
- **15.2 The shape of a TPC.** POST-only, `mutates true`, takes a target node as
  context, writes a response subtree beneath it:
  ```
  # root/env/meta/ask
  methods POST
  mutates true
  parse-mode raw        # or arity, depending on how the target is addressed
  ```
- **15.3 A turn.** One POST = an input node plus the response subtree written
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
- **15.4 Continuations and alternatives.** *Continuation* = a reader-level gloss
  over successive nodes sharing an `author` metadata value (not structural);
  *alternatives* = sibling branches (≥2 children) recording explored variations.
  How a notebook grows a tree of tries.
- **15.5 HTTP-ignorance by design.** A TPC knows nothing about HTTP; a separate
  *adapter* command consumes the stderr manifest to synthesize a
  Post/Redirect/Get response and cache headers. Keep the producer pure
  (runtime.md §6, §10 referenced by the TPC spec).
- **15.6 "The LLM is not special."** Deterministic TPCs (`wc`, a shell command)
  and nondeterministic ones (a model call, an Eliza script) are treated
  identically — same contract, same manifest. Why this uniformity matters for
  reproducibility and testing.
- **15.7 Our notebook becomes a workspace.** Wire `ask` + an adapter so that
  posting a question appends a node and redirects the browser to the new leaf —
  a conversation, command history, or experiment log that *is* a directory tree.
- **Exercises.** Write a deterministic TPC (`echo`-as-node); add an adapter that
  redirects to the leaf; branch an alternative and view both in the browser.

## Chapter 16. Patterns for Accumulating Work

*Synthesis chapter: SDT + TPC + wash composition as one discipline.*

- **16.1 Append-only thinking.** Results accumulate; you navigate history by URL.
- **16.2 Branching to explore.** Alternatives as siblings; comparing two leaves
  with a wash `diff` command (Chapter 4) over their `a` files.
- **16.3 Reading a tree back.** `sdt read` for classification/stats; serving the
  tree for human browsing; pipelines *over* node text (`/grep/TODO/0/3/a`).
- **16.4 Git as the time machine.** SDT trees are plain files; commit them, diff
  them, share them — the persistence story from Chapter 13 applied to results.
- **Exercises.** Build a small experiment log with three branches and write a
  one-command "show me all leaves containing X."

---

# Part VI — Seeing the Whole: gripeline

## Chapter 17. A Graph Is a Pipeline

- **17.1 The motivation.** Long linear pipelines (URL or shell) get hard to read;
  a graph shows data flow at a glance. gripeline's thesis: *the same file you
  draw is the file you run.*
- **17.2 The notation.** A Graphviz `dot` digraph where nodes carry commands:
  ```
  digraph {
    a [label="cat access.log"]
    b [label="grep 404"]
    c [label="wc -l"]
    a -> b -> c
  }
  ```
  ≈ `cat access.log | grep 404 | wc -l`.
- **17.3 The three verbs.** `gripeline build foo.dot` (emit bash), `run` (emit +
  execute), `check` (static validation/executability). One example each.
- **17.4 What gripeline validates.** Node-role resolution, static checks before
  execution — catch a broken graph before it runs.
- **Exercises.** Draw the Chapter 6 four-stage pipeline as a graph; `build` it;
  `run` it; render it with `dot -Tpng`.

## Chapter 18. gripeline and wash Together

- **18.1 Two surfaces for one pipeline.** The URL form is great for ad-hoc and
  bookmarking; the graph form is great for branching, documentation, and review.
  Map a wash pipeline URL to its gripeline graph and back, side by side.
- **18.2 Visualizing wash workflows.** Treat a saved URL expression (Chapter 13)
  and a `.dot` graph as two encodings of the same workflow; when to reach for
  which.
- **18.3 Branching graphs vs. linear URLs.** Where graphs earn their keep:
  fan-out/fan-in that a single left-to-right URL cannot express cleanly.
- **18.4 Serving and running graphs through wash.** A `gripeline` command on the
  path so `GET /gripeline/check/flow.dot` validates and `POST /gripeline/run/...`
  executes — visualization and execution behind ordinary URLs.
- **Exercises.** Build a branching graph, validate it through a wash command, and
  render the diagram into the project's served docs.

---

# Part VII — Putting It All Together

## Chapter 19. A Complete Project: The Lab Notebook

*The capstone, in TUPE's "build something real" spirit — every prior mechanism
appears once, in service of one coherent root.*

- **19.1 The root layout.** A single annotated tree showing `env/path`,
  `env/meta/*`, `exec`, `env/mime`, `bin/` commands, an SDT `tree/`, and `.dot`
  graphs — the whole environment on one page.
- **19.2 Day in the life.** A narrative sequence of real requests: browse files →
  search with a pipeline → save it as a command → POST a question that appends an
  SDT node via a TPC → branch an alternative → draw the workflow as a graph and
  run it → commit everything to Git.
- **19.3 Reuse audit.** Trace how each command reuses earlier ones; show the
  dependency graph (as a gripeline diagram, naturally).
- **19.4 Sharing it.** Clone the root elsewhere; what travels, what is
  machine-local (interpreters, binaries), and how to tell (runtime.md §14).

## Chapter 20. Debugging and Diagnostics

- **20.1 Reading status codes as a language.** 400 (your URL), 404 (nothing
  there), 405 (wrong method), 500 (the *project's* config is wrong) — a decision
  table (runtime.md §15, pipeline_parsing.md §10).
- **20.2 "Why did my pipeline not parse?"** The arity-0 trap, command/argument
  collisions, `arg` on a non-command segment — each with the fix.
- **20.3 Inspecting without running.** `parse-mode raw` explainers and
  `X-WebShell-*` headers (Chapter 12).
- **20.4 Malformed-config 500s.** Bad `exec`, bad `env/meta`, bad `env/mime`,
  bad `env/index`, bad `env/listing` — find them fast.
- **20.5 SDT/TPC pitfalls.** Non-dense ordinals (`sdt compact`), missing/extra
  sidecars (`sdt check`), a TPC that forgets its manifest line.

## Chapter 21. The wash Way (Epilog)

*The TUPE epilog, restated for wash.*

- **21.1 Small pieces, composed.** The Unix philosophy, relocated to URLs and the
  browser.
- **21.2 The filesystem as the only database.** Why plain files beat hidden state
  for a single user (runtime.md §3, §14).
- **21.3 Transparency as a feature.** A URL you can read is a workflow you can
  trust, share, and modify; commands can still shadow behavior, just like a
  shell (runtime.md §5, "Transparent URL").
- **21.4 Constraints that liberate.** No multi-user, no sandbox, no package
  manager — and how dropping those let wash stay legible.
- **21.5 Where wash is going.** A measured note on v1's reserved-but-undefined
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
  sidecar, TPC, turn, continuation, alternative, adapter, gripeline graph).
- **Appendix J — From shell to wash.** A translation table: `|`, redirection,
  flags, `grep`/`jq`/`wc`, `|&`, `set -o pipefail` → their wash URL forms (and
  where wash deliberately differs, e.g. no core output redirection).
- **Appendix K — Building a runtime / conformance.** Pointer to the MVP checklist
  (runtime.md §18), the spec→clause→vector→impl propagation chain, and how to run
  the conformance harness for a new implementation (AGENTS.md).

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
- **Ecosystem weave.** Per the full-ecosystem decision, SDT/TPC/gripeline are
  introduced as soon as the motivating need appears (Parts V–VI) and then reused
  in the capstone, rather than quarantined in a closing survey.
- **Open spec questions to track.** Where v1 marks something implementation-
  defined (OPTIONS/CORS, symlink policy, synthesized resources, directory-listing
  format) or reserved (range arity, `input file`/`output file`, standardized
  `explain`), the book should say "implementation-defined / not yet specified"
  rather than document one server's behavior as law.
```
