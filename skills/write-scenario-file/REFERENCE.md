# Reference — generating a QPortfolio scenario file

Deep guidance for the `write-scenario-file` skill. The authoritative structure
is always the schema itself (`schemas/scenario.schema.json`), which carries a
description and `examples` for every field. This file adds domain meaning and the
rules the schema can't express.

## What a scenario is (grounded in the QP vault)

A **scenario** is a single **"what-if" case** within a portfolio. Crucially it does
**not** define opportunities or their input metrics — those live in the portfolio;
a scenario file references portfolio names and layers optimization, metric limits,
selections, rule overrides and settings on top.

The schema describes each of those sections. These are the vault pages behind them:

- Scenario, active scenario — `wiki/concepts/scenario.md`,
  `wiki/concepts/active-scenario.md`
- Optimization — `wiki/concepts/optimization.md`
- Metric limits, including soft constraints — `wiki/concepts/metric-constraint.md`,
  `wiki/active-scenarios/soft-constraints.md`
- Rule overrides — `wiki/active-scenarios/scenario-rules.md`
- Settings — `wiki/active-scenarios/scenario-data.md`

## Rule sections are all-or-nothing overrides

The schema says each rule section is overridden when present and inherited when
absent. What that means for authoring: **emit a rule section only when overriding
it, and when you do, emit the COMPLETE set** — seeded from the portfolio's defaults
plus the user's change, because it is section-level replacement, not a merge.

Within `selection_group`, group limits take precedence over members' individual
selection constraints while active (`wiki/rules/the-selection-groups-tab.md`).

## Authoring conventions

- `metadata.qp_file_type` must be exactly `"QPortfolio Scenario Data"`. Include
  `qp_version` for traceability — use the bundled schema's own `qp_version`
  (currently `4.5`) unless the user states their product version.
- snake_case keys; enums as strings — the schema's `enum` lists spell them.
- Omit optional fields rather than writing `null`. Never emit `NaN`/`Infinity`.
- Keep the objective metric name exactly as the portfolio names it.

## Objective & metric names may be computed metrics

The objective metric and a metric limit may reference a **computed/expression**
metric (e.g. `"Discounted Cash Flow ($ MM) @13% - With Expression"`) that does NOT
appear in the portfolio's `input_data`. So when cross-checking against a portfolio,
a *missing metric name* is reported only as a **warning** (it may be computed),
whereas a *missing opportunity name* — opportunities are fully enumerable in the
portfolio — is a **hard error**.

## Ask vs default

**Ask the user** (blocks a meaningful file):
- The scenario name is missing.
- The optimization objective metric is unstated (and no portfolio is available to
  pick one from). Direction defaults to maximize, so only ask if ambiguous.
- A described limit/override references an opportunity or metric you can't resolve
  — ask whether to fix the name or which portfolio it belongs to (never invent).
- A domain term you can't resolve from this file or the vault.

**Default silently** (note assumptions in your summary):
- `optimization.direction` → `"Maximize"` when unstated.
- No metric limits described → omit `metric_limits`.
- No rule overrides described → omit `selection_constraints` /
  `selection_dependency` / `selection_group` (inherit the portfolio's).
- Selections not pinned by the user → omit `opportunity_selections` (the solver
  fills them in-app).
- Advanced solver fields (tolerances, timeout, linearization, local solver,
  Lindo `solver_parameters`, penalty weights) → omit unless asked.
- Colour, description, data version, characteristics → omit unless given.

## Validator CLI

```
python scripts/validate_scenario.py <file.json> [--schema PATH] [--portfolio PATH] [--format json|text] [--strict-nulls]
```

Pass `--portfolio` whenever a companion portfolio is available so opportunity/metric
names are cross-checked. Exit codes: `0` valid (warnings allowed) · `1` invalid
(schema and/or hard errors) · `2` IO/parse error (missing file, bad JSON, or
NaN/Infinity) · `3` environment error (`jsonschema` not installed, or no schema
found).

**PowerShell fallback (no Python).** When Python is unavailable, the bundled
`scripts/validate_scenario.ps1` (Windows PowerShell 5.1+, no modules) is a
drop-in replacement — same flags (incl. `--portfolio`), same exit codes, identical
JSON output and schema discovery:

```
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/validate_scenario.ps1 <file.json> [--schema PATH] [--portfolio PATH] [--format json|text] [--strict-nulls]
```

It has no `jsonschema` dependency, so its exit `3` means only "no schema found".
The Python validator stays the source of truth.

JSON output:
```jsonc
{
  "ok": false,
  "schema_path_used": "…/scenario.schema.json",
  "schema_source": "bundled" | "explicit",
  "portfolio_path_used": "…/portfolio.json" | null,
  "summary": { "schema_errors": 0, "hard_errors": 2, "warnings": 3 },
  "schema_errors": [ { "json_path", "message", "validator" } ],
  "semantic":      [ { "severity": "error"|"warning", "check", "json_path",
                       "message", "offending_value", "hint" } ]
}
```
Drive the repair loop off `summary` (continue while `schema_errors` or
`hard_errors` > 0) and fix each finding at its `json_path` using `hint`. A bad or
missing `--portfolio` downgrades to a warning (cross-ref skipped), it does not fail
the run; with no `--portfolio` at all you get a single `crossref.unchecked` warning.

## Check catalog (semantic — beyond JSON Schema)

JSON Schema covers structure, types, enums, `required`,
`additionalProperties:false`, **value constraints (string `maxLength`/`minLength`,
numeric `minimum`/`maximum`/`exclusive*`, the `color` `pattern`)**, and **per-array
uniqueness via the custom `uniqueKeys` keyword** (the validator registers a
handler for it). The semantic layer adds
the cross-field / cross-reference rules JSON Schema cannot express. **HARD** =
blocks the write; **WARN** = reported, still writes.

Uniqueness is **schema-enforced** (`uniqueKeys`, surfaced as schema errors, HARD) on
every array that carries the keyword. (`opportunity_selections` is the exception — no `uniqueKeys` backs it, so a
duplicate `opportunity_name` there is still a semantic HARD error.)

Metadata (HARD): `metadata.qp_file_type` exactly `"QPortfolio Scenario Data"`.
`qp_version` not numeric → WARN.

Settings (WARN): no `settings` block; blank `scenario_name`. (Its single-field
ranges and patterns are schema-enforced.)

Optimization: missing/blank `objective_metric_name` → WARN; negative
`objective_time_period` → HARD. (Single-field ranges are schema-enforced.)

Metric limits: missing `limit_type` → WARN; negative target `period` → HARD;
`soft: true` while `settings.enable_soft_constraints` is not true → WARN.

Opportunity selections: duplicate `opportunity_name` → HARD (semantic); negative
selection `period` or `value` → HARD.

Selection rules — numeric ordering (applies to `opportunity_limits` and
`group_limits`), the cross-field comparisons the schema can't express:
`total_maximum ≥ total_minimum` and
`total_instances_maximum ≥ total_instances_minimum` are HARD. Per-index
`time_period_maxima[i] ≥ time_period_minima[i]` is only WARN, for the reason the
schema gives. (Single-field non-negativity is schema-enforced.) `interior_limit > total_maximum` → WARN; `integer_only` +
`interior_limit` → WARN. `group_limits.group_name` with no matching group → HARD.
Selection dependency: dependent == independent → WARN; duplicate
(dependent, independent) pair → WARN.

Cross-reference (only with `--portfolio`): every opportunity name in
`opportunity_selections`, `selection_constraints.opportunity_limits`,
`selection_dependency` (dependent/independent), and `selection_group` members must
exist in the portfolio (HARD). `optimization.objective_metric_name` and every
`metric_limits[].metric_name` should exist among the portfolio's input/master
metrics, else WARN (it may be a computed metric). Without `--portfolio`: one
`crossref.unchecked` WARN.

Other: NaN/Infinity literals are rejected at parse time (exit 2). Explicit `null`
for optional fields → WARN only under `--strict-nulls`.

> Note: the importer is deliberately permissive (it asserts only `qp_file_type`),
> so a file can be schema-valid yet reference names no portfolio defines. Only the
> `--portfolio` cross-ref catches that — always pass it when you can.

## The bundled schema

The schema is **generated** from the QPortfolio server's own type definitions —
never hand-edit it, and never contradict it here. It ships with the skill and is
refreshed whenever the product's file format changes; its `qp_version` records
which product version it came from.
