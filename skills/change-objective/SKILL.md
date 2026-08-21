---
name: change-objective
description: >-
  Changes what a QPortfolio scenario optimizes for — its objective metric and
  direction — by exporting the scenario, editing the objective, and importing it
  back as a new scenario, then optimizing to compare. Use when a user wants to
  change/swap/switch the objective metric or objective function, optimize for a
  different metric, flip maximize to minimize, ask "what should I optimize for",
  ask which metrics can be an objective, or compare two objectives on the same
  portfolio. Requires the `qpmcp` MCP server; this skill calls it.
---

# Change a scenario's objective

Unlike the `write-*-file` skills, this one **calls the `qpmcp` MCP server**. It never
edits a scenario in place: QPortfolio records the objective when an optimization
runs, so the safe move is to produce a **new scenario** beside the original and
optimize both. The user keeps their baseline and gets a comparison for free.

## Workflow

### 1. Show what the scenario optimizes today

```
list_scenarios(portfolioId)
```

Read `objective_metric_name`, `direction` and `objective_time_period` off the scenario. Say
it back in one line — "S1 maximizes *Discounted Cash Flow ($ MM) @13% - With
Expression*, objective value 9,967.67" — so the user knows the starting point.

### 2. Offer the objective choices

```
list_metrics(portfolioId)
```

The tool returns every metric in the model — minus interim sub-metrics, which it excludes
for you — in the QPortfolio Model JSON file's own field names. Do not show the user all of
them: a real portfolio has dozens, and most make no sense as an objective.

**Present only metrics where `scalar: true` and `report_only: false`.** That is usually a handful out of dozens. Reasons, in order
of how much they matter:

- **`scalar: true`** — a scalar metric is a single value, so it needs no
  `objective_time_period`. A metric with `scalar: false` is a per-period time
  series and the document *must* also say which period to optimize to. One less
  thing to get wrong, and it is what a user asking "maximize NPV" almost always
  means.
- **`report_only: true`** — flagged for reporting, not optimization.

Show `metric_name`, `unit` and `description` when present, and mark which one is
the current objective.

**If the user wants something not in that shortlist**, or the shortlist is empty
(a model may have no scalar metrics at all), widen to just `report_only: false`
and say plainly that these are per-period metrics, so you also
need a period — ask which one, or default to the scenario's existing
`objective_time_period`.

Never invent or abbreviate a metric name. They are long and contain punctuation
(`Discounted Cash Flow ($ MM)- With Sum`); copy `metric_name` **exactly** as the
tool returned it, or the import fails with `ObjectiveMetricUnknown`.

### 3. Build the new scenario

```
export_scenario(portfolioId, scenarioId)      -> { folder, files: [{ name }] }
GET /download/{folder}/{name}                 -> the scenario document, on your disk
```

Edit two or three fields, and nothing else:

```json
"settings":     { "scenario_name": "S1 — max DCF (Sum)" },
"optimization": { "objective_metric_name": "Discounted Cash Flow ($ MM)- With Sum",
                  "direction": "Maximize" }
```

- **Rename it.** `settings.scenario_name` decides the new scenario's name; leave it
  alone and you get "S1 (1)", which tells the user nothing. Name it after the change.
- `direction` is `"Maximize"` or `"Minimize"` — carry the original over unless the
  user asked to flip it.
- Set `optimization.objective_time_period` **only** for a non-scalar metric.

```
POST /upload  (the edited file)   -> { folder }
import_scenario(portfolioId, folder)  -> the NEW scenario id
```

### 4. Optimize and compare

```
run_optimization(portfolioId, newScenarioId)
get_job_status(portfolioId, jobId)     # poll to a terminal state
get_selections(portfolioId, newScenarioId)
```

Report both scenarios side by side: objective metric, direction, solution status,
objective value, and how the selections differ. A different objective usually picks
a different set — that difference is the answer the user came for.

## Rules

- **Check the status before trusting numbers.** Only a solved `solver_status`
  (e.g. `Optimal`) means the selections are real. Say so if it is not.
- **Never modify the original scenario.** If the user truly wants the baseline
  changed rather than compared, tell them that means optimizing the original with
  the new objective, and that it overwrites their existing result — then ask.
- **One import per portfolio at a time.** `import_scenario` is synchronous, but if a
  model/data import job is alive the import refuses; poll `get_job_status` first.
- Permissions follow the user's API key: Read to list, Write to import and optimize.
  A denial is a real answer — relay it rather than retrying.
