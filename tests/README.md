# Full schema-coverage tests

This area proves the two authoring skills can produce files that exercise **every
component, field, and enum value** in the QPortfolio Portable-JSON schemas, and that
those files validate cleanly.

It complements the per-skill regression tests under
`skills/*/tests/` (which prove the *validators* behave). Here the focus is
**schema coverage**: a machine check that nothing in the schema is left untested.

## What it asserts

`run_coverage_tests.py` runs two kinds of check against the **bundled** schemas the
skills ship (`skills/*/schemas/*.schema.json`):

1. **Validity** — every golden fixture validates clean through the skill's own
   validator: exit 0, `schema_errors == 0`, `hard_errors == 0` (warnings are allowed).
   Scenario fixtures are cross-referenced against the portfolio fixture with
   `--portfolio`.
2. **Coverage** — `coverage_check.py` walks each schema and confirms the fixtures,
   taken together, cover every property path (array levels collapsed to `[]`) and every
   non-null enum value. Any gap fails the test and is named.

## Layout

```
tests/
├── README.md                          # this file
├── PROMPTS.md                         # the golden prompt ↔ fixture pairing
├── coverage_check.py                  # schema-walking coverage checker
├── run_coverage_tests.py              # the test harness
├── portfolio/
│   └── portfolio_full_coverage.json   # every portfolio field + enum value
└── scenario/
    ├── scenario_full_coverage.json    # every scenario field; direction=Maximize, linearization_level=SolverDecide
    ├── scenario_enum_minimize.json    # direction=Minimize, linearization_level=AbsMinMax
    └── scenario_enum_linearization.json  # linearization_level=All
```

The scenario `optimization` block is a single object, so `direction` and
`linearization_level` can hold only one value per file. The two tiny
`scenario_enum_*` fixtures exist solely to supply the remaining enum values; the
coverage check unions all three scenario fixtures.

The fixtures deliberately populate *every* optional field with a real, non-null value —
the opposite of the skills' normal "omit optionals" guidance — because their job is total
coverage, not idiomatic minimalism.

## Run

```
python run_coverage_tests.py        # from this directory
```

Expect `6 passed, 0 failed`. Requires `jsonschema>=4.18` (Draft 2020-12), the same
dependency the validators use.

You can also run the coverage checker directly:

```
python coverage_check.py --schema ../skills/generate-portfolio-file/schemas/portfolio.schema.json \
    portfolio/portfolio_full_coverage.json
```

It prints `paths: N/N covered` / `enums: M/M values covered` and exits non-zero if any
path or enum value is missing.

## PowerShell fallback conformance (`conformance_ps.py`)

The skills ship a **PowerShell fallback** validator (`skills/*/scripts/validate_*.ps1`
+ a byte-identical `qp_validation_common.ps1`) for Windows machines with no Python.
`conformance_ps.py` is the gate that keeps it honest: it runs **every fixture** under
both `skills/*/tests/fixtures/` through the Python validator (the source of truth) AND
the PowerShell validator, and asserts they agree on exit code, `summary`, `ok`,
`schema_source`, the ordered `(json_path, validator)` schema-error sequence, and the
full ordered semantic findings. It also asserts the two `qp_validation_common.ps1`
copies are byte-identical.

```
python conformance_ps.py        # from this directory, on Windows
```

Run it on Windows **before releasing any change to a validator or schema**. It skips
cleanly (exit 0) when PowerShell or `jsonschema` is absent, so it is a no-op on
Linux / Python-less machines rather than a failure. It is the safety net for the
intentional Python↔PowerShell duplication — if the two implementations drift, it fails
with the exact fixture and field that differ.

## Two test surfaces

- **Automated (this harness)** — validates the committed golden JSON and asserts full
  coverage. Deterministic; safe for CI.
- **Interactive (PROMPTS.md)** — run each golden prompt through its skill in a fresh
  session and compare the output to the golden fixture. Non-deterministic (LLM-driven);
  a sanity check, not a CI assertion.

## Keeping coverage honest

The schemas are generated from the server C# types (see
`skills/*/REFERENCE.md` → "Maintaining the bundled schema"). When the schema gains a new
field or enum value, this test fails with the exact missing path until a fixture is
extended to cover it — that is the point.
