#!/usr/bin/env python3
"""Cross-language conformance gate for the PowerShell fallback validators.

The Python validators (validate_*.py) are the source of truth; the PowerShell
validators (validate_*.ps1) are the no-Python fallback. This harness runs every
fixture through BOTH and asserts they agree, so the two implementations cannot
silently drift.

For each fixture it compares:
  - exit code
  - ok, schema_source, basename(schema_path_used), basename(portfolio_path_used)
  - summary {schema_errors, hard_errors, warnings}
  - schema_errors as an ORDERED (json_path, validator) sequence  (NOT message:
    jsonschema's wording cannot be reproduced; the repair loop keys on json_path)
  - semantic as an ORDERED list of full finding dicts (message included)

It also asserts the two bundled qp_validation_common.ps1 copies are byte-identical.

This is a manual pre-release gate. It SKIPS cleanly (exit 0) when PowerShell or
jsonschema is unavailable, so Linux / Python-less machines are not broken.

Run on Windows:  python tests/conformance_ps.py
Exit: 0 if every fixture agrees (or the gate is skipped), 1 on any mismatch.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
PLUGIN_DIR = TESTS_DIR.parent
SKILLS_DIR = PLUGIN_DIR / "skills"

PORTFOLIO = "generate-portfolio-file"
SCENARIO = "generate-scenario-file"


def find_powershell():
    for exe in ("pwsh", "powershell"):
        if shutil.which(exe):
            return exe
    return None


def have_jsonschema():
    try:
        from jsonschema import Draft202012Validator  # noqa: F401
        return True
    except ImportError:
        return False


def fixtures_for(skill):
    return sorted((SKILLS_DIR / skill / "tests" / "fixtures").glob("*.json"))


def build_runs():
    """List of (skill, validator_stem, fixture_path, portfolio_path_or_None)."""
    runs = []
    for fx in fixtures_for(PORTFOLIO):
        runs.append((PORTFOLIO, "validate_portfolio", fx, None))
    fix = SKILLS_DIR / SCENARIO / "tests" / "fixtures"
    sample = fix / "sample_portfolio.json"
    for fx in fixtures_for(SCENARIO):
        runs.append((SCENARIO, "validate_scenario", fx, None))
    # cross-reference path: same scenario file WITH a portfolio
    if (fix / "crossref_bad.json").is_file() and sample.is_file():
        runs.append((SCENARIO, "validate_scenario", fix / "crossref_bad.json", sample))
    # unreadable --portfolio downgrades to a warning (must agree across engines)
    if (fix / "valid_minimal.json").is_file():
        runs.append((SCENARIO, "validate_scenario", fix / "valid_minimal.json",
                     fix / "does_not_exist_portfolio.json"))
    return runs


def run_python(skill, stem, fixture, portfolio):
    script = SKILLS_DIR / skill / "scripts" / f"{stem}.py"
    cmd = [sys.executable, str(script), str(fixture), "--format", "json"]
    if portfolio:
        cmd += ["--portfolio", str(portfolio)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, parse_json(p.stdout), p.stdout, p.stderr


def run_powershell(pwsh, skill, stem, fixture, portfolio):
    script = SKILLS_DIR / skill / "scripts" / f"{stem}.ps1"
    cmd = [pwsh, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
           str(fixture), "--format", "json"]
    if portfolio:
        cmd += ["--portfolio", str(portfolio)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, parse_json(p.stdout), p.stdout, p.stderr


def parse_json(text):
    try:
        return json.loads(text) if text and text.strip() else None
    except json.JSONDecodeError:
        return None


def schema_pairs(result):
    return [(e.get("json_path"), e.get("validator")) for e in (result.get("schema_errors") or [])]


def normalize_semantic(result):
    """Findings, with messages that legitimately can't match across engines blanked.

    crossref.portfolio_unreadable passes the loader's error text through verbatim
    (Python OSError vs the PowerShell read error); everything else about the
    finding is still compared strictly."""
    norm = []
    for f in (result.get("semantic") or []):
        g = dict(f)
        if g.get("check") == "crossref.portfolio_unreadable":
            g["message"] = "<loader-error>"
        norm.append(g)
    return norm


def base(path):
    return os.path.basename(path) if path else path


def compare(py_code, py, ps_code, ps):
    """Return a list of human-readable difference strings (empty == match)."""
    diffs = []
    if py_code != ps_code:
        diffs.append(f"exit code: python={py_code} powershell={ps_code}")
    # io (2) / environment (3) errors carry paths/exception text we don't reproduce;
    # exit-code agreement is the contract there.
    if py_code in (2, 3) or ps_code in (2, 3):
        return diffs
    if py is None or ps is None:
        diffs.append(f"unparseable JSON (python={py is not None}, powershell={ps is not None})")
        return diffs
    if py.get("ok") != ps.get("ok"):
        diffs.append(f"ok: python={py.get('ok')} powershell={ps.get('ok')}")
    if py.get("schema_source") != ps.get("schema_source"):
        diffs.append(f"schema_source: python={py.get('schema_source')} powershell={ps.get('schema_source')}")
    if base(py.get("schema_path_used")) != base(ps.get("schema_path_used")):
        diffs.append(f"schema_path basename: python={base(py.get('schema_path_used'))} powershell={base(ps.get('schema_path_used'))}")
    if base(py.get("portfolio_path_used")) != base(ps.get("portfolio_path_used")):
        diffs.append(f"portfolio_path basename: python={base(py.get('portfolio_path_used'))} powershell={base(ps.get('portfolio_path_used'))}")
    if py.get("summary") != ps.get("summary"):
        diffs.append(f"summary: python={py.get('summary')} powershell={ps.get('summary')}")
    if schema_pairs(py) != schema_pairs(ps):
        diffs.append("schema_errors (json_path, validator) differ:")
        diffs.append(f"    python    : {schema_pairs(py)}")
        diffs.append(f"    powershell: {schema_pairs(ps)}")
    if normalize_semantic(py) != normalize_semantic(ps):
        diffs.append("semantic findings differ:")
        pys = normalize_semantic(py)
        pss = normalize_semantic(ps)
        for i in range(max(len(pys), len(pss))):
            a = pys[i] if i < len(pys) else None
            b = pss[i] if i < len(pss) else None
            if a != b:
                diffs.append(f"    [{i}] python    : {a}")
                diffs.append(f"    [{i}] powershell: {b}")
    return diffs


def check_common_copies():
    copies = [SKILLS_DIR / PORTFOLIO / "scripts" / "qp_validation_common.ps1",
              SKILLS_DIR / SCENARIO / "scripts" / "qp_validation_common.ps1"]
    hashes = []
    for c in copies:
        if not c.is_file():
            return f"missing shared core: {c}"
        hashes.append(hashlib.sha256(c.read_bytes()).hexdigest())
    if hashes[0] != hashes[1]:
        return ("the two qp_validation_common.ps1 copies differ (must be byte-identical); "
                "sync them before release")
    return None


def main():
    pwsh = find_powershell()
    if not pwsh:
        print("SKIP: no PowerShell (pwsh/powershell) on PATH; PS fallback not exercised.")
        return 0
    if not have_jsonschema():
        print("SKIP: jsonschema not installed; cannot run the Python source-of-truth validators.")
        return 0

    failures = 0

    drift = check_common_copies()
    if drift:
        print(f"FAIL  shared-core check: {drift}")
        failures += 1
    else:
        print("PASS  qp_validation_common.ps1 copies are byte-identical")

    for skill, stem, fixture, portfolio in build_runs():
        label = f"{skill}/{fixture.name}" + (f" +{portfolio.name}" if portfolio else "")
        py_code, py, py_out, py_err = run_python(skill, stem, fixture, portfolio)
        ps_code, ps, ps_out, ps_err = run_powershell(pwsh, skill, stem, fixture, portfolio)
        diffs = compare(py_code, py, ps_code, ps)
        if diffs:
            failures += 1
            print(f"FAIL  {label}")
            for d in diffs:
                print(f"        {d}")
            if ps_err.strip():
                print(f"        ps stderr: {ps_err.strip()[:300]}")
        else:
            print(f"PASS  {label}  (exit={py_code})")

    print(f"\n{'FAILED' if failures else 'OK'}: {failures} mismatch(es)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
