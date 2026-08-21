# Reference — generating a QPortfolio model file

Deep guidance for the `write-model-file` skill. The authoritative structure
is always the schema itself (`schemas/model.schema.json`, or the in-repo
`server/Esi.Sp.Portable/Schemas/model.schema.json`), which carries a
description and `examples` for every field. This file adds domain meaning and
the rules the schema can't express.

## What a model is (grounded in the QP vault)

A **model** is the definitional layer of a portfolio: its **metrics** and its
**attribute definitions**. A portfolio has exactly **one** model, and the model
is **not versioned** — importing a model file updates the recipe in place
(`wiki/concepts/portfolio-model.md`). Per-opportunity metric *values* and
per-opportunity characteristic *values* live in the portfolio **data** file;
the two are joined **by name**, so names here must match the data file exactly
(`wiki/expressions/expressions-json.md`).

- **Metrics** come in three kinds (`wiki/concepts/metric.md`): **Input**
  (values imported per opportunity — the default), **MasterData** (one value
  set applying across opportunities, matched via attributes: price decks, FX,
  inflation), and **Computed** (calculated from other metrics by expressions).
- **Expressions** compute a metric per time period from other metrics
  (`wiki/concepts/expression.md`). `formula` runs at every period;
  `first_period_formula` seeds only period 0 (an opening balance). A metric's
  formula may reference **itself** — that is the recurrence idiom, e.g.
  Reserves = `${Reserves} - ${Oil Rate}` with `first_period_formula: "1000"`
  (`wiki/expressions/expressions-sheet-basics.md`).
- **Calculation level** (`wiki/expressions/expression-calculation-level.md`):
  **Outcome** — per opportunity-outcome pair; any filter applies. **Opportunity**
  — from each opportunity's expected values; usually matches Outcome with
  faster runs; every filter except by-outcome. **Group** — per attribute-defined
  group (`group_by`) for ring-fenced calculations. **Scenario** — once for the
  whole scenario (e.g. a graduated tax); cannot be filtered.
- **Filtering by exception** (`wiki/expressions/filtering-expressions.md`): a
  metric's expressions apply in `order` (lower first); the lowest is the
  default, higher orders are exceptions restricted by `criteria`. Within one
  expression, multiple criteria combine as **OR**; each condition accepts
  several values and can be negated with its `except_*` flag. Time periods are
  **0-based**.
- **Derived metrics** (`wiki/concepts/derived-metric.md`): auto-created
  transforms of an origin metric, declared by listing types in the origin's
  `derived` array — never as their own metric entry. Each becomes
  `<origin>#<Type>` (e.g. `Revenue#CumSum`) and inherits everything from the
  origin. `Total`/`TotalDisc`/`TotalInf`/`MaxAT` are scalars; the other six
  follow the origin's shape. Discounting/inflation use the portfolio's rates.
  **Use a derived metric whenever the origin is linear and scaled by Interest**
  (the default `scale_by`); write an explicit computed metric only when the
  origin is non-linear or Instance-scaled — there the derived transform and the
  hand-written `Total(...)`/`Disc(...)` can legitimately differ — or when the
  user explicitly wants a metric of their own naming. Operationally:
  Input/MasterData origins are always linear; a Computed origin is linear when
  its formulas use only `+`/`-` and multiplication/division by constants or
  **master-data** metrics. Non-linear signals: `^`, `If`/`Min`/`Max`/`Abs`,
  `GetIRR`/`GetMaxAcrossTime`/`MaxAT`, or a product/quotient of two
  non-master-data metrics
  (`wiki/expressions/expressions-master-data.md`, `wiki/concepts/optimization.md`).
- **Attributes** (`wiki/concepts/attribute.md`): grouping categories (Country,
  Project Type) whose **characteristics** are the values. Used for grouping
  (`group_by`), expression filtering (`criteria`), master-data matching, and
  dashboards (characteristic `sort_order` + `color` drive chart rendering). An
  attribute used by **no** opportunity becomes a scenario attribute (offered as
  a per-scenario dropdown) — `scenario_level: true`
  (`wiki/portfolio-modeling/portfolio-modeling-attributes.md`).

## Re-import semantics (the traps)

These rules matter only when **updating an existing model** — for a brand-new
model there is nothing to clear, so omit optional properties freely (don't pad
every metric with defensive descriptions). The importer treats the file as
authoritative for what it carries — with three different merge behaviours
(`wiki/expressions/expressions-json.md`):

- **A metric definition is complete.** An omitted optional property (`unit`,
  `color`, `format`, `category`, `description`) **CLEARS** the stored value on
  re-import. State every property the user wants kept.
- **`metrics` and `attributes` are independent sections.** Omit a section to
  leave that part of the model untouched (a metrics-only or attributes-only
  file is normal — a model may even be split across two files imported
  together, each section carried by at most one of them).
- **`"metrics": []` is NOT the same as omitting `metrics`** — an empty list
  names no metrics, so **every computed metric of the model is deleted** as
  obsolete. `"attributes": []` is harmless (attributes are never deleted by an
  import).
- An attribute's `characteristics` list is **add/update-only** — an omitted
  characteristic is kept, not removed (deletion is a UI operation).
- The `derived` list is **additive**: listed types merge with existing derived
  metrics; a type no longer listed keeps its metric (remove it on the Model
  page; it is deleted with its origin).
- A metric's type **cannot flip** between input and computed on re-import, and
  a metric already imported **visible cannot become hidden** — both rejected.

## Authoring conventions

- `metadata.qp_file_type` must be exactly `"QPortfolio Model"`. Include
  `qp_version` for traceability — use the value recorded in the skill's
  `.schema-sync.json` (currently `4.5`) unless the user states their product
  version.
- snake_case keys; enums as strings: `metric_type`
  `Input`/`MasterData`/`Computed`; `level`
  `Outcome`/`Scenario`/`Group`/`Opportunity`; `scale_by` `Interest`/`Instance`;
  `data_type` `String`/`Numeric`/`Date`; `derived` types
  `PT`/`Disc`/`Inf`/`CumSum`/`CumSumDisc`/`CumSumInf`/`Total`/`TotalDisc`/`TotalInf`/`MaxAT`.
- Omit optional fields rather than writing `null`. Never emit `NaN`/`Infinity`.
- **Always state `level` explicitly on every computed metric** — do not rely on
  a default. Filters belong on Outcome/Group-level metrics: Scenario level
  cannot be filtered, and Opportunity level takes every filter except
  by-outcome.
- `group_by` only with `level: "Group"` (a Group metric must have it; multiple
  attributes give multi-level grouping).
- Names: no `{` or `}` (they delimit `${...}` references); names ending
  `#<Type>` for a derivation type are **reserved** for derived metrics; metric
  names are unique **case-insensitively**; attribute names avoid `\` and `/`.
- Give each of a metric's expressions a distinct `order` (lower evaluates
  first); the default/unfiltered expression takes the lowest order.
- Omit `first_period_formula` when the first period uses the same formula —
  never write an empty string.
- **One-time amounts (capex-like).** Both shapes are safe under totals: a
  `scalar: true` metric holds one value and `Total()`/`GetCumulative` of it
  returns that value; a zero-padded series `[w, 0, 0]` totals to the same `w`.
  What silently breaks is a **flat series** `[w, w, w]` — it totals to `3w`.
  Choose `scalar` for a genuinely time-less value that multiplies other metrics
  the same way in every period (a rate, an interest, a flag — a scalar acts as
  a per-period constant); choose the zero-padded series when the amount belongs
  to a specific period (spend at decision time) or must show up in per-period
  reporting and metric limits.

### Field limits & schema-enforced constraints

The synced schema enforces these directly (a violation is a hard schema error),
so author within them:

- **String max lengths** (names must be non-empty): `metric_name`,
  `attribute_name`, `characteristic_name`, criterion `attribute` ≤ 450;
  `category` ≤ 255; `format` ≤ 256; `description` ≤ 1000; `unit` ≤ 128.
- **No braces** in `metric_name` / `attribute_name` / criterion `attribute`
  (`pattern ^[^{}]+$`).
- **`color`** must match the hex `pattern` `#RRGGBB` (e.g. `"#1F77B4"`), ≤ 32.
- **Numeric ranges**: `expressions[].order` ≥ 0; criterion `period` values ≥ 0.
- **Non-empty arrays** (`minItems: 1`): `group_by` and every criterion value
  list (`characteristic`, `opportunity`, `outcome`, `period`) — a present-but-
  empty list matches nothing and is rejected.
- **Uniqueness** (`uniqueKeys`): `metrics` by `metric_name`, `attributes` by
  `attribute_name`, each attribute's `characteristics` by
  `characteristic_name`. (These are case-sensitive; the case-insensitive
  duplicate check is in the semantic layer.)

## Expression language quick reference

Formulas are Excel-style (`wiki/expressions/expression-functions.md`). Only
**references** are wrapped in `${...}`; functions, operators and numeric
constants are written bare. Attribute values are reachable only through
`GetAttributeValue(${Attr})`. Derived metrics are referenced by their generated
name: `${Revenue#CumSum}` (this also auto-creates the derived metric, provided
the origin is defined in the same file). Every `${...}` metric reference must
name a metric **defined in this file** — never one that exists only in the
target model.

The function set is **closed — exactly these 26 names** (case-insensitive), no
others (no `ROUND`, `AND`, `OR`, `EXP`, `SQRT`, `POWER`, …):

| Function | Arguments |
|---|---|
| `PT` `Disc` `Inf` `CumSum` `CumSumDisc` `CumSumInf` `Total` `TotalDisc` `TotalInf` `MaxAT` | exactly 1 metric ref (the p4 shorthands; prefer `derived` instead) |
| `GetMetricValue` `GetDiscounted` `GetInflated` | metric ref [, period] |
| `GetCumulative` `GetCumulativeInflated` `GetMaxAcrossTime` `GetIRR` | metric ref [, first [, last]] |
| `GetCumulativeDiscounted` | [rate,] metric ref [, first [, last]] |
| `GetCurrentTime` | none |
| `GetAttributeValue` | exactly 1 attribute ref |
| `Sum` | 1..n |
| `Abs` | exactly 1 |
| `Min` / `Max` | exactly 2 |
| `If` | exactly 3 (condition, then, else) |
| `NPV` | rate (non-negative constant), then 1..n values |

- Operators: `+ - * / ^` (power — there is no `POWER` function), comparisons
  `= <> < > <= >=` as `If` conditions, parentheses, `,` between arguments.
- Literals: numbers (scientific notation needs a **signed** exponent: `1e+5`,
  never `1e5`), double-quoted strings (for `GetAttributeValue` comparisons and
  outcome names), `TRUE`/`FALSE`.
- Time indices are 0-based; `-1` means the last period. Optional arguments are
  positional.
- **Macros are rejected in JSON** model files: `FlagUpToMax` is Excel-import
  only — break it into explicit metrics/expressions instead.
- `&` and `%` parse but are **silently discarded** by the calculator — never
  use them.
- `GetIRR` imports and calculates, but **any optimization of a scenario using
  it fails** — avoid it in metrics optimization will touch.
- Keep expressions linear where possible for the solver; multiplying/dividing
  by a **master-data** metric introduces no non-linearity
  (`wiki/expressions/expressions-master-data.md`).
- `unit` is a label only — QPortfolio verifies unit consistency against the
  input data but never converts units (`wiki/expressions/units.md`).

## Ask vs default

**Ask the user** (blocks a meaningful file):
- A metric is clearly computed but you cannot infer its formula.
- A formula references a metric/attribute the description never defines — ask
  whether to add the definition or fix the name (never invent).
- The user wants to reduce or clear existing model content (that needs the
  re-import semantics above spelled out — confirm intent before emitting an
  empty `metrics` list or a stripped-down metric definition).
- A domain term you can't resolve from this file or the vault.

**Default silently** (note assumptions in your summary):
- `metric_type` → omit for inputs (`Input` is the default); state it for
  `MasterData`/`Computed`.
- `level` → `"Outcome"` for per-opportunity calculations unless the user
  describes a scenario-wide or per-group calculation — but always **emit** it.
- `scalar`, `hidden`, `scale_by`, `format`, `color` → omit unless the user
  gives them (new metrics get a random colour).
- Totals/cumulatives/discounted variants of a linear, Interest-scaled metric →
  `derived` on the origin (reference them as `${Name#Type}`), not explicit
  computed metrics — unless the user asks for their own metric name.
- No attributes described → omit `attributes` entirely (never `[]`… though for
  attributes `[]` is merely pointless, not destructive).
- `sort_order`/characteristic `color` → omit unless the user cares about chart
  ordering/colours.

## Validator CLI

```
python scripts/validate_model.py <file.json> [--schema PATH] [--format json|text] [--strict-nulls]
```

Exit codes: `0` valid (warnings allowed) · `1` invalid (schema and/or hard
errors) · `2` IO/parse error (missing file, bad JSON, or NaN/Infinity) · `3`
environment error (`jsonschema` not installed, or no schema found).

**PowerShell fallback (no Python).** When Python is unavailable, the bundled
`scripts/validate_model.ps1` (Windows PowerShell 5.1+, no modules) is a drop-in
replacement — same flags, same exit codes, identical JSON output and schema
discovery:

```
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/validate_model.ps1 <file.json> [--schema PATH] [--format json|text] [--strict-nulls]
```

It has no `jsonschema` dependency, so its exit `3` means only "no schema found".
The Python validator stays the source of truth; `tests/conformance_ps.py`
asserts the two agree on every fixture.

JSON output:
```jsonc
{
  "ok": false,
  "schema_path_used": "…/model.schema.json",
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
`additionalProperties:false`, value constraints (lengths, patterns, `minItems`,
ranges), and per-array uniqueness via the custom `uniqueKeys` keyword. The
semantic layer adds the naming, cross-metric, and expression rules JSON Schema
cannot express. **HARD** = blocks the write; **WARN** = reported, still writes.

Metadata (HARD): `metadata.qp_file_type` exactly `"QPortfolio Model"`.
`qp_version` not numeric → WARN.

Naming (HARD): a name that is whitespace-only after normalization; a metric
name duplicated **case-insensitively** (`uniqueKeys` is case-sensitive, the
importer is not); a metric named `<origin>#<Type>` for a known derivation type
(reserved — a bare `#` is fine).

Metric shape: expressions on a non-`Computed` metric → HARD; a `Computed`
metric with no expressions → HARD; `level: "Group"` without `group_by` → HARD;
`group_by` on a non-Group level → WARN; a `Computed` metric with no explicit
`level` → WARN (state it); `"metrics": []` → WARN (deletes every computed
metric on import).

Derived-metric guidance (WARN): `derived` on an Instance-scaled metric, and
`derived` on a Computed origin whose expressions look non-linear (`^`,
`If`/`Min`/`Max`/`Abs`, `GetIRR`/`GetMaxAcrossTime`/`MaxAT`, or a product of
two non-master-data metrics) — in both cases the derived value may differ from
the equivalent explicit expression, so prefer an explicit computed metric there.

Criteria: criteria on a `Scenario`-level metric → WARN (scenario-level
expressions cannot be filtered — the importer accepts the file, the filter
won't behave); an `outcome` criterion on an `Opportunity`-level metric → WARN;
a criterion `attribute` (or a `GetAttributeValue` reference) not declared in
this file's `attributes` → WARN (the importer silently creates it — usually a
typo). These attribute warnings only fire when the file carries an
`attributes` section; a metrics-only file may legitimately lean on the sibling
file's definitions. Duplicate `order` within one metric's expressions → WARN.

Formulas (both `formula` and `first_period_formula`; the tokenizer mirrors the
import-time parse): unbalanced parentheses / unterminated string / unclosed
`${` → HARD; a `${ref}` that doesn't match a metric defined in this file →
HARD; a `${origin#Type}` whose origin isn't defined in this file → HARD; a
function name outside the closed 26-name set → HARD; wrong argument count →
HARD; the `FlagUpToMax` macro → HARD; a bare identifier (a metric name missing
its `${...}`) → HARD. `&`/`%` present → WARN (silently discarded); an unsigned
exponent (`1e5`) → WARN; `GetIRR` used → WARN (breaks optimization).

Other: NaN/Infinity literals are rejected at parse time (exit 2). Explicit
`null` for optional fields → WARN only under `--strict-nulls`.

> Note: the validator checks the file **self-contained**, exactly like the
> importer resolves references (a formula may only use metrics this file
> defines). What it cannot see is the join with the portfolio data file —
> whether the metric/attribute names match the data — so get names from the
> user's actual portfolio wherever possible.

## Maintaining the bundled schema

The schema is **generated** from `server/Esi.Sp.Portable/Types/*.cs` and their
`[Description]` attributes — never hand-edit it (server copy or bundled). When
the C# types change:

1. Regenerate the server schema (see `server/Esi.Sp.Portable/Schemas/README.md`):
   ```
   UPDATE_PORTABLE_SCHEMAS=1 dotnet test Esi.Sp.Portable.Tests --filter Committed_schema_matches_generator_output
   ```
2. Refresh the bundled copy + provenance:
   ```
   python scripts/sync_schema.py
   ```

`.schema-sync.json` records the source path, sha256, and `qp_version`. When the
validator runs inside the repo it prefers the live server schema and warns if
the bundled copy has drifted. The 26-function/arity table in both validators
mirrors `server/Esi.Sp.Parsing/Converter/FunctionDef.cs` — revisit it when that
file changes.
