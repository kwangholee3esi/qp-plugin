# Tests — generate-scenario-file

Two test surfaces:

## 1. Validator regression (deterministic)

`run_tests.py` runs the bundled validator against `fixtures/` and asserts exit
codes + summary counters.

```
python tests/run_tests.py        # from the skill directory
```

Fixtures:
- `valid_minimal.json` — name + optimization objective → exit 0
- `valid_optimization_limits.json` — objective + a Maximum metric limit → exit 0
- `valid_overrides.json` — selection constraint + dependency + group overrides → exit 0
- `valid_pinned_selections.json` — pinned selections + soft metric limit + characteristic → exit 0
- `broken_semantic.json` — **schema-valid but semantically broken**: duplicate
  `opportunity_selections` (no schema `uniqueKeys` backs that array),
  `total_maximum < total_minimum`, `time_period_maxima < minima`, and a
  `group_limits` entry pointing at a nonexistent group. Proves the validator
  catches the cross-field/cross-reference rules JSON Schema cannot express → exit
  1, `schema_errors == 0`, `hard_errors >= 4`. (Most uniqueness and single-field
  ranges are now enforced by the schema, so this fixture omits those.)
- `bad_schema_constraints.json` — **schema-invalid**: a non-hex `color`
  (`pattern`), `instance_selection_threshold` = 0 (`exclusiveMinimum`), and a
  duplicate composite `metric_limits` key (`uniqueKeys` on
  `[/metric_name, /limit_type]`). Proves the synced value constraints — including
  the custom `uniqueKeys` keyword — are enforced → exit 1 with those JSON-Schema
  keywords firing.
- `bad_nan.json` — `NaN` literal → exit 2.
- `crossref_bad.json` — references opportunity `"Ghost Well"`. Run **without**
  `--portfolio` → exit 0 with a `crossref.unchecked` warning; run **with**
  `--portfolio sample_portfolio.json` → exit 1 with a hard `crossref.selection_opportunity`
  error.
- `sample_portfolio.json` — a minimal portfolio (opportunities `Well A`/`Well B`,
  metric `NPV ($ MM)`) used as the `--portfolio` cross-ref source.

Requires `jsonschema` **>= 4.18** (the schemas use Draft 2020-12):
`pip install --upgrade 'jsonschema>=4.18'`.

## 2. Skill authoring (interactive)

Invoke the skill itself (e.g. `/generate-scenario-file ...`) and have it write
the generated file under `output/`. That directory is git-ignored — it holds
throwaway artifacts from manual/agent test runs, not source.
