# AGENTS.md

## Scope
Minimal Python reference `wash` server. It is one implementation among several
(additional language impls live as siblings under `impls/`). It must conform to
`specs/runtime.md` and `specs/pipeline_parsing.md`. The harness launches it via
`harness/adapters/reference.toml` and never imports it — keep it free of any
`conformance` import. See `../../AGENTS.md` for repo-wide commands.

## Module Map (`wash/`)
- `server.py`     — HTTP entry point (`python -m wash.server`), routing, request handling.
- `parser.py`     — URL/pipeline parsing per `pipeline_parsing.md`.
- `filesystem.py` — file/dir resolution, serving, mutation, MIME, root-escape rejection.
- `metadata.py`   — `env/meta/*` command-metadata loading + validation.
- `executor.py`   — interpreter resolution and command-pipeline evaluation.

## When you change behavior here
Mirror it in `specs/`, register or adjust a clause in
`harness/conformance/spec.py`, and add or update a vector in
`harness/conformance/vectors/`. Then `make conformance`. Declared features go in
`wash.capabilities.json`. If this impl and the spec disagree, resolve it case by
case — the long-term goal is zero differences across all implementations.
