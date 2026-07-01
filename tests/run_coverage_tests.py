#!/usr/bin/env python3
"""Full schema-coverage test for the QPortfolio authoring skills.

Two assertions, run against the bundled schemas the skills actually ship:

  1. Validity   - every golden fixture validates CLEAN through the skill's own
                  validator (exit 0, schema_errors == 0, hard_errors == 0).
                  Scenario fixtures are cross-referenced against the portfolio
                  fixture via --portfolio.
  2. Coverage   - coverage_check.py confirms the fixtures, taken together, exercise
                  EVERY property path and EVERY enum value in each schema.

The golden prompt for each fixture lives in PROMPTS.md; generating a fixture from
its prompt is the interactive (non-deterministic) surface and is NOT run here.

Run:  python run_coverage_tests.py
Exit: 0 if every check passes, 1 otherwise.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
PLUGIN_DIR = TESTS_DIR.parent
SKILLS = PLUGIN_DIR / "skills"

PORTFOLIO_VALIDATOR = SKILLS / "generate-portfolio-file" / "scripts" / "validate_portfolio.py"
SCENARIO_VALIDATOR = SKILLS / "generate-scenario-file" / "scripts" / "validate_scenario.py"
PORTFOLIO_SCHEMA = SKILLS / "generate-portfolio-file" / "schemas" / "portfolio.schema.json"
SCENARIO_SCHEMA = SKILLS / "generate-scenario-file" / "schemas" / "scenario.schema.json"
COVERAGE_CHECK = TESTS_DIR / "coverage_check.py"

PORTFOLIO_FIXTURE = TESTS_DIR / "portfolio" / "portfolio_full_coverage.json"
SCENARIO_FIXTURES = [
    TESTS_DIR / "scenario" / "scenario_full_coverage.json",
    TESTS_DIR / "scenario" / "scenario_enum_minimize.json",
    TESTS_DIR / "scenario" / "scenario_enum_linearization.json",
]


def _run(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    try:
        result = json.loads(proc.stdout) if proc.stdout.strip() else None
    except json.JSONDecodeError:
        result = None
    return proc.returncode, result, proc.stdout, proc.stderr


def _is_clean(result):
    if not isinstance(result, dict) or "summary" not in result:
        return False, "no JSON summary"
    s = result["summary"]
    ok = result.get("ok") and s["schema_errors"] == 0 and s["hard_errors"] == 0
    return ok, f"ok={result.get('ok')} summary={s}"


def main():
    if not COVERAGE_CHECK.is_file():
        print(f"FATAL: coverage_check.py not found at {COVERAGE_CHECK}")
        return 1
    try:
        from jsonschema import Draft202012Validator  # noqa: F401
    except ImportError:
        print("FATAL: the validators need 'jsonschema' >= 4.18 (Draft 2020-12). "
              "Run: pip install --upgrade 'jsonschema>=4.18'")
        return 1

    passed = failed = 0

    def check(label, ok, detail):
        nonlocal passed, failed
        if ok:
            passed += 1
            print(f"PASS  {label}")
        else:
            failed += 1
            print(f"FAIL  {label}")
            print(f"        - {detail}")

    # 1. Validity: portfolio fixture validates clean.
    code, result, out, err = _run([
        sys.executable, str(PORTFOLIO_VALIDATOR), str(PORTFOLIO_FIXTURE),
        "--schema", str(PORTFOLIO_SCHEMA), "--format", "json"])
    ok, detail = _is_clean(result)
    check("validate portfolio_full_coverage.json (clean)", code == 0 and ok,
          f"exit={code} {detail} stderr={err.strip()[:200]}")

    # 1. Validity: each scenario fixture validates clean, cross-ref'd to the portfolio.
    for fx in SCENARIO_FIXTURES:
        code, result, out, err = _run([
            sys.executable, str(SCENARIO_VALIDATOR), str(fx),
            "--schema", str(SCENARIO_SCHEMA),
            "--portfolio", str(PORTFOLIO_FIXTURE), "--format", "json"])
        ok, detail = _is_clean(result)
        check(f"validate {fx.name} (clean, --portfolio)", code == 0 and ok,
              f"exit={code} {detail} stderr={err.strip()[:200]}")

    # 2. Coverage: portfolio schema fully covered by the portfolio fixture.
    code, _, out, err = _run([
        sys.executable, str(COVERAGE_CHECK),
        "--schema", str(PORTFOLIO_SCHEMA), str(PORTFOLIO_FIXTURE)])
    check("coverage: portfolio schema fully covered", code == 0,
          f"exit={code}\n{out}{err}".rstrip())

    # 2. Coverage: scenario schema fully covered by the scenario fixtures together.
    code, _, out, err = _run([
        sys.executable, str(COVERAGE_CHECK),
        "--schema", str(SCENARIO_SCHEMA), *[str(f) for f in SCENARIO_FIXTURES]])
    check("coverage: scenario schema fully covered", code == 0,
          f"exit={code}\n{out}{err}".rstrip())

    print(f"\n{passed} passed, {failed} failed  ({passed + failed} total)")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
