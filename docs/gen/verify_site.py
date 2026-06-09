#!/usr/bin/env python3
"""Verify site generation works locally before pushing to CI.

Run this script before committing changes to docs/gen/ to catch issues early:
    python3 docs/gen/verify_site.py

It runs collect.py and render.py, validating that:
- Both scripts exit successfully
- Generated JSON is valid
- Generated HTML files exist and are non-empty
- Failure JSON files have expected structure
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

def run_script(script_name: str) -> bool:
    """Run a script and return True if successful."""
    script_path = Path(__file__).parent / script_name
    print(f"\n=== Running {script_name} ===")
    result = subprocess.run(
        ["python3", str(script_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"FAIL: {script_name} exited with code {result.returncode}")
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        return False
    print("OK:", result.stdout.strip().split("\n")[-1] if result.stdout else "completed")
    return True


def validate_json(path: Path) -> bool:
    """Validate a JSON file can be loaded."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        # Check expected structure for failure JSONs
        if "-failures.json" in path.name:
            required_keys = ["generated_at", "commit", "impl", "language", "summary", "failures", "by_clause"]
            for key in required_keys:
                if key not in data:
                    print(f"  FAIL: Missing key '{key}' in {path}")
                    return False
        return True
    except json.JSONDecodeError as e:
        print(f"  FAIL: Invalid JSON in {path}: {e}")
        return False
    except Exception as e:
        print(f"  FAIL: Error reading {path}: {e}")
        return False


def check_outputs() -> bool:
    """Check all expected output files exist and are valid."""
    print("\n=== Checking Generated Outputs ===")
    build_dir = Path(__file__).parent / "build"
    site_dir = Path(__file__).resolve().parents[2] / "site"

    all_ok = True

    # Check build/data.json
    data_json = build_dir / "data.json"
    if data_json.exists():
        print(f"  Checking {data_json}...")
        if validate_json(data_json):
            print(f"    OK")
        else:
            all_ok = False
    else:
        print(f"  FAIL: {data_json} not found")
        all_ok = False

    # Check failure JSONs
    failures_dir = build_dir / "failures"
    if failures_dir.exists():
        for json_file in sorted(failures_dir.glob("*-failures.json")):
            print(f"  Checking {json_file.name}...")
            if validate_json(json_file):
                print(f"    OK")
            else:
                all_ok = False
    else:
        print(f"  FAIL: {failures_dir} not found")
        all_ok = False

    # Check site HTML files
    expected_html = [
        "index.html",
        "ci.html",
        "compliance.html",
        "coverage.html",
        "failures/index.html",
    ]
    for html_path in expected_html:
        full_path = site_dir / html_path
        if full_path.exists() and full_path.stat().st_size > 0:
            print(f"  OK: {html_path} ({full_path.stat().st_size} bytes)")
        else:
            print(f"  FAIL: {html_path} missing or empty")
            all_ok = False

    # Check failure pages
    failures_site = site_dir / "failures"
    if failures_site.exists():
        for html_file in sorted(failures_site.glob("*.html")):
            size = html_file.stat().st_size
            if size > 0:
                print(f"  OK: failures/{html_file.name} ({size} bytes)")
            else:
                print(f"  FAIL: failures/{html_file.name} is empty")
                all_ok = False

        for json_file in sorted(failures_site.glob("*-failures.json")):
            print(f"  Checking failures/{json_file.name}...")
            if validate_json(json_file):
                print(f"    OK")
            else:
                all_ok = False
    else:
        print(f"  FAIL: {failures_site} not found")
        all_ok = False

    return all_ok


def main() -> int:
    """Run verification and return exit code."""
    print("=" * 60)
    print("Site Generation Verification")
    print("=" * 60)

    # Clean up any previous build
    build_dir = Path(__file__).parent / "build"
    site_dir = Path(__file__).resolve().parents[2] / "site"

    if build_dir.exists():
        import shutil
        shutil.rmtree(build_dir)
        print(f"Cleaned {build_dir}")

    # Run collect.py
    if not run_script("collect.py"):
        print("\n" + "=" * 60)
        print("VERIFICATION FAILED: collect.py error")
        return 1

    # Run render.py
    if not run_script("render.py"):
        print("\n" + "=" * 60)
        print("VERIFICATION FAILED: render.py error")
        return 1

    # Check outputs
    if not check_outputs():
        print("\n" + "=" * 60)
        print("VERIFICATION FAILED: output validation error")
        return 1

    print("\n" + "=" * 60)
    print("VERIFICATION PASSED")
    print("=" * 60)
    print(f"\nGenerated site at: {site_dir}")
    print("You can open site/index.html in a browser to preview.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
