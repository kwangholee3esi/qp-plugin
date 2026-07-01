# Tests — generate-portfolio-file

Two test surfaces:

## 1. Validator regression (deterministic)

`run_tests.py` runs the bundled validator against `fixtures/` and asserts exit
codes + summary counters.

```
python tests/run_tests.py        # from the skill directory
```

Fixtures:
- `valid_minimal.json` — one certain opportunity → exit 0
- `valid_uncertain_rules.json` — uncertain (P90/P50/P10) + outcome dependency + constraint → exit 0
- `valid_master_attrs_group.json` — master data + attributes + selection group → exit 0
- `valid_selection_dependency.json` — selection dependency (direction check) → exit 0
- `broken_semantic.json` — **schema-valid but semantically broken**: bogus
  outcome-dependency outcome names, `total_maximum < total_minimum`,
  `time_period_maxima < minima`, group member not in `input_data`. Proves the
  validator catches the cross-field/cross-reference rules JSON Schema cannot
  express → exit 1, `schema_errors == 0`, `hard_errors >= 4`. (Uniqueness and
  single-field ranges are now enforced by the schema, so this fixture carries
  none of those.)
- `bad_schema_constraints.json` — **schema-invalid**: an over-length
  `opportunity_name` (`maxLength`), a negative `weight` (`minimum`), and a
  duplicate `opportunity_name` (`uniqueKeys`). Proves the synced value
  constraints — including the custom `uniqueKeys` keyword — are enforced → exit 1
  with those JSON-Schema keywords firing.
- `bad_nan.json` — `NaN` literal → exit 2.

Requires `jsonschema` **>= 4.18** (the schemas use Draft 2020-12):
`pip install --upgrade 'jsonschema>=4.18'`.

## 2. Skill authoring (interactive)

Invoke the skill itself (e.g. `/generate-portfolio-file ...`) and have it write
the generated file under `output/`. That directory is git-ignored — it holds
throwaway artifacts from manual/agent test runs, not source.
