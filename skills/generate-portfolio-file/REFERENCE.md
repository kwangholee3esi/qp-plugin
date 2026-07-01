# Reference — generating a QPortfolio portfolio file

Deep guidance for the `generate-portfolio-file` skill. The authoritative structure
is always the schema itself (`schemas/portfolio.schema.json`, or the in-repo
`server/Esi.Sp.Portable/Schemas/portfolio.schema.json`), which carries a
description and `examples` for every field. This file adds domain meaning and the
rules the schema can't express.

## Domain model (grounded in the QP vault)

- **Opportunity** — an investment candidate the optimizer may select. Its
  **input data** is the time-series and scalar data (capex, opex, production,
  reserves, …) that characterises it and that *shifts and scales with selection*
  (`wiki/concepts/portfolio-model.md`; `wiki/expressions/dataconsiderations.md`).
- **Outcome** — a possible realisation of an opportunity. A **certain**
  opportunity has a single outcome; an **uncertain** one has several **weighted**
  outcomes (e.g. P90/P50/P10). The probability-weighted **expected value** is what
  optimization, calculations and constraints use — optimization does NOT run a
  Monte Carlo simulation, it optimizes on expected values
  (`wiki/expressions/dataconsiderations.md`). You may add as many outcomes to an
  opportunity as needed (`wiki/expressions/dataconsiderations.md`).
- **Metric** — a model variable: **input**, **master data**, or **computed**; a
  metric may be a time series or an **indicator** (single scalar value). Metrics
  may differ from one opportunity to another (`wiki/concepts/metric.md`).
- **Master data** — array inputs constant period-to-period but varying across
  periods and sets (price decks, FX, inflation, fiscal params), matched to
  opportunities via attributes; a **default set with no attributes must always
  exist** (schema `master_data` description; `wiki/concepts/metric.md`).
- **Attributes** — descriptive characteristics (Country, Reserve Type, …) used to
  group/filter/match (`wiki/concepts/metric.md`).
- **Outcome dependency** — probabilistic correlation: when an independent
  opportunity samples a given outcome, the dependent opportunity's outcome weights
  are replaced. `"*"` means "all independent outcomes not listed explicitly"
  (`wiki/concepts/outcome-dependency.md`; `wiki/rules/rules-outcome-dependencies.md`).
- **Selection rules** — `selection_constraints` (per-opportunity how-many/when
  limits), `selection_dependency` (one opportunity's selectability depends on
  another's), `selection_group` (mutually inclusive/exclusive sets). These are
  scenario-varying selection rules; outcome dependency is versioned data.

**The cardinal rule** (`wiki/expressions/dataconsiderations.md`): *Opportunity
names must be unique, and the names used in Input Data, Attributes and Selection
Constraints must match each other exactly.* Names are the only identifier. This is
the rule the validator most exists to protect, because nothing else enforces it.

## Authoring conventions

- `metadata.qp_file_type` must be exactly `"QPortfolio Data"`. Include
  `qp_version` (e.g. `4.5`) for traceability.
- snake_case keys; enums as strings (`Must`/`MustNot`, `OverAll`/`Before`/`After`/
  `During`, `MutualInclusive`/`MutualExclusive`).
- Omit optional fields rather than writing `null`. Never emit `NaN`/`Infinity`.
- One consistent **input** horizon: every non-scalar `values` array should have
  the same length (the number of input time periods). Scalar metrics
  (`scalar: true`) carry exactly one value. Missing input metrics default to 0 —
  omit rather than zero-pad only when you mean "no data". This input length is
  independent of the selection-constraint period arrays (see "Input periods vs
  planning horizon").
- Single-outcome opportunity: name the outcome (e.g. `"Base"`), `weight` optional.
  Multi-outcome: give every outcome a non-negative `weight`; they need not sum to
  1 (the importer normalizes), but should be sensible probabilities.
- An opportunity referenced by a rule/group/dependency/attribute must exist in
  `input_data.opportunity_outcomes`. Outcome names referenced in an outcome
  dependency must be real outcomes of the named opportunity (or `"*"` on the
  independent side).

### Field limits & schema-enforced constraints

The synced schema enforces these directly (a violation is a hard schema error),
so author within them:

- **String max lengths** (names must be non-empty): `opportunity_name` ≤ 255,
  `outcome_name` ≤ 255, `metric_name` ≤ 450, attribute name & characteristic
  value ≤ 450, `group_name` ≤ 255, `unit` ≤ 128, color ≤ 32, data-version name
  ≤ 255.
- **Numeric ranges**: outcome and dependency `weight` ≥ 0; attribute `order`
  0–999999; limit quantities (`total_*`, `time_period_*`) ≥ 0; `interior_limit`
  strictly between 0 and 1; selection-dependency `each_scale`/`need_scale` > 0.
- **Uniqueness** (`uniqueKeys`): see the check catalog — names must be unique
  within their array.

## Input periods vs planning horizon

Two different period axes — keep them separate; do NOT couple their lengths:

- **Input time periods** — the index of each metric `values` array (`values[0]` =
  period 0, …). All non-scalar series in an outcome share this length (the input
  horizon). Governs the *data*.
- **Planning (selection) periods** — the portfolio's eligible periods that the
  selection-constraint arrays (`time_period_minima`/`time_period_maxima`) are
  indexed over — the vault's "a column … for each period in your portfolio" /
  "eligible time periods" (`wiki/rules/the-selection-constraints-tab.md`).
  Governs the *decision*.

These are INDEPENDENT. A portfolio can carry, say, 3 input periods while selection
is decided over a single planning period — never pad `time_period_*` just to match
the metric-series length. Authoritative facts
(`wiki/concepts/selection-constraint.md`, `wiki/rules/the-selection-constraints-tab.md`):

- `total_minimum`/`total_maximum` apply across ALL eligible periods *in aggregate*
  — `total_maximum: 1` means "at most one selection over the whole span."
- `time_period_maxima` defines the periods in which selection is actually allowed.
  **On Portable JSON import, an opportunity with no positive per-period maximum is
  never selected** — an empty `time_period_maxima: []` leaves it unselectable even
  with `total_maximum: 1`. So always give a non-empty selection horizon; the
  default is a single period `[1]`. (The help-site Selection Constraints tab
  documents a blank UI cell as "unbounded"; the JSON import path is stricter —
  trust this observed import behaviour over the UI doc. The validator cannot detect
  it, since it only checks schema/semantics, not selectability.)
- This selection-horizon length is INDEPENDENT of the metric-series length: a
  3-period input series still defaults to a 1-period selection horizon `[1]`. Make
  it longer only when selection is decided over multiple planning periods (e.g.
  `[1, 1, 1]` = "at most one per period across 3 planning periods").
- A per-period **Max of `0` forbids** selection in that period; a positive Max caps
  it. A per-period **Min** forces selection; omit minima (`time_period_minima: []`)
  to keep selection optional.

So the sensible default is `total_maximum: 1` with `time_period_maxima: [1]`. Reach
for a multi-period selection horizon only when the user wants genuinely per-period
behaviour (e.g. "at most one per year" with a higher `total_maximum`, or
forcing/forbidding a specific period).

## Ask vs default

**Ask the user** (blocks a valid/meaningful file):
- Opportunity names are missing or ambiguous (they are the unique identifiers).
- No metric names given for an opportunity.
- Horizon (number of periods) unknown.
- An opportunity is implied risky but its certainty is unstated — certain (single
  outcome) vs uncertain (which weighted outcomes + probabilities).
- A described rule references an opportunity/outcome/group you didn't define —
  ask whether to add the entity or fix the name (never invent silently).
- A domain term you can't resolve from this file or the vault.

**Default silently** (note assumptions in your summary):
- Single outcome → `outcome_name: "Base"`, weight omitted.
- No `unit` → omit. `scalar` unspecified → omit (time series).
- No master_data/attributes/dependencies/groups mentioned → omit those sections.
- **Selection limits unspecified → default each opportunity to `total_minimum: 0`,
  `total_maximum: 1`, `time_period_minima: []`, `time_period_maxima: [1]`** (one
  `opportunity_limits` entry per opportunity). The `[1]` is a single-period
  selection horizon — it MUST be non-empty or the opportunity is never selected on
  import, and its length is independent of the metric-series length (see "Input
  periods vs planning horizon"). Honor any limits the user states explicitly
  instead of the default; never fabricate other `0/0` bounds.
- Declared-but-missing metric values → omit or zero-fill to the horizon.

## Validator CLI

```
python scripts/validate_portfolio.py <file.json> [--schema PATH] [--format json|text] [--strict-nulls]
```

Exit codes: `0` valid (warnings allowed) · `1` invalid (schema and/or hard
errors) · `2` IO/parse error (missing file, bad JSON, or NaN/Infinity) · `3`
environment error (`jsonschema` not installed, or no schema found).

**PowerShell fallback (no Python).** When Python is unavailable, the bundled
`scripts/validate_portfolio.ps1` (Windows PowerShell 5.1+, no modules) is a
drop-in replacement — same flags, same exit codes, identical JSON output and
schema discovery:

```
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/validate_portfolio.ps1 <file.json> [--schema PATH] [--format json|text] [--strict-nulls]
```

It has no `jsonschema` dependency, so its exit `3` means only "no schema found".
The Python validator stays the source of truth; `tests/conformance_ps.py` asserts
the two agree on every fixture.

JSON output:
```jsonc
{
  "ok": false,
  "schema_path_used": "…/portfolio.schema.json",
  "schema_source": "server-in-repo" | "bundled" | "explicit",
  "summary": { "schema_errors": 0, "hard_errors": 2, "warnings": 3 },
  "schema_errors": [ { "json_path", "message", "validator" } ],
  "semantic":      [ { "severity": "error"|"warning", "check", "json_path",
                       "message", "offending_value", "hint" } ],
  "drift_warning": "…"   // only if bundled schema differs from server copy
}
```
Drive the repair loop off `summary` (continue while `schema_errors` or
`hard_errors` > 0) and fix each finding at its `json_path` using `hint`.

## Check catalog (semantic — beyond JSON Schema)

JSON Schema covers structure, types, enums, `required`,
`additionalProperties:false`, **value constraints (string `maxLength`/`minLength`,
numeric `minimum`/`maximum`/`exclusive*`, `pattern`)**, and **per-array
uniqueness via the custom `uniqueKeys` keyword** (the validator registers a
handler for it — see "Schema-enforced constraints" below). The semantic layer
adds the cross-field / cross-reference / shape rules JSON Schema cannot express.
**HARD** = blocks the write; **WARN** = reported, still writes.

Uniqueness is now **schema-enforced** (`uniqueKeys`, surfaced as schema errors,
HARD): `opportunity_name` within `input_data` and within `master_data`,
`outcome_name` within an opportunity, `metric_name` within an outcome,
`group_name` (groups & group_limits), `opportunity_name` in `opportunity_limits`,
`opportunity_attributes`, and group `members`, and `attribute` within one row's
characteristics.

Referential integrity → must resolve to an `input_data` opportunity (HARD):
outcome_dependency independent/dependent; selection_constraints opportunity_name;
selection_dependency dependent/independent; selection_group `members.opportunity_name`;
attribute rows (∈ input, or ∈ input∪master when `is_master_data: true`);
group_limits `group_name` → a defined group.

Outcome-name integrity (HARD): `target_cases[].independent_outcomes` are `"*"` or
real outcomes of the independent opportunity; `outcome_weights[].dependent_outcomes`
are real outcomes of the dependent opportunity. Same independent outcome mapped by
two cases → HARD. Self-dependency → WARN.

Numeric ordering (HARD; applies to `opportunity_limits` and `group_limits`) — the
cross-field comparisons the schema can't express: `total_maximum ≥ total_minimum`;
`total_instances_maximum ≥ total_instances_minimum`; per-index
`time_period_maxima[i] ≥ time_period_minima[i]`. (Single-field non-negativity is
schema-enforced via `minimum: 0`.) `interior_limit > total_maximum` → WARN;
`integer_only` + `interior_limit` → WARN.

Time series: `scalar: true` ⇒ exactly one value (HARD); empty non-scalar series
and differing series lengths within an outcome → WARN.

Other: `metadata.qp_file_type` exactly `"QPortfolio Data"` (HARD); negative
outcome `weight` (HARD); missing weight on a multi-outcome opportunity (WARN);
attribute used but not declared in `attributes.attributes` (WARN); duplicate
`order` (WARN); `qp_version` not numeric (WARN); when `master_data` is present, a
default (attribute-free) set must exist (HARD). NaN/Infinity literals are rejected
at parse time (exit 2). Explicit `null` for optional fields → WARN only under
`--strict-nulls`.

> Note: the importer is deliberately permissive (it asserts only `qp_file_type`),
> so a file can be schema-valid yet semantically broken. The committed sample
> `server/TestData/Json/portfolio-data.json` itself has a `selection_dependency`
> referencing opportunities `"A"`/`"D"` that don't exist — schema-valid, but the
> validator (correctly) flags it. Generated files must be clean.

## Maintaining the bundled schema

The schema is **generated** from `server/Esi.Sp.Portable/Types/*.cs` and their
`[Description]` attributes — never hand-edit it (server copy or bundled). When the
C# types change:

1. Regenerate the server schema (see `server/Esi.Sp.Portable/Schemas/README.md`):
   ```
   UPDATE_PORTABLE_SCHEMAS=1 dotnet test Esi.Sp.Portable.Tests --filter Committed_schema_matches_generator_output
   ```
2. Refresh the bundled copy + provenance:
   ```
   python scripts/sync_schema.py
   ```

`.schema-sync.json` records the source path, sha256, and `qp_version`. When the
validator runs inside the repo it prefers the live server schema and warns if the
bundled copy has drifted.
