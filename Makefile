.PHONY: install validate test unit conformance coverage smoke-reference

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

test: validate unit conformance

coverage:
	wash-conformance coverage

smoke-reference:
	$(PYTHON) -m wash.server --root harness/roots/plain-files --port 8080
