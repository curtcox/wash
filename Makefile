.PHONY: install validate test conformance coverage smoke-reference

install:
	pip install -e ./harness[dev]
	pip install -e ./impls/reference

validate:
	wash-conformance validate-roots
	wash-conformance validate-vectors
	wash-conformance validate-capabilities harness/adapters/reference.toml
	wash-conformance coverage

conformance:
	wash-conformance run --adapter harness/adapters/reference.toml

test: validate conformance

coverage:
	wash-conformance coverage

smoke-reference:
	python -m wash.server --root harness/roots/plain-files --port 8080
