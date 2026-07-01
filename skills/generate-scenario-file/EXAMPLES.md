# Examples — scenario files

Four annotated few-shots at increasing complexity. All pass
`scripts/validate_scenario.py` (exit 0). For an exhaustive real-world file see
`server/TestData/Json/scenario-1.json`, which exercises every section.

Remember: a scenario references names defined in its **portfolio**. The examples
use placeholder opportunity/metric names; when you have a companion portfolio, use
its real names and validate with `--portfolio`.

## 1. Minimal — objective only

The leanest meaningful scenario: a name and an optimization objective. Direction
defaults to `"Maximize"`. No metric limits, no rule overrides (so the portfolio's
selection rules are inherited), no pinned selections.

```json
{
  "metadata": { "qp_file_type": "QPortfolio Scenario Data", "qp_version": 4.5 },
  "settings": { "scenario_name": "Maximize NPV" },
  "optimization": {
    "direction": "Maximize",
    "objective_metric_name": "NPV ($ MM)"
  }
}
```

## 2. Objective + metric limit

Maximize NPV subject to a capex ceiling. The capex limit is a per-period
**Maximum** metric limit; periods not listed are unconstrained. `objective_time_period`
optimizes the objective up to a given period (omit for a scalar objective).

```json
{
  "metadata": { "qp_file_type": "QPortfolio Scenario Data", "qp_version": 4.5 },
  "settings": { "scenario_name": "Capex-capped plan", "description": "NPV max with $50MM/yr capex cap" },
  "optimization": {
    "direction": "Maximize",
    "objective_metric_name": "NPV ($ MM)",
    "objective_time_period": 10
  },
  "metric_limits": [
    {
      "metric_name": "Capex-Drilling",
      "limit_type": "Maximum",
      "unit": "$ MM",
      "targets": [
        { "period": 0, "value": 50 },
        { "period": 1, "value": 50 },
        { "period": 2, "value": 50 }
      ]
    }
  ]
}
```

## 3. Rule overrides — full section, not a delta

Override the scenario's selection rules. Because a present rule section **replaces**
the portfolio's whole section (it is not merged), emit the **complete** set you want
for that section. Here both opportunities get an explicit limit, one opportunity
depends on another, and a mutually-inclusive group ties two together. Read a
dependency as a sentence: *"to select the dependent, the independent must be
selected"*.

```json
{
  "metadata": { "qp_file_type": "QPortfolio Scenario Data", "qp_version": 4.5 },
  "settings": { "scenario_name": "Tied development" },
  "optimization": {
    "direction": "Maximize",
    "objective_metric_name": "NPV ($ MM)"
  },
  "selection_constraints": {
    "opportunity_limits": [
      {
        "opportunity_name": "Wildcat Ridge",
        "integer_only": true,
        "total_minimum": 0,
        "total_maximum": 1,
        "time_period_minima": [],
        "time_period_maxima": [1]
      },
      {
        "opportunity_name": "Eastfield Infill",
        "integer_only": true,
        "total_minimum": 0,
        "total_maximum": 1,
        "time_period_minima": [],
        "time_period_maxima": [1]
      }
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
  "selection_group": {
    "groups": [
      {
        "group_name": "Ridge cluster",
        "type": "MutualInclusive",
        "members": [
          { "opportunity_name": "Wildcat Ridge" },
          { "opportunity_name": "Eastfield Infill" }
        ]
      }
    ]
  }
}
```

## 4. Pinned selections + soft limit + characteristics

A manually pinned case: specific opportunities selected in specific periods, a
**soft** metric limit (allowed to be violated for a penalty — note
`settings.enable_soft_constraints: true`), and a scenario **characteristic** (a
price set) driving sensitivity without changing opportunity inputs. Pin selections
only when the user explicitly wants them; otherwise leave the solver to fill them.

```json
{
  "metadata": { "qp_file_type": "QPortfolio Scenario Data", "qp_version": 4.5 },
  "settings": {
    "scenario_name": "Manual CDN-price case",
    "enable_soft_constraints": true,
    "characteristics": [ { "attribute": "MD_Pricing", "value": "CDN" } ]
  },
  "optimization": {
    "direction": "Maximize",
    "objective_metric_name": "NPV ($ MM)",
    "penalty_weight": 1
  },
  "metric_limits": [
    {
      "metric_name": "Capex-Drilling",
      "limit_type": "Maximum",
      "unit": "$ MM",
      "soft": true,
      "magnitude": 10,
      "penalty_weight": 5,
      "targets": [ { "period": 0, "value": 50 } ]
    }
  ],
  "opportunity_selections": [
    {
      "opportunity_name": "Wildcat Ridge",
      "selections": [ { "period": 0, "value": 1 } ]
    },
    {
      "opportunity_name": "Eastfield Infill",
      "selections": []
    }
  ]
}
```
