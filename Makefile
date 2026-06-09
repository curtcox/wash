.PHONY: install validate test unit lint format typecheck conformance coverage smoke-reference

PYTHON ?= python3

install:
	$(PYTHON) -m pip install -e ./harness[dev]
	$(PYTHON) -m pip install -e ./impls/reference

validate:
	wash-conformance validate-roots
	wash-conformance validate-vectors
	wash-conformance validate-capabilities harness/adapters/reference.toml
	wash-conformance coverage

conformance:
	wash-conformance run --adapter harness/adapters/reference.toml

unit:
	cd harness && $(PYTHON) -m pytest -q

lint:
	ruff check harness/conformance harness/scripts harness/tests impls/reference/wash
	ruff format --check harness/conformance harness/scripts harness/tests impls/reference/wash

format:
	ruff format harness/conformance harness/scripts harness/tests impls/reference/wash
	ruff check --fix harness/conformance harness/scripts harness/tests impls/reference/wash

typecheck:
	cd harness && mypy conformance
	cd impls/reference && mypy wash

test: validate unit lint typecheck conformance

coverage:
	wash-conformance coverage

smoke-reference:
	$(PYTHON) -m wash.server --root harness/roots/plain-files --port 8080
