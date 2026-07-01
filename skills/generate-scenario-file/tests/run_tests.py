#!/usr/bin/env python3
"""Regression tests for validate_scenario.py.

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
VALIDATOR = SKILL_DIR / "scripts" / "validate_scenario.py"
FIX = TESTS_DIR / "fixtures"


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
    (e.g. pattern, exclusiveMinimum, uniqueKeys) — guards the synced constraints."""
    def check(r):
        fired = {e.get("validator") for e in r.get("schema_errors", [])}
        ok = (not r["ok"]) and set(required).issubset(fired)
        return ok, f"ok={r['ok']} fired={sorted(v for v in fired if v)}"
    return check


def expect_crossref_unchecked(r):
    # Schema-valid and intra-scenario clean, but no portfolio supplied -> a single
    # crossref.unchecked warning and exit 0.
    s = r["summary"]
    has_warn = any(f["check"] == "crossref.unchecked" for f in r.get("semantic", []))
    ok = r["ok"] and s["hard_errors"] == 0 and has_warn
    return ok, f"ok={r['ok']} summary={s} crossref_unchecked={has_warn}"


def expect_crossref_hard(r):
    # Same file WITH a portfolio: the ghost opportunity is now a hard error.
    s = r["summary"]
    has_err = any(f["check"] == "crossref.selection_opportunity"
                  for f in r.get("semantic", []))
    ok = (not r["ok"]) and s["schema_errors"] == 0 and has_err
    return ok, f"ok={r['ok']} summary={s} crossref_opportunity_error={has_err}"


def expect_portfolio_unreadable(r):
    # An unreadable --portfolio downgrades to a warning (cross-ref skipped), exit 0.
    has_warn = any(f["check"] == "crossref.portfolio_unreadable"
                   for f in r.get("semantic", []))
    ok = r["ok"] and r["summary"]["hard_errors"] == 0 and has_warn
    return ok, f"ok={r['ok']} portfolio_unreadable={has_warn}"


# Each case: (fixture, portfolio|None, expected_exit, predicate, description)
CASES = [
    ("valid_minimal.json", None, 0, expect_clean, "objective only"),
    ("valid_optimization_limits.json", None, 0, expect_clean, "objective + metric limit"),
    ("valid_overrides.json", None, 0, expect_clean, "constraint + dependency + group overrides"),
    ("valid_pinned_selections.json", None, 0, expect_clean, "pinned selections + soft limit"),
    ("broken_semantic.json", None, 1, expect_semantic_only,
     "schema-valid but semantically broken (cross-ref/numeric only, 0 schema errors)"),
    ("bad_schema_constraints.json", None, 1,
     expect_schema_validators("pattern", "exclusiveMinimum", "uniqueKeys"),
     "trips pattern + exclusiveMinimum + uniqueKeys (synced value constraints)"),
    ("bad_nan.json", None, 2, None, "NaN literal rejected at parse"),
    ("crossref_bad.json", None, 0, expect_crossref_unchecked,
     "ghost opportunity, no --portfolio -> exit 0 + crossref.unchecked warning"),
    ("crossref_bad.json", "sample_portfolio.json", 1, expect_crossref_hard,
     "ghost opportunity, --portfolio -> hard cross-ref error"),
    ("enum_linearization_null.json", None, 0, expect_clean,
     "linearization_level null is a valid enum member"),
    ("enum_linearization_bad.json", None, 1, expect_schema_validators("enum"),
     "linearization_level out of enum trips the enum keyword"),
    ("valid_minimal.json", "does_not_exist_portfolio.json", 0, expect_portfolio_unreadable,
     "unreadable --portfolio downgrades to a warning, scenario still valid"),
]


def run(fixture: str, portfolio: str | None):
    cmd = [sys.executable, str(VALIDATOR), str(FIX / fixture), "--format", "json"]
    if portfolio:
        cmd += ["--portfolio", str(FIX / portfolio)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
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
    for fixture, portfolio, exp_exit, predicate, desc in CASES:
        code, result, out, err = run(fixture, portfolio)
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
        label = fixture + (f" +{portfolio}" if portfolio else "")
        if problems:
            failed += 1
            print(f"FAIL  {label:46} {desc}")
            for p in problems:
                print(f"        - {p}")
            if err.strip():
                print(f"        stderr: {err.strip()[:200]}")
        else:
            passed += 1
            extra = ""
            if result and "summary" in result:
                extra = f"  {result['summary']}  ({result.get('schema_source')})"
            print(f"PASS  {label:46} exit={code}{extra}")

    print(f"\n{passed} passed, {failed} failed  ({passed + failed} total)")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
