# Examples — portfolio files

Five annotated few-shots at increasing complexity. All pass
`scripts/validate_portfolio.py` (exit 0). For an exhaustive real-world file see
`server/TestData/Json/portfolio-data.json` (note: its `selection_dependency`
references undefined opportunities, so it is illustrative of *shape*, not of a
clean file).

## 1. Minimal — one certain opportunity

A single certain opportunity with one metric over 3 input periods. No weight
needed for a single outcome; optional fields omitted. The user gave no selection
limits, so `selection_constraints` carries the **default**: each opportunity
capped at `total_maximum: 1` with a single-period selection horizon
`time_period_maxima: [1]`. The selection horizon (1 period) is deliberately
independent of the metric-series length (3) — it is not padded to match, and must
be non-empty or the opportunity would never be selected on import.

```json
{
  "metadata": { "qp_file_type": "QPortfolio Data", "qp_version": 4.5 },
  "input_data": {
    "opportunity_outcomes": [
      {
        "opportunity_name": "Well A",
        "outcomes": [
          {
            "outcome_name": "Base",
            "metric_values": [
              { "metric_name": "Net cash flow", "values": [-10, 50, 60], "unit": "$ MM" }
            ]
          }
        ]
      }
    ]
  },
  "selection_constraints": {
    "opportunity_limits": [
      {
        "opportunity_name": "Well A",
        "total_minimum": 0,
        "total_maximum": 1,
        "time_period_minima": [],
        "time_period_maxima": [1]
      }
    ]
  }
}
```

## 2. Uncertain opportunity + rules

One uncertain opportunity (P90/P50/P10, weights summing to 1), two certain ones,
an **outcome dependency** (when `Exploration X` samples P90, reweight `Dev Y`;
`"*"` covers all other independent outcomes), and **selection constraints**. The
user gave no explicit limits, so every opportunity carries the default cap
(`total_maximum: 1`, single-period selection horizon `time_period_maxima: [1]`) —
even though the input series span 5 periods, the selection horizon stays at one
period. `master_data`,
`attributes`, `selection_dependency`, and `selection_group` are omitted because
nothing in the description calls for them; every referenced name matches
`input_data`.

```json
{
  "metadata": { "qp_file_type": "QPortfolio Data", "qp_version": 4.5 },
  "input_data": {
    "opportunity_outcomes": [
      {
        "opportunity_name": "Exploration X",
        "outcomes": [
          { "outcome_name": "P90", "weight": 0.2, "metric_values": [
            { "metric_name": "Net cash flow", "values": [-50, -10, 20, 30, 30], "unit": "$ MM" } ] },
          { "outcome_name": "P50", "weight": 0.5, "metric_values": [
            { "metric_name": "Net cash flow", "values": [-50, 40, 80, 90, 90], "unit": "$ MM" } ] },
          { "outcome_name": "P10", "weight": 0.3, "metric_values": [
            { "metric_name": "Net cash flow", "values": [-50, 120, 200, 210, 210], "unit": "$ MM" } ] }
        ]
      },
      { "opportunity_name": "Dev Y", "outcomes": [
        { "outcome_name": "Base", "weight": 1, "metric_values": [
          { "metric_name": "Net cash flow", "values": [-30, 25, 40, 40, 40], "unit": "$ MM" } ] } ] },
      { "opportunity_name": "Dev Z", "outcomes": [
        { "outcome_name": "Base", "weight": 1, "metric_values": [
          { "metric_name": "Net cash flow", "values": [-20, 15, 25, 25, 25], "unit": "$ MM" } ] } ] }
    ]
  },
  "outcome_dependency": {
    "dependencies": [
      {
        "independent_opportunity": "Exploration X",
        "dependent_opportunity": "Dev Y",
        "target_cases": [
          { "independent_outcomes": ["P90"], "outcome_weights": [
            { "dependent_outcomes": ["Base"], "weight": 1 } ] },
          { "independent_outcomes": ["*"], "outcome_weights": [
            { "dependent_outcomes": ["Base"], "weight": 1 } ] }
        ]
      }
    ]
  },
  "selection_constraints": {
    "opportunity_limits": [
      {
        "opportunity_name": "Exploration X",
        "total_minimum": 0,
        "total_maximum": 1,
        "time_period_minima": [],
        "time_period_maxima": [1]
      },
      {
        "opportunity_name": "Dev Y",
        "total_minimum": 0,
        "total_maximum": 1,
        "time_period_minima": [],
        "time_period_maxima": [1]
      },
      {
        "opportunity_name": "Dev Z",
        "total_minimum": 0,
        "total_maximum": 1,
        "time_period_minima": [],
        "time_period_maxima": [1]
      }
    ]
  }
}
```

## 3. Master data + attributes + group

Adds a **master-data** set (a default, attribute-free price/FX deck; outcome name
may be empty), **attributes** (declared set + per-opportunity characteristics with
`order`), and a **mutually-inclusive selection group**. Horizon here is 3 periods.

```json
{
  "metadata": { "qp_file_type": "QPortfolio Data", "qp_version": 4.5 },
  "input_data": {
    "opportunity_outcomes": [
      { "opportunity_name": "Field North", "outcomes": [
        { "outcome_name": "Base", "weight": 1, "metric_values": [
          { "metric_name": "Capex-Drilling", "values": [120, 80, 0], "unit": "$ MM" },
          { "metric_name": "Oil production before royalties", "values": [0, 1.5, 1.35], "unit": "MMBOE" } ] } ] },
      { "opportunity_name": "Field South", "outcomes": [
        { "outcome_name": "Base", "weight": 1, "metric_values": [
          { "metric_name": "Capex-Drilling", "values": [90, 60, 0], "unit": "$ MM" },
          { "metric_name": "Oil production before royalties", "values": [0, 1.1, 1.0], "unit": "MMBOE" } ] } ] }
    ]
  },
  "master_data": {
    "opportunity_outcomes": [
      { "opportunity_name": "Default Prices", "outcomes": [
        { "outcome_name": "", "weight": 1, "metric_values": [
          { "metric_name": "Oil Price", "values": [70, 72, 74], "unit": "$/bbl" } ] } ] }
    ]
  },
  "attributes": {
    "attributes": ["Country"],
    "opportunity_attributes": [
      { "opportunity_name": "Field North", "order": 0, "characteristics": [
        { "attribute": "Country", "value": "Canada" } ] },
      { "opportunity_name": "Field South", "order": 1, "characteristics": [
        { "attribute": "Country", "value": "USA" } ] }
    ]
  },
  "selection_group": {
    "groups": [
      {
        "group_name": "North+South",
        "type": "MutualInclusive",
        "members": [
          { "opportunity_name": "Field North" },
          { "opportunity_name": "Field South" }
        ]
      }
    ]
  },
  "selection_constraints": {
    "opportunity_limits": [
      {
        "opportunity_name": "Field North",
        "total_minimum": 0,
        "total_maximum": 1,
        "time_period_minima": [],
        "time_period_maxima": [1]
      },
      {
        "opportunity_name": "Field South",
        "total_minimum": 0,
        "total_maximum": 1,
        "time_period_minima": [],
        "time_period_maxima": [1]
      }
    ]
  }
}
```

## 4. Selection dependency — mind the direction

A **selection dependency** makes one opportunity's selectability depend on
another's. The direction is the easy thing to get wrong, and the validator can
NOT catch a backwards-but-valid rule (both names resolve, so it stays exit 0
while being semantically inverted). Get it right by reading the rule as a
sentence:

> *"To select **X**, **Y** must be selected"* → **X is the `dependent_opportunity`**
> (its selection triggers the rule), **Y is the `independent_opportunity`**.

So "Eastfield Infill should only go ahead if Wildcat Ridge is selected" means
`dependent_opportunity = "Eastfield Infill"`, `independent_opportunity =
"Wildcat Ridge"`, `type = "Must"`. Use `type: "MustNot"` for an exclusive
either/or. `timing`/`timing_offset` are optional — omit them for a plain
across-all-periods relationship (no directional timing). Both names must exist in
`input_data`.

```json
{
  "metadata": { "qp_file_type": "QPortfolio Data", "qp_version": 4.5 },
  "input_data": {
    "opportunity_outcomes": [
      { "opportunity_name": "Wildcat Ridge", "outcomes": [
        { "outcome_name": "Base", "weight": 1, "metric_values": [
          { "metric_name": "Net cash flow", "values": [-120, 60, 90], "unit": "$ MM" } ] } ] },
      { "opportunity_name": "Eastfield Infill", "outcomes": [
        { "outcome_name": "Base", "weight": 1, "metric_values": [
          { "metric_name": "Net cash flow", "values": [-40, 25, 35], "unit": "$ MM" } ] } ] }
    ]
  },
  "selection_dependency": {
    "dependencies": [
      {
        "dependent_opportunity": "Eastfield Infill",
        "independent_opportunity": "Wildcat Ridge",
        "type": "Must",
        "timing": "OverAll",
        "timing_offset": 0
      }
    ]
  },
  "selection_constraints": {
    "opportunity_limits": [
      {
        "opportunity_name": "Wildcat Ridge",
        "total_minimum": 0,
        "total_maximum": 1,
        "time_period_minima": [],
        "time_period_maxima": [1]
      },
      {
        "opportunity_name": "Eastfield Infill",
        "total_minimum": 0,
        "total_maximum": 1,
        "time_period_minima": [],
        "time_period_maxima": [1]
      }
    ]
  }
}
```

## 5. Input periods ≠ planning horizon (knapsack-style)

The trap this guards against: the metric series and the selection-constraint
period arrays are **independent axes** (see REFERENCE.md → "Input periods vs
planning horizon"). Here each item carries a **3-period** input series, but the
decision is a one-off 0/1 "take it or leave it" pick over a **single** selection
period — modelled with `integer_only: true`, `total_maximum: 1`, and a single-period
selection horizon `time_period_maxima: [1]`. Note the deliberate length mismatch:
the input series has length 3, the selection horizon length 1. Do NOT pad the
selection array to length 3 to "match" the series — but also do NOT leave it `[]`,
which would make the item unselectable on import.

```json
{
  "metadata": { "qp_file_type": "QPortfolio Data", "qp_version": 4.5 },
  "input_data": {
    "opportunity_outcomes": [
      { "opportunity_name": "Candy", "outcomes": [
        { "outcome_name": "Base", "metric_values": [
          { "metric_name": "Value", "values": [20, 20, 20], "unit": "$ MM" },
          { "metric_name": "Capex", "values": [10, 10, 10], "unit": "$ MM" } ] } ] },
      { "opportunity_name": "Chocolate", "outcomes": [
        { "outcome_name": "Base", "metric_values": [
          { "metric_name": "Value", "values": [40, 40, 40], "unit": "$ MM" },
          { "metric_name": "Capex", "values": [30, 30, 30], "unit": "$ MM" } ] } ] }
    ]
  },
  "selection_constraints": {
    "opportunity_limits": [
      {
        "opportunity_name": "Candy",
        "integer_only": true,
        "total_minimum": 0,
        "total_maximum": 1,
        "time_period_minima": [],
        "time_period_maxima": [1]
      },
      {
        "opportunity_name": "Chocolate",
        "integer_only": true,
        "total_minimum": 0,
        "total_maximum": 1,
        "time_period_minima": [],
        "time_period_maxima": [1]
      }
    ]
  }
}
```
