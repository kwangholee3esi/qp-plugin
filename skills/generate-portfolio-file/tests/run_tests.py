#!/usr/bin/env python3
"""Regression tests for validate_portfolio.py.

Runs the bundled validator against the fixtures in tests/fixtures/ and asserts
the exit code and (where relevant) the JSON summary counters. This is the
deterministic test surface for the skill; authoring quality is exercised
separately by invoking the skill itself (outputs land in tests/output/).

Run:  python tests/run_tests.py
Exit: 0 if all cases pass, 1 otherwise.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SKILL_DIR = TESTS_DIR.parent
VALIDATOR = SKILL_DIR / "scripts" / "validate_portfolio.py"
FIX = TESTS_DIR / "fixtures"

# Each case: (fixture, expected_exit, predicate-on-result-or-None, description)
# predicate receives the parsed JSON result (dict) and returns (ok, detail).
def expect_clean(r):
    s = r["summary"]
    ok = r["ok"] and s["schema_errors"] == 0 and s["hard_errors"] == 0
    return ok, f"ok={r['ok']} summary={s}"


def expect_semantic_only(r):
    # The whole point: passes JSON Schema, fails on semantic cross-ref/numeric
    # rules the schema cannot express (uniqueness is now enforced by the schema's
    # uniqueKeys, so this fixture deliberately carries none).
    s = r["summary"]
    ok = (not r["ok"]) and s["schema_errors"] == 0 and s["hard_errors"] >= 4
    return ok, f"ok={r['ok']} summary={s}"


def expect_schema_validators(*required):
    """Assert the file is rejected and that each named JSON-Schema keyword fired
    (e.g. maxLength, minimum, uniqueKeys) — guards the synced value constraints."""
    def check(r):
        fired = {e.get("validator") for e in r.get("schema_errors", [])}
        ok = (not r["ok"]) and set(required).issubset(fired)
        return ok, f"ok={r['ok']} fired={sorted(v for v in fired if v)}"
    return check


CASES = [
    ("valid_minimal.json", 0, expect_clean, "minimal certain opportunity"),
    ("valid_uncertain_rules.json", 0, expect_clean, "uncertain + outcome_dep + constraint"),
    ("valid_master_attrs_group.json", 0, expect_clean, "master_data + attributes + group"),
    ("valid_selection_dependency.json", 0, expect_clean, "selection dependency"),
    ("broken_semantic.json", 1, expect_semantic_only,
     "schema-valid but semantically broken (cross-ref/numeric only, 0 schema errors)"),
    ("bad_schema_constraints.json", 1,
     expect_schema_validators("maxLength", "minimum", "uniqueKeys"),
     "trips maxLength + minimum + uniqueKeys (synced value constraints)"),
    ("dup_master_data.json", 1, expect_schema_validators("uniqueKeys"),
     "duplicate master-data opportunity name trips uniqueKeys through the $ref"),
    ("bad_nan.json", 2, None, "NaN literal rejected at parse"),
]


def run(fixture: str):
    proc = subprocess.run(
        [sys.executable, str(VALIDATOR), str(FIX / fixture), "--format", "json"],
        capture_output=True, text=True)
    try:
        result = json.loads(proc.stdout) if proc.stdout.strip() else None
    except json.JSONDecodeError:
        result = None
    return proc.returncode, result, proc.stdout, proc.stderr


def main():
    if not VALIDATOR.is_file():
        print(f"FATAL: validator not found at {VALIDATOR}")
        return 1
    try:
        from jsonschema import Draft202012Validator  # noqa: F401
    except ImportError:
        print("FATAL: the validators need 'jsonschema' >= 4.18 (Draft 2020-12). "
              "Run: pip install --upgrade 'jsonschema>=4.18'")
        return 1

    passed = failed = 0
    for fixture, exp_exit, predicate, desc in CASES:
        code, result, out, err = run(fixture)
        problems = []
        if code != exp_exit:
            problems.append(f"exit {code} != expected {exp_exit}")
        if predicate is not None:
            if result is None:
                problems.append("no JSON result to check predicate")
            else:
                ok, detail = predicate(result)
                if not ok:
                    problems.append(f"predicate failed: {detail}")
        if problems:
            failed += 1
            print(f"FAIL  {fixture:34} {desc}")
            for p in problems:
                print(f"        - {p}")
            if err.strip():
                print(f"        stderr: {err.strip()[:200]}")
        else:
            passed += 1
            extra = ""
            if result and "summary" in result:
                extra = f"  {result['summary']}  ({result.get('schema_source')})"
            print(f"PASS  {fixture:34} exit={code}{extra}")

    print(f"\n{passed} passed, {failed} failed  ({passed + failed} total)")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
