# Plan: AI-Friendly Conformance Failure Pages

## Goal
Create per-language conformance pages that are optimized for:
1. **Direct download** - JSON exports with full failure context
2. **AI ingestion** - Structured, actionable data for iterative fixing
3. **Human readability** - HTML pages with clear failure analysis

## Current State Analysis

### Data Available (from `TestRecord` in `report.py`)
- `vector_id`, `clauses`, `tier`, `outcome`
- `request_method`, `request_target` - The HTTP request made
- `expected_summary` - What was expected
- `actual` - HttpSnapshot with status, headers, body (base64), transport_error
- `diff` - Human-readable diff of mismatch
- `tree_diff` - Filesystem tree differences (for mutation tests)
- `reason` - Failure reason string
- `child_output` - Server process output (for crashes)
- `timing_ms` - Request timing

### Current Limitations
1. `collect.py` `summarize_conformance()` only stores: vector, clauses, outcome, reason
2. `render.py` `render_ci()` displays basic failure list without request/response details
3. No per-language JSON export with full failure context
4. No AI-optimized formatting (structured prompts, suggested fixes, related spec links)

## Implementation Plan

### Phase 1: Enhanced Data Collection (collect.py)

**Task 1.1: Extend conformance summary with detailed failures**
- Modify `summarize_conformance()` to capture full `TestRecord` data for failures
- Store: request details, actual response, diff, tree_diff, child_output
- Group failures by clause for easier analysis
- Add vector source file paths for context

**Task 1.2: Add AI-optimized failure analysis**
- For each failure, generate an `ai_context` object containing:
  - `suggested_fix_pattern`: Classification of failure type (status_mismatch, header_missing, body_mismatch, etc.)
  - `related_spec_sections`: Direct links to relevant spec clauses
  - `vector_file_path`: Location of the YAML vector file
  - `root_fixture_path`: Location of the test fixture root
  - `similar_passing_vectors`: Other vectors for the same clause that pass (for comparison)

### Phase 2: Per-Language JSON Export (collect.py)

**Task 2.1: Generate `{lang}-failures.json` files**
Create `site/failures/` directory with:
- `reference-failures.json` - Python reference implementation
- `go-failures.json` - Go implementation
- `dart-failures.json` - Dart implementation

Each JSON structure:
```json
{
  "generated_at": "ISO timestamp",
  "commit": "abc123",
  "impl": "go",
  "language": "Go",
  "summary": {
    "MUST": {"pass": 85, "total": 112, "fail": 27},
    "SHOULD": {"pass": 1, "total": 1, "fail": 0},
    "optional": {"pass": 11, "total": 11, "fail": 0}
  },
  "failures": [
    {
      "vector_id": "basic-get-file",
      "clauses": ["RT-1.1-get"],
      "tier": "MUST",
      "outcome": "FAIL",
      "category": "status_mismatch",
      "request": {
        "method": "GET",
        "target": "/hello.txt"
      },
      "expected": {
        "status": 200,
        "body_present": true
      },
      "actual": {
        "status": 404,
        "headers": {"Content-Type": ["text/plain"]},
        "body_base64": "...",
        "transport_error": null
      },
      "diff": "status: expected 200, got 404",
      "reason": "Status mismatch",
      "ai_context": {
        "vector_source": "harness/conformance/vectors/basic.yaml",
        "root_fixture": "harness/roots/plain-files",
        "spec_links": ["specs/runtime.html#sec-1.1"],
        "suggested_investigation": "Check if file exists in root and is accessible",
        "similar_passing": ["basic-get-dir"]
      }
    }
  ],
  "by_clause": {
    "RT-1.1-get": {
      "total": 5,
      "pass": 3,
      "fail": 2,
      "failure_ids": ["basic-get-file", "basic-get-nested"]
    }
  }
}
```

### Phase 3: Per-Language HTML Pages (render.py)

**Task 3.1: Create `render_failures_page()` function**
Generate `site/failures/{impl}.html` for each implementation:

Page structure:
- **Header**: Implementation name, commit, generation time
- **Summary**: Tier breakdown with pass/fail counts
- **Download Button**: Prominent JSON download link
- **Failure List**: Expandable cards for each failure

Failure card content:
- Vector ID (link to coverage page)
- Outcome badge (FAIL, LAUNCH_FAILURE, etc.)
- Clauses (links to spec sections)
- Request details (method, target)
- Expected vs Actual comparison
- Diff highlighting
- AI Context panel with:
  - Vector source file link
  - Fixture root path
  - Suggested investigation steps
  - Related spec links

**Task 3.2: Add failure categorization UI**
- Filter by: tier (MUST/SHOULD/optional), outcome type, clause
- Sort by: severity (MUST first), vector ID
- Group by: clause category for pattern analysis

### Phase 4: Main CI Page Integration (render.py)

**Task 4.1: Update `render_ci()` with failure page links**
- Add prominent link to per-language failure analysis page
- Add "Download JSON for AI" button next to each implementation section
- Include failure count summary with direct link to filtered view

### Phase 5: Navigation & Index (render.py)

**Task 5.1: Add failures section to site navigation**
- Add "Failure Analysis" to main nav
- Create `site/failures/index.html` with overview of all implementations
- Include comparison matrix (which failures are shared across impls)

## File Changes Summary

### Modified Files
1. `docs/gen/collect.py`:
   - Extend `summarize_conformance()` to capture full failure details
   - Add `generate_ai_context()` helper
   - Write per-language JSON files to `build/failures/`

2. `docs/gen/render.py`:
   - Add `render_failures_page(impl)` function
   - Add `render_failures_index()` function
   - Update `render_ci()` with failure page links
   - Copy failures from `build/failures/` to `site/failures/`

### New Output Files
- `site/failures/index.html` - Overview page
- `site/failures/reference.html` - Python failure analysis
- `site/failures/go.html` - Go failure analysis
- `site/failures/dart.html` - Dart failure analysis
- `site/failures/reference-failures.json` - Downloadable data
- `site/failures/go-failures.json` - Downloadable data
- `site/failures/dart-failures.json` - Downloadable data

## AI Tool Integration Design

### For Loop-Based AI Tools
The JSON format supports iterative fixing:

```python
# Pseudocode for AI tool
failures = load_json("go-failures.json")

for clause, group in group_by_clause(failures):
    # All failures for RT-6.2-precedence
    for failure in group:
        # Attempt fix based on pattern
        fix = generate_fix(failure)
        apply_fix(fix)
    
    # Re-run just this clause's vectors
    result = run_conformance(clause=clause)
    
    # Update progress
    if all_pass(result):
        mark_clause_fixed(clause)
```

### Key Features for AI Consumption
1. **Categorization**: Each failure has a `category` field (status_mismatch, body_mismatch, header_missing, etc.)
2. **Pattern detection**: `by_clause` grouping shows if multiple vectors fail for same clause
3. **Minimal reproduction**: Request details allow recreating the failing test
4. **Spec context**: Direct links to relevant specification sections
5. **Similar passing**: Shows related vectors that pass (helps isolate the issue)

## Success Metrics

After implementation, an AI tool should be able to:
1. Download a single JSON file with all failure context
2. Identify patterns across failures (e.g., "all PUT requests fail with 404")
3. Access vector source files and fixture roots for local reproduction
4. Navigate from failure to relevant spec section
5. Track progress as fixes are applied (by re-running and comparing)

## Future Enhancements (Out of Scope)
- Diff suggestions (AI-generated fix proposals)
- Historical trend analysis (failure counts over commits)
- Automated bisect to find when failures were introduced
- Integration with GitHub Issues (auto-create tickets for MUST failures)
