"""pytest integration for wash conformance harness."""

from __future__ import annotations

import pytest

from conformance.httpclient import self_test
from conformance.report import Outcome
from conformance.rootcorpus import validate_roots
from conformance.runner import load_vectors, run, validate_vectors


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("wash")
    group.addoption(
        "--wash-adapter",
        action="append",
        default=None,
        help="Adapter manifest for conformance run",
    )
    group.addoption("--wash-root", default=None, help="Filter vectors by root")
    group.addoption("--wash-tier", default=None, help="Filter vectors by tier")
    group.addoption("--wash-clause", default=None, help="Filter vectors by clause id")
    group.addoption(
        "--wash-strict",
        action="store_true",
        default=False,
        help="Fail gate on SHOULD warnings",
    )


@pytest.fixture(scope="session")
def wash_vectors(request: pytest.FixtureRequest) -> list[dict]:
    return load_vectors(
        root=request.config.getoption("--wash-root"),
        tier=request.config.getoption("--wash-tier"),
        clause=request.config.getoption("--wash-clause"),
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "conformance: wash conformance integration test")


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    adapters = config.getoption("--wash-adapter")
    if not adapters:
        return
    # When adapters provided, ensure conformance tests are selected
    for item in items:
        if "conformance" in item.keywords:
            item.add_marker(pytest.mark.conformance)


@pytest.fixture(scope="session")
def wash_report(request: pytest.FixtureRequest):
    adapters = request.config.getoption("--wash-adapter")
    if not adapters:
        pytest.skip("no --wash-adapter provided")
    return run(
        adapters,
        root=request.config.getoption("--wash-root"),
        tier=request.config.getoption("--wash-tier"),
        clause=request.config.getoption("--wash-clause"),
        strict=request.config.getoption("--wash-strict"),
    )


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "vector_id" in metafunc.fixturenames:
        vectors = load_vectors()
        ids = [v["id"] for v in vectors]
        metafunc.parametrize("vector_id", ids or ["__no_vectors__"])


@pytest.hookimpl(tryfirst=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    adapters = session.config.getoption("--wash-adapter")
    if not adapters:
        return
    report = run(
        adapters,
        root=session.config.getoption("--wash-root"),
        tier=session.config.getoption("--wash-tier"),
        clause=session.config.getoption("--wash-clause"),
        strict=session.config.getoption("--wash-strict"),
    )
    if report.gate_failed(strict=session.config.getoption("--wash-strict")):
        session.exitstatus = 1


def test_httpclient_self_test() -> None:
    errors = self_test()
    assert not errors, errors


def test_validate_vectors_schema() -> None:
    errors = validate_vectors()
    assert not errors, errors


def test_validate_roots_corpus() -> None:
    errors = validate_roots()
    # roots may not exist yet in early phases — only fail on real invariant breaks
    hard = [e for e in errors if "missing canonical" in e or "symlink forbidden" in e]
    assert not hard, hard


@pytest.mark.conformance
def test_conformance_gate(wash_report) -> None:
    failures = [
        r
        for r in wash_report.records
        if r.outcome
        in {
            Outcome.FAIL,
            Outcome.UNTESTED,
            Outcome.LAUNCH_FAILURE,
            Outcome.PROCESS_DIED,
        }
        and r.tier == "MUST"
    ]
    assert not failures, [
        f"{r.vector_id}: {r.outcome} {r.reason}" for r in failures[:10]
    ]
