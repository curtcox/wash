"""Render build/data.json + specs into the static site under site/.

Plain HTML/CSS, no client-side JavaScript. Run after collect.py.
"""

from __future__ import annotations

import html
import json
import re
import shutil
from pathlib import Path
from typing import Any

from md import render_markdown, render_toc

ROOT = Path(__file__).resolve().parents[2]
GEN = Path(__file__).resolve().parent
BUILD = GEN / "build"
SITE = ROOT / "site"

NAV = [
    ("index.html", "Home"),
    ("compliance.html", "Compliance"),
    ("ci.html", "CI results"),
    ("failures/index.html", "Failure Analysis"),
    ("coverage.html", "Spec coverage"),
    ("specs/runtime.html", "Runtime spec"),
    ("specs/pipeline_parsing.html", "Pipeline parsing"),
    ("specs/audit.html", "Audit"),
]

STATUS_LABEL = {"pass": "✓ pass", "fail": "✗ fail", "n/a": "— n/a"}
CELL_TITLE = {
    "✓": "all vectors pass",
    "✗": "one or more vectors fail",
    "~": "passes with SHOULD warnings",
    "U": "untested (declared unsupported)",
    "–": "no vectors / skipped",
}


def e(s: Any) -> str:
    return html.escape(str(s))


def page(title: str, body: str, *, depth: int = 0, extra_head: str = "") -> str:
    prefix = "../" * depth
    nav = "".join(f'<a href="{prefix}{href}">{e(label)}</a>' for href, label in NAV)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)} · wash</title>
<link rel="stylesheet" href="{prefix}assets/style.css">
{extra_head}
</head>
<body>
<header class="topbar">
  <a class="brand" href="{prefix}index.html">wash</a>
  <nav class="mainnav">{nav}</nav>
</header>
<main>
{body}
</main>
<footer>
  <p>Spec <code>{e(DATA["spec_label"])}</code> · commit <code>{e(DATA["commit_short"])}</code>
     · generated {e(DATA["generated_at"])}</p>
</footer>
</body>
</html>
"""


# ----- pages ------------------------------------------------------------------------


def rewrite_readme_links(html_body: str) -> str:
    """Make README links work on the site.

    Spec markdown links point at their rendered pages; every other repo-relative
    link (harness/, impls/, …) becomes an absolute link into the GitHub repo at
    the built commit so nothing 404s on the static site.
    """
    spec_map = {
        "specs/runtime.md": "specs/runtime.html",
        "specs/pipeline_parsing.md": "specs/pipeline_parsing.html",
        "specs/audit.md": "specs/audit.html",
    }
    repo = DATA.get("repo_url", "")
    commit = DATA.get("commit", "")

    def repl(m: re.Match[str]) -> str:
        href = m.group(1)
        if href in spec_map:
            return f'href="{spec_map[href]}"'
        if href.startswith(("http://", "https://", "#", "mailto:")):
            return m.group(0)
        if repo:
            return f'href="{repo}/blob/{commit}/{href}"'
        return m.group(0)

    return re.sub(r'href="([^"]+)"', repl, html_body)


def render_index() -> str:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    body_html, _ = render_markdown(readme)
    body_html = rewrite_readme_links(body_html)
    impls = DATA["impls"]
    cards = []
    for name, impl in impls.items():
        c = impl["conformance"]
        must = c.get("MUST", [0, 0])
        pct = pct_str(must)
        cards.append(
            f'<a class="impl-card" href="ci.html#{e(name)}">'
            f'<h3>{e(impl["language"])} <span class="impl-name">({e(name)})</span></h3>'
            f'<p class="big">{pct}</p><p class="muted">MUST clauses passing</p></a>'
        )
    summary = f'<section class="cards">{"".join(cards)}</section>'
    intro = (
        '<section class="hero"><h1>wash developer site</h1>'
        "<p>Specs, cross-language compliance, and the latest CI health for every "
        "<code>wash</code> implementation.</p></section>"
    )
    return page(
        "Home", intro + summary + '<section class="prose">' + body_html + "</section>"
    )


def render_compliance() -> str:
    impls = DATA["impls"]
    names = list(impls)
    # Capability columns shared across all manifests, in a friendly order.
    cap_cols = [
        ("escape_policy", "Escape policy"),
        ("case_sensitive_lookup", "Case-sensitive"),
        ("writes_enabled", "Writes"),
        ("deletes_enabled", "Deletes"),
        ("put_creates_parents", "PUT creates parents"),
        ("execution_metadata_headers", "Exec metadata hdrs"),
    ]
    head = (
        "<tr><th>Implementation</th><th>MUST</th><th>SHOULD</th><th>optional</th>"
        + "".join(f"<th>{e(label)}</th>" for _, label in cap_cols)
        + "</tr>"
    )
    rows = []
    for name in names:
        impl = impls[name]
        caps = impl["capabilities"]
        c = impl["conformance"]
        cells = [
            f'<th class="rowhead">{e(impl["language"])} '
            f'<span class="impl-name">({e(name)})</span></th>',
            f"<td>{tier_cell(c.get('MUST'))}</td>",
            f"<td>{tier_cell(c.get('SHOULD'))}</td>",
            f"<td>{tier_cell(c.get('optional'))}</td>",
        ]
        for key, _ in cap_cols:
            cells.append(f"<td>{cap_value(caps.get(key))}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    table = f'<table class="grid"><thead>{head}</thead><tbody>{"".join(rows)}</tbody></table>'
    body = (
        "<h1>Compliance &amp; capabilities</h1>"
        "<p>Conformance pass rates per requirement tier, alongside the capabilities each "
        "implementation declares in its manifest.</p>"
        + table
        + '<p class="muted">Tier cells show passing / total clause checks. '
        "Capabilities come from each impl's <code>wash.capabilities.json</code>.</p>"
    )
    return page("Compliance", body)


def render_ci() -> str:
    impls = DATA["impls"]
    sections = [
        "<h1>CI results</h1><p>Fresh build, lint, test, and static-analysis "
        "results, plus conformance detail and code metrics for every implementation.</p>"
    ]
    step_order = ["compilation", "linting", "testing", "static_analysis"]
    step_titles = {
        "compilation": "Compilation",
        "linting": "Linting",
        "testing": "Testing",
        "static_analysis": "Static analysis",
    }
    for name, impl in impls.items():
        meta = impl["meta"]
        c = impl["conformance"]
        steps = impl["steps"]
        m = impl["metrics"]
        pkgs = meta["packages"] or ["none"]
        dev = meta["dev_packages"]

        step_cards = []
        for key in step_order:
            s = steps.get(key, {})
            status = s.get("status", "n/a")
            log = s.get("log_tail", "")
            timing = f" · {s['seconds']}s" if s.get("seconds") else ""
            detail = (
                f"<details><summary>log</summary><pre>{e(log)}</pre></details>"
                if log
                else ""
            )
            step_cards.append(
                f'<div class="step {status}"><div class="step-h">{e(step_titles[key])}'
                f'<span class="badge {status}">{e(STATUS_LABEL.get(status, status))}</span></div>'
                f'<code class="cmd">{e(s.get("cmd", "")) or "—"}</code>'
                f'<span class="muted">{timing}</span>{detail}</div>'
            )

        fails = c.get("failures", [])
        fail_count = len(fails)
        if fails:
            fail_rows = "".join(
                f"<li><code>{e(f['vector'])}</code> "
                f'<span class="badge fail">{e(f["outcome"])}</span> '
                f"{e(', '.join(f['clauses']))}"
                + (f" — {e(f['reason'])}" if f.get("reason") else "")
                + "</li>"
                for f in fails
            )
            conf_detail = f'<details open><summary>{fail_count} failing vector(s)</summary><ul class="fails">{fail_rows}</ul></details>'
        else:
            conf_detail = '<p class="ok">All vectors pass.</p>'

        # Link to detailed failure analysis
        fail_link = f'<p><a href="failures/{e(name)}.html" class="btn">Detailed failure analysis &rarr;</a></p>' if fail_count > 0 else ''

        largest = m["largest_file"]
        sections.append(
            f'<section class="impl-section" id="{e(name)}">'
            f'<h2>{e(impl["language"])} <span class="impl-name">({e(name)})</span></h2>'
            '<div class="meta-grid">'
            f'<div><span class="k">Supported version</span><span class="v">{e(meta["declared_version"]) or "—"}</span></div>'
            f'<div><span class="k">Toolchain (this run)</span><span class="v">{e(meta["toolchain_version"])}</span></div>'
            f'<div><span class="k">External packages</span><span class="v">{e(", ".join(pkgs))}</span></div>'
            f'<div><span class="k">Dev/test packages</span><span class="v">{e(", ".join(dev)) or "none"}</span></div>'
            "</div>"
            "<h3>Conformance</h3>"
            '<p class="tiers">'
            f"MUST {tier_cell(c.get('MUST'))} · SHOULD {tier_cell(c.get('SHOULD'))} · optional {tier_cell(c.get('optional'))}</p>"
            f"{conf_detail}"
            f"{fail_link}"
            "<h3>Checks</h3>"
            f'<div class="steps">{"".join(step_cards)}</div>'
            "<h3>Code metrics</h3>"
            '<div class="meta-grid">'
            f'<div><span class="k">Source files</span><span class="v">{m["files"]}</span></div>'
            f'<div><span class="k">Lines of code</span><span class="v">{m["lines_of_code"]:,}</span></div>'
            f'<div><span class="k">Largest file</span><span class="v"><code>{e(largest["path"])}</code> ({largest["lines"]} lines)</span></div>'
            f'<div><span class="k">Last changed</span><span class="v">{e(m["last_changed"]) or "—"}</span></div>'
            "</div>"
            "</section>"
        )
    return page("CI results", "".join(sections))


def render_coverage() -> str:
    impls = list(DATA["impls"])
    clauses = DATA["clauses"]
    matrix = DATA["matrix"]
    covered = DATA["coverage"]["covered"]
    cov_summary = DATA["coverage"]
    head = (
        "<tr><th>Clause</th><th>Source</th><th>Tier</th><th>Vectors</th>"
        + "".join(f"<th>{e(n)}</th>" for n in impls)
        + "</tr>"
    )
    rows = []
    for cid, meta in clauses.items():
        nvec = covered.get(cid, 0)
        warn = ' class="gap"' if meta["tier"] == "MUST" and nvec == 0 else ""
        cells = [
            f'<th class="rowhead" id="{e(cid)}"><code>{e(cid)}</code><br>'
            f'<span class="muted">{e(meta["requirement"])}</span></th>',
            f'<td class="src">{source_links(meta["source"])}</td>',
            f'<td><span class="tier {meta["tier"]}">{e(meta["tier"])}</span></td>',
            f"<td>{nvec}</td>",
        ]
        for n in impls:
            sym = matrix.get(cid, {}).get(n, "–")
            cells.append(
                f'<td class="cell" title="{e(CELL_TITLE.get(sym, sym))}">{e(sym)}</td>'
            )
        rows.append(f"<tr{warn}>" + "".join(cells) + "</tr>")
    table = f'<table class="grid coverage"><thead>{head}</thead><tbody>{"".join(rows)}</tbody></table>'
    legend = (
        '<p class="legend">'
        + " · ".join(f"<b>{e(s)}</b> {e(t)}" for s, t in CELL_TITLE.items())
        + "</p>"
    )
    missing = cov_summary["must_missing_vectors"]
    miss_html = (
        '<p class="warn-note">MUST clauses with no vectors: '
        + ", ".join(f"<code>{e(c)}</code>" for c in missing)
        + "</p>"
        if missing
        else f'<p class="ok">All MUST clauses are exercised by at least one vector '
        f"({cov_summary['must_coverage_pct']}% MUST coverage).</p>"
    )
    body = (
        "<h1>Spec coverage</h1>"
        "<p>Every clause in the registry, the vectors exercising it, and per-implementation "
        "results. Clause links from the specs land here.</p>"
        + miss_html
        + legend
        + table
    )
    return page("Spec coverage", body)


def render_spec(src: Path, title: str) -> str:
    text = src.read_text(encoding="utf-8")
    body_html, toc = render_markdown(text)
    toc_html = render_toc(toc)
    body = (
        f'<div class="spec-layout"><article class="prose">{body_html}</article>'
        f"{toc_html}</div>"
    )
    return page(title, body, depth=1)


# ----- failure analysis pages -------------------------------------------------------


# Category colors for badges
CATEGORY_BADGE = {
    "status_mismatch": "badge-fail",
    "body_mismatch": "badge-fail",
    "header_mismatch": "badge-fail",
    "tree_mismatch": "badge-fail",
    "file_not_found": "badge-fail",
    "launch_failure": "badge-error",
    "process_died": "badge-error",
    "timeout": "badge-warn",
    "capability_declared": "badge-warn",
    "untested": "badge-warn",
    "unknown": "badge-warn",
}


def _outcome_badge(outcome: str) -> str:
    cls = "badge fail" if outcome in {"FAIL", "LAUNCH_FAILURE", "PROCESS_DIED"} else "badge warn"
    return f'<span class="{cls}">{e(outcome)}</span>'


def _render_failure_card(failure: dict[str, Any], impl: str) -> str:
    """Render a single failure as an expandable card."""
    vector_id = failure["vector_id"]
    outcome = failure.get("outcome", "FAIL")
    clauses = failure.get("clauses", [])
    category = failure.get("ai_context", {}).get("category", "unknown")
    diff = failure.get("diff", "")
    reason = failure.get("reason", "")

    # Build clause links
    clause_links = ", ".join(
        f'<a href="../coverage.html#{e(c)}"><code>{e(c)}</code></a>' for c in clauses
    )

    # Category badge
    cat_cls = CATEGORY_BADGE.get(category, "badge-warn")
    cat_badge = f'<span class="badge {cat_cls}">{e(category)}</span>'

    # Request details
    req_method = failure.get("request_method", "")
    req_target = failure.get("request_target", "")
    request_info = f'<code>{e(req_method)} {e(req_target)}</code>' if req_method else ""

    # Expected vs Actual
    expected = failure.get("expected_summary", "")
    actual = failure.get("actual") or {}
    actual_status = actual.get("status", "—") if actual else "—"
    actual_body = actual.get("body_base64", "") if actual else ""
    body_preview = ""
    if actual_body:
        import base64
        try:
            decoded = base64.b64decode(actual_body).decode("utf-8", errors="replace")[:200]
            body_preview = f"<pre class='body-preview'>{e(decoded)}</pre>"
        except Exception:
            pass

    # AI Context
    ai_ctx = failure.get("ai_context", {})
    spec_links = ai_ctx.get("spec_links", [])
    spec_html = ""
    if spec_links:
        spec_html = "<ul>" + "".join(f'<li><a href="../{e(l)}">{e(l)}</a></li>' for l in spec_links) + "</ul>"

    similar = ai_ctx.get("similar_passing", [])
    similar_html = ""
    if similar:
        similar_html = "<p>Similar passing vectors: " + ", ".join(f"<code>{e(s)}</code>" for s in similar[:3]) + "</p>"

    suggested = ai_ctx.get("suggested_investigation", "")

    card = f"""
<div class="failure-card" data-category="{e(category)}" data-tier="{e(failure.get('tier', 'optional'))}">
  <div class="failure-header">
    <span class="failure-id"><code>{e(vector_id)}</code></span>
    {_outcome_badge(outcome)}
    {cat_badge}
  </div>
  <div class="failure-clauses">Clauses: {clause_links}</div>
  <div class="failure-request">{request_info}</div>
  <details>
    <summary>Details</summary>
    <div class="failure-details">
      <div class="row">
        <div class="col">
          <h4>Expected</h4>
          <pre>{e(expected) if expected else "See vector definition"}</pre>
        </div>
        <div class="col">
          <h4>Actual</h4>
          <p>Status: <b>{actual_status}</b></p>
          {body_preview}
        </div>
      </div>
      {f'<div class="diff"><h4>Diff</h4><pre>{e(diff)}</pre></div>' if diff else ""}
      {f'<div class="reason"><h4>Reason</h4><p>{e(reason)}</p></div>' if reason else ""}
      <div class="ai-context">
        <h4>AI Analysis Context</h4>
        <p><b>Suggested investigation:</b> {e(suggested)}</p>
        {similar_html}
        <p><b>Spec references:</b></p>
        {spec_html or "<p class='muted'>No spec links available</p>"}
        <p class="muted">Vector source: <code>{e(ai_ctx.get('vector_source', 'unknown'))}</code></p>
        <p class="muted">Fixture root: <code>{e(ai_ctx.get('root_fixture', 'unknown'))}</code></p>
      </div>
    </div>
  </details>
</div>
"""
    return card


def render_failures_page(impl: str, data: dict[str, Any]) -> str:
    """Render detailed failure analysis page for an implementation."""
    summary = data.get("summary", {})
    failures = data.get("failures", [])
    language = data.get("language", impl)
    commit = data.get("commit", "")[:8]

    # Summary section
    must = summary.get("MUST", {})
    should = summary.get("SHOULD", {})
    optional = summary.get("optional", {})

    summary_html = f"""
    <div class="summary-grid">
      <div class="summary-card must">
        <span class="tier">MUST</span>
        <span class="count">{must.get('pass', 0)}/{must.get('total', 0)}</span>
        <span class="label">passing</span>
        <span class="fail">{must.get('fail', 0)} failing</span>
      </div>
      <div class="summary-card should">
        <span class="tier">SHOULD</span>
        <span class="count">{should.get('pass', 0)}/{should.get('total', 0)}</span>
        <span class="label">passing</span>
        <span class="fail">{should.get('fail', 0)} failing</span>
      </div>
      <div class="summary-card optional">
        <span class="tier">optional</span>
        <span class="count">{optional.get('pass', 0)}/{optional.get('total', 0)}</span>
        <span class="label">passing</span>
        <span class="fail">{optional.get('fail', 0)} failing</span>
      </div>
    </div>
    """

    # Download button
    download_section = f"""
    <div class="download-section">
      <a href="{e(impl)}-failures.json" download class="btn-primary">
        Download {e(language)} Failures JSON
      </a>
      <span class="muted">For AI tooling · {len(failures)} failures · commit {e(commit)}</span>
    </div>
    """

    # Filters
    filters = """
    <div class="filters">
      <label>Filter by tier:</label>
      <button onclick="filterFailures('all')">All</button>
      <button onclick="filterFailures('MUST')">MUST</button>
      <button onclick="filterFailures('SHOULD')">SHOULD</button>
      <button onclick="filterFailures('optional')">Optional</button>
      <label style="margin-left: 1rem;">Category:</label>
      <button onclick="filterCategory('all')">All</button>
      <button onclick="filterCategory('status_mismatch')">Status</button>
      <button onclick="filterCategory('body_mismatch')">Body</button>
      <button onclick="filterCategory('launch_failure')">Launch</button>
    </div>
    <script>
    function filterFailures(tier) {
      document.querySelectorAll('.failure-card').forEach(card => {
        card.style.display = tier === 'all' || card.dataset.tier === tier ? 'block' : 'none';
      });
    }
    function filterCategory(cat) {
      document.querySelectorAll('.failure-card').forEach(card => {
        card.style.display = cat === 'all' || card.dataset.category === cat ? 'block' : 'none';
      });
    }
    </script>
    """

    # Failure cards
    if failures:
        # Sort: MUST first, then by outcome severity
        def sort_key(f):
            tier_order = {"MUST": 0, "SHOULD": 1, "optional": 2}
            outcome_order = {"LAUNCH_FAILURE": 0, "PROCESS_DIED": 1, "FAIL": 2, "UNTESTED": 3}
            return (tier_order.get(f.get("tier"), 3), outcome_order.get(f.get("outcome"), 4), f.get("vector_id", ""))

        sorted_failures = sorted(failures, key=sort_key)
        failure_cards = "".join(_render_failure_card(f, impl) for f in sorted_failures)
    else:
        failure_cards = '<p class="ok">All tests pass. No failures to display.</p>'

    body = f"""
    <h1>{e(language)} Failure Analysis</h1>
    <p class="muted">Detailed conformance failures for iterative AI-assisted fixing.</p>
    {summary_html}
    {download_section}
    {filters if failures else ""}
    <h2>Failures ({len(failures)})</h2>
    <div class="failure-list">
      {failure_cards}
    </div>
    """

    return page(f"{language} Failures", body)


def render_failures_index(impls_data: dict[str, dict[str, Any]]) -> str:
    """Render overview page listing all implementations' failure analysis."""
    cards = []
    for impl, data in sorted(impls_data.items()):
        lang = data.get("language", impl)
        summary = data.get("summary", {})
        must = summary.get("MUST", {})
        fail_count = data.get("failure_count", 0)

        cls = "has-failures" if fail_count > 0 else "all-pass"
        status = f"{fail_count} failures" if fail_count > 0 else "All pass"
        must_str = f"MUST: {must.get('pass', 0)}/{must.get('total', 0)}"

        cards.append(f"""
        <a href="{e(impl)}.html" class="impl-card {cls}">
          <h3>{e(lang)} <span class="impl-name">({e(impl)})</span></h3>
          <p class="big">{e(status)}</p>
          <p class="muted">{e(must_str)}</p>
          <span class="download-hint">View details &rarr;</span>
        </a>
        """)

    body = f"""
    <h1>Failure Analysis by Implementation</h1>
    <p>Per-language conformance failure details for AI-assisted debugging.</p>
    <section class="cards">
      {"".join(cards)}
    </section>
    <p class="muted">Each page provides downloadable JSON with full failure context for programmatic analysis.</p>
    """

    return page("Failure Analysis", body)


# ----- helpers ----------------------------------------------------------------------


def pct_str(pair: list[int] | None) -> str:
    if not pair or pair[1] == 0:
        return "—"
    return f"{round(100 * pair[0] / pair[1])}%"


def tier_cell(pair: list[int] | None) -> str:
    if not pair or pair[1] == 0:
        return '<span class="muted">—</span>'
    passed, total = pair
    cls = "ok" if passed == total else "bad"
    return f'<span class="{cls}">{passed}/{total}</span>'


_SPEC_FILE = {
    "runtime": "specs/runtime.html",
    "pipeline": "specs/pipeline_parsing.html",
    "audit": "specs/audit.html",
}


def source_links(source: str) -> str:
    """Linkify a clause source label like 'runtime §6.2 / pipeline §9.1'."""
    out: list[str] = []
    for token in re.split(r"\s*/\s*", source):
        m = re.match(r"(runtime|pipeline|audit)\s*§?\s*([\d.]+)?", token)
        if not m or m.group(1) not in _SPEC_FILE:
            out.append(e(token))
            continue
        href = _SPEC_FILE[m.group(1)]
        if m.group(2):
            href += f"#sec-{m.group(2)}"
        out.append(f'<a href="{href}">{e(token)}</a>')
    return " / ".join(out)


def cap_value(v: Any) -> str:
    if v is None:
        return '<span class="muted">—</span>'
    if isinstance(v, bool):
        return '<span class="yes">yes</span>' if v else '<span class="no">no</span>'
    if isinstance(v, list):
        return e(", ".join(map(str, v))) if v else '<span class="muted">none</span>'
    return e(v)


DATA: dict[str, Any] = {}


def main() -> None:
    global DATA
    DATA = json.loads((BUILD / "data.json").read_text(encoding="utf-8"))

    if SITE.exists():
        shutil.rmtree(SITE)
    (SITE / "specs").mkdir(parents=True)
    (SITE / "assets").mkdir(parents=True)
    (SITE / "failures").mkdir(parents=True)
    shutil.copyfile(GEN / "assets/style.css", SITE / "assets/style.css")

    (SITE / "index.html").write_text(render_index(), encoding="utf-8")
    (SITE / "compliance.html").write_text(render_compliance(), encoding="utf-8")
    (SITE / "ci.html").write_text(render_ci(), encoding="utf-8")
    (SITE / "coverage.html").write_text(render_coverage(), encoding="utf-8")
    (SITE / "specs/runtime.html").write_text(
        render_spec(ROOT / "specs/runtime.md", "Runtime spec"), encoding="utf-8"
    )
    (SITE / "specs/pipeline_parsing.html").write_text(
        render_spec(ROOT / "specs/pipeline_parsing.md", "Pipeline parsing"),
        encoding="utf-8",
    )
    (SITE / "specs/audit.html").write_text(
        render_spec(ROOT / "specs/audit.md", "Audit"), encoding="utf-8"
    )

    # Generate failure analysis pages
    failures_build = BUILD / "failures"
    if failures_build.exists():
        impls_failures: dict[str, dict[str, Any]] = {}
        for json_file in sorted(failures_build.glob("*-failures.json")):
            impl = json_file.stem.replace("-failures", "")
            impl_data = json.loads(json_file.read_text(encoding="utf-8"))
            impls_failures[impl] = impl_data
            # Copy JSON to site
            shutil.copyfile(json_file, SITE / "failures" / json_file.name)
            # Generate HTML page
            (SITE / "failures" / f"{impl}.html").write_text(
                render_failures_page(impl, impl_data), encoding="utf-8"
            )
            print(f"wrote failures/{impl}.html and {json_file.name}")

        # Generate failures index page
        if impls_failures:
            (SITE / "failures" / "index.html").write_text(
                render_failures_index(impls_failures), encoding="utf-8"
            )
            print("wrote failures/index.html")

    print(f"wrote site to {SITE}")


if __name__ == "__main__":
    main()
