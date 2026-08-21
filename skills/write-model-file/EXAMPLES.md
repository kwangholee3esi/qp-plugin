# Examples — QPortfolio model files

Annotated few-shot files for the `write-model-file` skill. Each validates
clean with `scripts/validate_model.py`. Field meanings: the schema +
[REFERENCE.md](REFERENCE.md).

## 1. Minimal — one input, one computed metric

*"Track Capex per opportunity and give me its total."*

```json
{
  "metadata": {
    "qp_file_type": "QPortfolio Model",
    "qp_version": 4.5
  },
  "metrics": [
    {
      "metric_name": "Capex",
      "unit": "$ MM"
    },
    {
      "metric_name": "Capex Total",
      "metric_type": "Computed",
      "level": "Outcome",
      "unit": "$ MM",
      "expressions": [
        { "formula": "Total(${Capex})" }
      ]
    }
  ]
}
```

Why this shape: `Capex` omits `metric_type` (`Input` is the default). The
computed metric states its `level` explicitly — always do that. No attributes
are needed, so the `attributes` section is omitted entirely (not `[]`).
Idiomatically this total should be `"derived": ["Total"]` on `Capex` itself
(see examples 4 and 6) — `Capex` is a linear, Interest-scaled input, exactly
when derived metrics are preferred. Write an explicit expression like this only
when the origin is non-linear or Instance-scaled, or when the user wants a
metric of their own naming (here, `Capex Total` as a named metric).

## 2. Recurrence — an opening balance that declines

*"Reserves start at 1000 MMbbl and decline by each period's production."*

```json
{
  "metadata": {
    "qp_file_type": "QPortfolio Model",
    "qp_version": 4.5
  },
  "metrics": [
    {
      "metric_name": "Oil Rate",
      "unit": "bbl/d"
    },
    {
      "metric_name": "Reserves",
      "metric_type": "Computed",
      "level": "Outcome",
      "unit": "MMbbl",
      "expressions": [
        {
          "formula": "${Reserves} - ${Oil Rate}",
          "first_period_formula": "1000"
        }
      ]
    }
  ]
}
```

Why this shape: a metric referencing **itself** is the recurrence idiom — at
each period the formula sees the metric's previous value. `first_period_formula`
seeds period 0 only; omit it when the first period uses the same formula (never
write `""`).

## 3. Filtering by exception — a country-specific royalty

*"Revenue is rate × price, but USA opportunities take a 10% royalty haircut —
except in the Fail outcome, where revenue is zero."*

```json
{
  "metadata": {
    "qp_file_type": "QPortfolio Model",
    "qp_version": 4.5
  },
  "metrics": [
    { "metric_name": "Oil Rate", "unit": "bbl/d" },
    { "metric_name": "Oil Price", "metric_type": "MasterData", "unit": "$/bbl" },
    {
      "metric_name": "Revenue",
      "metric_type": "Computed",
      "level": "Outcome",
      "unit": "$ MM",
      "expressions": [
        {
          "order": 0,
          "formula": "${Oil Rate} * ${Oil Price} / 1000"
        },
        {
          "order": 1,
          "formula": "${Oil Rate} * ${Oil Price} * 0.9 / 1000",
          "criteria": [
            { "attribute": "Country", "characteristic": ["USA"] }
          ]
        },
        {
          "order": 2,
          "formula": "0",
          "criteria": [
            { "outcome": ["Fail"] }
          ]
        }
      ]
    }
  ],
  "attributes": [
    {
      "attribute_name": "Country",
      "data_type": "String",
      "characteristics": [
        { "characteristic_name": "Canada" },
        { "characteristic_name": "USA" }
      ]
    }
  ]
}
```

Why this shape: expressions apply in `order` — the unfiltered `order: 0`
expression is the default; higher orders are exceptions where their `criteria`
match. Multiple criteria on ONE expression would combine as OR, so mutually
distinct cases go on separate expressions. `Oil Price` is master data: one
price deck matched to opportunities via attributes, referenced like any other
metric. The `Country` attribute used by the criterion is declared in the same
file. Outcome filters like `["Fail"]` belong on Outcome-level metrics.

## 4. Group level + derived metrics

*"Cashflow per country (ring-fenced), and give Revenue running-cumulative and
discounted variants."*

```json
{
  "metadata": {
    "qp_file_type": "QPortfolio Model",
    "qp_version": 4.5
  },
  "metrics": [
    { "metric_name": "Oil Rate", "unit": "bbl/d" },
    { "metric_name": "Oil Price", "metric_type": "MasterData", "unit": "$/bbl" },
    {
      "metric_name": "Revenue",
      "metric_type": "Computed",
      "level": "Outcome",
      "unit": "$ MM",
      "derived": ["CumSum", "Disc"],
      "expressions": [
        { "formula": "${Oil Rate} * ${Oil Price} / 1000" }
      ]
    },
    {
      "metric_name": "Payback Flag",
      "metric_type": "Computed",
      "level": "Outcome",
      "expressions": [
        { "formula": "If(${Revenue#CumSum} > 500, 1, 0)" }
      ]
    },
    {
      "metric_name": "Country Cashflow",
      "metric_type": "Computed",
      "level": "Group",
      "group_by": ["Country"],
      "unit": "$ MM",
      "expressions": [
        { "formula": "${Revenue} - ${Oil Rate} * 0.02" }
      ]
    }
  ]
}
```

Why this shape: `derived` lists transforms on the **origin** metric — each
becomes `Revenue#CumSum` / `Revenue#Disc`, inheriting everything from Revenue
(never declare one as its own metric entry; those names are reserved). Derived
is the right choice here because `Revenue` is **linear** (its only product is
with the master-data `Oil Price`) and **Interest-scaled** — the validator warns
when `derived` sits on a non-linear or Instance-scaled origin. A formula may
reference `${Revenue#CumSum}` — that reference alone would even auto-create the
derivation, as long as `Revenue` is defined in this file. The Group-level
metric must carry `group_by`; this file omits `attributes`, so the `Country`
attribute is expected from the model or a sibling attributes file.

## 5. Attributes-only file

*"Define the Project Type attribute with ordered, coloured characteristics —
don't touch the metrics."*

```json
{
  "metadata": {
    "qp_file_type": "QPortfolio Model",
    "qp_version": 4.5
  },
  "attributes": [
    {
      "attribute_name": "Project Type",
      "data_type": "String",
      "editable": true,
      "characteristics": [
        { "characteristic_name": "Exploration", "sort_order": 1, "color": "#1F77B4" },
        { "characteristic_name": "Development", "sort_order": 2, "color": "#FF7F0E" },
        { "characteristic_name": "Abandonment", "sort_order": 3, "color": "#7F7F7F" }
      ]
    },
    {
      "attribute_name": "Price Set",
      "data_type": "String",
      "scenario_level": true,
      "characteristics": [
        { "characteristic_name": "High" },
        { "characteristic_name": "Low" }
      ]
    }
  ]
}
```

Why this shape: `metrics` is **omitted**, so the model's metrics are untouched
— never write `"metrics": []` here (an empty list deletes every computed
metric). Characteristics are add/update-only on re-import: ones not listed are
kept. `sort_order` and `color` drive dashboard chart rendering.
`scenario_level: true` marks Price Set as selectable per scenario (sensitivity
analysis); `editable: true` lets users edit Project Type on the Opportunities
page.

## 6. Knapsack-style (non-O&G) — the model half of a pick-the-best-items portfolio

*"Each item has a value and a one-time cost; pick the best combination under a
budget."* This is the **companion model** to the `write-portfolio-file`
skill's example 5 (same metric names and units — the pair is joined by name).

```json
{
  "metadata": {
    "qp_file_type": "QPortfolio Model",
    "qp_version": 4.5
  },
  "metrics": [
    {
      "metric_name": "Value",
      "unit": "$ MM",
      "derived": ["Total"]
    },
    {
      "metric_name": "Capex",
      "unit": "$ MM",
      "derived": ["Total"]
    }
  ]
}
```

Why this shape: the whole model is two input metrics plus `derived: ["Total"]`
— no computed metrics at all. Both origins are linear, Interest-scaled inputs,
which is exactly when derived metrics are preferred over explicit
`Total(${...})` expressions; a scenario then maximizes `Value#Total` with a
metric limit on `Capex#Total`. **Data-shape contract:** `Total` sums every
period, so a one-time cost must arrive as a zero-padded series (`[10, 0, 0]`) —
a flat `[10, 10, 10]` series would silently make the item cost 30, not 10.
Nothing validates that the model and data file agree — keep the metric names,
units, and this data shape in sync by hand (see portfolio example 5 for the
matching data file).
