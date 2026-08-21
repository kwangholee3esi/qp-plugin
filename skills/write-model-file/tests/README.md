# Tests — write-model-file

Two test surfaces:

## 1. Validator regression (deterministic)

`run_tests.py` runs the bundled validator against `fixtures/` and asserts exit
codes + summary counters.

```
python tests/run_tests.py        # from the skill directory
```

Fixtures:
- `valid_minimal.json` — one input + one computed metric → exit 0
- `valid_kitchen_sink.json` — recursion via `first_period_formula`, filtering by
  exception (`order` + `criteria`), Group level + `group_by`, derived metrics,
  a hidden interim metric, attributes → exit 0, no warnings
- `valid_attributes_only.json` — attributes-only split file (no `metrics` key) → exit 0
- `broken_semantic.json` — **schema-valid but semantically broken**: expressions on
  a non-computed metric, a computed metric with none, a reserved `#CumSum` name, a
  Group metric without `group_by`, an undefined `${ref}`, an undefined derived
  origin, a case-insensitive duplicate name, a whitespace-only name. Proves the
  validator catches the naming/type/reference rules JSON Schema cannot express →
  exit 1, `schema_errors == 0`, `hard_errors >= 4`.
- `bad_schema_constraints.json` — **schema-invalid**: braces in a name (`pattern`),
  an over-length `unit` (`maxLength`), a wrong-case enum value (`enum`), an empty
  `group_by` (`minItems`), a negative `order` (`minimum`), a duplicate name
  (`uniqueKeys`) → exit 1 with those JSON-Schema keywords firing.
- `bad_formula.json` — the formula tokenizer: unbalanced parentheses, `POWER(...)`
  (unknown function), wrong argument counts, the `FlagUpToMax` macro, a bare
  unwrapped metric name → exit 1, 6 hard errors.
- `warn_lint.json` — authoring-lint warnings that never block the write: computed
  metric with no `level`, ignored `group_by`, criteria on a Scenario-level metric,
  outcome filter at Opportunity level, undeclared attributes, duplicate expression
  `order`, `&` (silently discarded), `1e5` (unsigned exponent), `GetIRR` → exit 0,
  10 warnings.
- `warn_derived.json` — derived-metric guidance: `derived` on an
  Instance-scaled metric and on non-linear computed origins (Max(...), a
  product of two non-master-data metrics) warns; a linear × master-data origin
  stays clean → exit 0, 3 warnings.
- `warn_empty_metrics.json` — `"metrics": []` deletes every computed metric on
  import → exit 0 with a warning.
- `bad_nan.json` — `NaN` literal → exit 2.

Requires `jsonschema` **>= 4.18** (the schemas use Draft 2020-12):
`pip install --upgrade 'jsonschema>=4.18'`.

## 2. Skill authoring (interactive)

Invoke the skill itself (e.g. `/write-model-file ...`) and have it write the
generated file under `output/`. That directory is git-ignored — it holds
throwaway artifacts from manual/agent test runs, not source.
