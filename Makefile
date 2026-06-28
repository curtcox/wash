.PHONY: install validate test unit lint format typecheck conformance coverage smoke-reference sdt-test ui-test \
	build-go lint-go test-go conformance-go test-go-all \
	build-dart lint-dart test-dart conformance-dart test-dart-all \
	verify-site check-book

PYTHON ?= python3

install:
	$(PYTHON) -m pip install -e ./harness[dev]
	$(PYTHON) -m pip install -e ./impls/reference

validate:
	wash-conformance validate-roots
	wash-conformance validate-vectors
	wash-conformance validate-capabilities harness/adapters/reference.toml
	wash-conformance validate-capabilities harness/adapters/go.toml
	wash-conformance validate-capabilities harness/adapters/dart.toml
	wash-conformance coverage

conformance:
	wash-conformance run --adapter harness/adapters/reference.toml

unit:
	cd harness && $(PYTHON) -m pytest -q

lint:
	ruff check harness/conformance harness/scripts harness/tests impls/reference/wash tools/sdt/sdt tools/sdt/tests
	ruff format --check harness/conformance harness/scripts harness/tests impls/reference/wash tools/sdt/sdt tools/sdt/tests

format:
	ruff format harness/conformance harness/scripts harness/tests impls/reference/wash tools/sdt/sdt tools/sdt/tests
	ruff check --fix harness/conformance harness/scripts harness/tests impls/reference/wash tools/sdt/sdt tools/sdt/tests

typecheck:
	cd harness && mypy conformance
	cd impls/reference && mypy wash
	cd tools/sdt && mypy sdt

sdt-test:
	cd tools/sdt && $(PYTHON) -m pytest -q

ui-test:
	$(PYTHON) -m pytest -q tests/ui

test: validate unit lint typecheck conformance sdt-test ui-test

coverage:
	wash-conformance coverage

smoke-reference:
	$(PYTHON) -m wash.server --root harness/roots/plain-files --port 8080

# Go implementation targets
build-go:
	cd impls/go && go build -o bin/wash-server ./cmd/wash-server

lint-go:
	cd impls/go && test -z "$$(gofmt -l .)" && go vet ./...

test-go: build-go
	cd impls/go && go test ./...

conformance-go: build-go
	wash-conformance run --adapter harness/adapters/go.toml

test-go-all: lint-go test-go conformance-go

# Dart implementation targets
build-dart:
	cd impls/dart && dart pub get && dart compile exe bin/wash_server.dart -o bin/wash-server

lint-dart:
	dart analyze impls/dart
	dart format --output=none --set-exit-if-changed impls/dart

test-dart: build-dart
	cd impls/dart && dart test

conformance-dart: build-dart
	wash-conformance run --adapter harness/adapters/dart.toml

test-dart-all: lint-dart test-dart conformance-dart

# Site generation verification (run before pushing docs/gen changes)
verify-site:
	$(PYTHON) docs/gen/verify_site.py

# Book app link check: crawl the served book from / and fail on any link >= 400
check-book:
	$(PYTHON) check
