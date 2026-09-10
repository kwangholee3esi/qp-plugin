# Reference — generating a QPortfolio portfolio file

Deep guidance for the `write-portfolio-file` skill. The authoritative structure
is always the schema itself (`schemas/portfolio.schema.json`), which carries a
description and `examples` for every field. This file adds domain meaning and the
rules the schema can't express.

## Domain model (grounded in the QP vault)

The schema defines every field. These are the vault pages behind the concepts,
which the schema does not carry:

- **Opportunity** and its **input data** — `wiki/concepts/portfolio-model.md`,
  `wiki/expressions/data-considerations.md`
- **Outcome**, certain vs uncertain, weights — `wiki/expressions/data-considerations.md`.
  Worth stating plainly: optimization does **not** run a Monte Carlo simulation, it
  optimizes on the probability-weighted expected value.
- **Metric**, **master data**, **attributes** — `wiki/concepts/metric.md`
- **Outcome dependency** — `wiki/concepts/outcome-dependency.md`,
  `wiki/rules/rules-outcome-dependencies.md`
- **Selection rules** — `wiki/rules/the-selection-constraints-tab.md`. These vary by
  scenario; outcome dependency is versioned data.

**The cardinal rule** (`wiki/expressions/data-considerations.md`): *Opportunity
names must be unique, and the names used in Input Data, Attributes and Selection
Constraints must match each other exactly.* Names are the only identifier. This is
the rule the validator most exists to protect, because nothing else enforces it.

## Authoring conventions

- `metadata.qp_file_type` must be exactly `"QPortfolio Data"`. Include
  `qp_version` for traceability — use the bundled schema's own `qp_version`
  (currently `4.5`) unless the user states their product version.
- snake_case keys; enums as strings — the schema's `enum` lists spell them.
- Omit optional fields rather than writing `null`. Never emit `NaN`/`Infinity`.
- An omitted (or `null`) **section** leaves the portfolio's existing one alone on import;
  an EMPTY section (`[]`) is merged like any other section, and merging an empty list adds
  nothing. Omit what you have nothing to say about.
- One consistent **input** horizon: every non-scalar `values` array should have
  the same length (the number of input time periods). Scalar metrics
  (`scalar: true`) carry exactly one value. Missing input metrics default to 0 —
  omit rather than zero-pad only when you mean "no data". This input length is
  independent of the selection-constraint period arrays (see "Input periods vs
  planning horizon").
- **One-time amounts (capex-like).** A value that occurs once at decision time
  goes in as a **zero-padded series** (`[10, 0, 0]`) or a `scalar: true`
  single value — under the model's `Total()`/derived-`Total` both yield the
  amount itself. What silently breaks is a **flat series** (`[10, 10, 10]`):
  the model totals it to 3× the intended amount. Use a flat series only for a
  genuinely recurring per-period value.
- `attributes.opportunity_attributes[].is_order_global` — omit it when authoring a
  new portfolio, so `order` positions the opportunity within its own block. Set it
  to `true` only to pin an opportunity to a manually
  assigned position that a later re-import must preserve as-is — the usual case
  being master-data opportunities you do not want re-import to reshuffle.
  Either way `order` must still be distinct per opportunity.
- Single-outcome opportunity: name the outcome (e.g. `"Base"`), `weight` optional.
  Multi-outcome: give every outcome a `weight`; they need not sum to
  1 (the importer normalizes), but should be sensible probabilities.
- An opportunity referenced by a rule/group/dependency/attribute must exist in
  `input_data.opportunity_outcomes`. Outcome names referenced in an outcome
  dependency must be real outcomes of the named opportunity (or `"*"` on the
  independent side).

## Input periods vs planning horizon

The schema describes each field, including that an empty `time_period_maxima`
forbids selection in every period. What it cannot say is that these are **two
different period axes whose lengths are independent**:

- **Input time periods** — the index of each metric `values` array. All non-scalar
  series in an outcome share this length. Governs the *data*.
- **Planning (selection) periods** — what `time_period_minima`/`time_period_maxima`
  are indexed over (`wiki/concepts/selection-constraint.md`,
  `wiki/rules/the-selection-constraints-tab.md`). Governs the *decision*.

Never pad `time_period_*` just to match the metric-series length: a 3-period input
series still defaults to a 1-period selection horizon.

So the sensible default is `total_maximum: 1` with `time_period_maxima: [1]`. Reach
for a multi-period selection horizon only when the user wants genuinely per-period
behaviour (e.g. "at most one per year" with a higher `total_maximum`, or
forcing/forbidding a specific period). Note the validator cannot catch a
never-selectable opportunity — it checks schema and semantics, not selectability.

## settings — omit it unless the user names a date, a horizon or a rate

`settings` carries the portfolio's calculation calendar and its discounting and
inflation rates. **Leave it out by default.** When present it *replaces* the
portfolio's settings, so a block written from guesses overwrites the real numbers
of a live portfolio.

Author it only when the user actually states a start date, a planning horizon, or
a discount/inflation rate. Then:

- **`time_unit` cannot be changed by an import** — a portfolio that needs monthly or
  quarterly periods has to be created that way in the product.
- `adjustment_policy` is **separately optional**. Omit it to leave the portfolio's
  convention and both rates untouched — do that unless the user named a rate. If
  you do write it, **omitting `discount_date` clears any existing one** (the
  portfolio then discounts from its start date).

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
- No start date, planning horizon or discount/inflation rate mentioned → omit
  `settings` (see "settings — omit it unless…"). Never write it from defaults.
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
The Python validator stays the source of truth.

JSON output:
```jsonc
{
  "ok": false,
  "schema_path_used": "…/portfolio.schema.json",
  "schema_source": "bundled" | "explicit",
  "summary": { "schema_errors": 0, "hard_errors": 2, "warnings": 3 },
  "schema_errors": [ { "json_path", "message", "validator" } ],
  "semantic":      [ { "severity": "error"|"warning", "check", "json_path",
                       "message", "offending_value", "hint" } ]
}
```
Drive the repair loop off `summary` (continue while `schema_errors` or
`hard_errors` > 0) and fix each finding at its `json_path` using `hint`.

## Check catalog (semantic — beyond JSON Schema)

JSON Schema covers structure, types, enums, `required`,
`additionalProperties:false`, **value constraints (string `maxLength`/`minLength`,
numeric `minimum`/`maximum`/`exclusive*`, `pattern`)**, and **per-array
uniqueness via the custom `uniqueKeys` keyword** (the validator registers a
handler for it). The semantic layer
adds the cross-field / cross-reference / shape rules JSON Schema cannot express.
**HARD** = blocks the write; **WARN** = reported, still writes.

Uniqueness is **schema-enforced** (`uniqueKeys`, surfaced as schema errors, HARD) on
every array that carries the keyword.

Referential integrity → must resolve to an `input_data` opportunity (HARD):
outcome_dependency independent/dependent; selection_constraints opportunity_name;
selection_dependency dependent/independent; selection_group `members.opportunity_name`;
attribute rows (∈ input, or ∈ input∪master when `is_master_data: true`);
group_limits `group_name` → a defined group.

Outcome-name integrity (HARD): `target_cases[].independent_outcomes` are `"*"` or
real outcomes of the independent opportunity; `outcome_weights[].dependent_outcomes`
are real outcomes of the dependent opportunity. Same independent outcome mapped by
two cases → HARD. Self-dependency → WARN.

Numeric ordering (applies to `opportunity_limits` and `group_limits`) — the
cross-field comparisons the schema can't express: `total_maximum ≥ total_minimum`
and `total_instances_maximum ≥ total_instances_minimum` are HARD. Per-index
`time_period_maxima[i] ≥ time_period_minima[i]` is only WARN, for the reason the
schema gives. (Single-field non-negativity is schema-enforced via `minimum: 0`.) `interior_limit >
total_maximum` → WARN; `integer_only` + `interior_limit` → WARN.

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
> so a file can be schema-valid yet semantically broken: a `selection_dependency`
> naming an opportunity that doesn't exist passes the schema, and the validator
> (correctly) flags it anyway. Generated files must be clean.

## The bundled schema

The schema is **generated** from the QPortfolio server's own type definitions —
never hand-edit it, and never contradict it here. It ships with the skill and is
refreshed whenever the product's file format changes; its `qp_version` records
which product version it came from.
