# Golden prompts

Each prompt below is the plain-language request a user would give the skill to
produce the matching golden fixture. The fixtures are **kitchen-sink** files: they
deliberately populate *every* optional field and *every* enum value so that, taken
together, they cover the whole schema (see `run_coverage_tests.py`). A real user
request would be smaller; these are exhaustive on purpose.

Generating a fixture from its prompt is the **interactive** test surface — run it by
hand in a fresh session and compare the output to the golden file. It is
non-deterministic (LLM-driven) and is **not** executed by `run_coverage_tests.py`,
which only validates the committed golden JSON and asserts coverage.

---

## `portfolio/portfolio_full_coverage.json`

Invoke `/generate-portfolio-file` with:

> Build me a portfolio (qp_version 4.5) with five opportunities over a 3-period horizon.
>
> - **Well A** is certain (single "Base" case). Metrics: Capex `[120.5, 98.2, 0]` $ MM, Oil
>   Rate `[0, 1500, 1350]` bbl/d, and a scalar Discount Rate of 0.1 (fraction).
> - **Well B** is uncertain — P90/P50/P10 weighted 0.2/0.6/0.2 — with Capex and Oil Rate
>   series per case.
> - **Well C** and **Well E** are certain with a Capex series.
> - **Well D** is uncertain P90/P50/P10 (weights 0.3/0.4/0.3) with Capex.
>
> Add master data: a default price deck "Default Prices" (Oil Price series + a scalar FX of
> 1.3 CAD/USD), and an attribute-qualified "Canada Prices" deck (High/Low cases, weighted 0.5
> each).
>
> Define attributes Country and Project Type. Order the opportunities A–E (0–4) then Canada
> Prices (5). Well A is Country=Canada, Project Type=Exploration with offset 0; Well B is
> Country=Norway with offset 1; Canada Prices is a master-data row with Country=Canada.
>
> Add an outcome dependency: when Well B samples P90, reweight Well D to 0.5/0.3/0.2; for all
> other Well B outcomes ("\*"), reweight Well D's P90+P50 to 0.4 and P10 to 0.2.
>
> Selection constraints: Well A — fractional selection, total max 1, min-fraction 0.1, up to 2
> instances, per-period maxima `[1,1]`; Well B — integer-only, total max 2, per-period maxima
> `[1,1,1]`.
>
> Selection dependencies (to select the dependent, the independent must/must-not be selected):
> Well C needs Well A (Must, OverAll); Well C must-not coincide with Well E (MustNot, Before,
> offset −1, disabled); Well E needs Well A (Must, After, offset +1); Well E needs Well C
> (Must, During).
>
> Selection groups: a mutually-inclusive "Group Inclusive" of Well A and Well B (Well B's
> membership disabled), and a mutually-exclusive "Group Exclusive" of Well C and Well D, each
> with group limits.

Expected: validates clean (exit 0, 0 hard errors).

---

## `scenario/scenario_full_coverage.json`

Invoke `/generate-scenario-file` (companion portfolio = the file above) with:

> Create a scenario "Full Coverage Case" (qp_version 4.5), colour #C25A38, on data version V1,
> instance-selection threshold 0.001, soft constraints enabled, scenario characteristic
> Country=Canada.
>
> Optimize to **maximize** "NPV ($ MM)" up to period 10. Tune the solver fully: feasibility
> tolerance 1e-7, optimality tolerance 1e-4, absolute gap 0.5, percentage gap 1.0, penalty
> weight 100, progress interval 5, timeout 5 minutes (don't force timeout), load current
> selections, linearize (SolverDecide), use 5 local solvers, no quadratic XOR, non-strict
> threshold, and one expert Lindo parameter id 1 = 0 plus id 42 = 1.5.
>
> Metric limits: Capex **Maximum** $ MM with targets period 0 ≤ 1000 and period 1 ≤ 2000, made
> a **soft** limit (magnitude 50, penalty weight 10); and Oil Rate **Minimum** bbl/d ≥ 500 in
> period 1.
>
> Pin selections: Well A fully selected in period 0 and half in period 1; Well B not selected.
>
> Override the selection rules from the portfolio with the complete set: the same Well A / Well
> B constraints, the four Well C/E dependencies (covering Must/MustNot and OverAll/Before/After/
> During), and the inclusive/exclusive groups with their group limits.

Expected: validates clean against the portfolio (exit 0). The objective "NPV ($ MM)" is a
computed metric not in the portfolio's input data, so the validator emits a single
`crossref.objective_metric` *warning* — that is expected, not a failure.

---

## `scenario/scenario_enum_minimize.json` and `scenario/scenario_enum_linearization.json`

These tiny scenarios exist only to supply the `optimization` enum values the kitchen-sink
scenario cannot also hold (`optimization` is a single object, so `direction` and
`linearization_level` can each carry just one value per file).

- **scenario_enum_minimize.json** — *"Make a scenario 'Minimize Spend' that minimizes Capex,
  with linearization set to ABS/MIN/MAX only."* → `direction: Minimize`,
  `linearization_level: AbsMinMax`.
- **scenario_enum_linearization.json** — *"Make a scenario 'Linearize All' that maximizes
  NPV ($ MM) and linearizes all supported functions."* → `linearization_level: All`.
