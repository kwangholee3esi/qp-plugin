---
name: generate-scenario-file
description: >-
  Generates a validated QPortfolio scenario file (Portable JSON, qp_file_type
  "QPortfolio Scenario Data") from a plain-language description of a what-if case —
  its optimization objective and direction, metric limits, and any selection-rule
  overrides — authoring the JSON, schema-validating it, and repairing it so it
  imports cleanly. Use when a user wants to create, build, author, draft, or
  generate a QPortfolio scenario JSON; set up an optimization run (maximize NPV,
  minimize spend) with metric/capex limits; override selection
  constraints/dependencies/groups for a case; pin opportunity selections; or
  mock up a scenario.json. Optionally cross-validates opportunity/metric names
  against a companion portfolio file.
---

# Generate a QPortfolio scenario file

Produce one **validated** `*.json` file (`ScenarioData`) the user imports through
the product's normal import flow. This skill does NOT call any API.

A scenario is one **what-if case within a portfolio**: it does *not* define
opportunities or metrics — it **references names defined in the portfolio** and
captures the optimization setup, metric limits, optional pinned selections, and any
selection rules **overridden** from the portfolio defaults. Because the scenario
file carries no definitions, name typos can't be caught by it alone: pass the
companion portfolio (`--portfolio`) so the validator cross-checks every referenced
name. Always run the validator; never hand over an unvalidated file.

## Workflow

1. **Gather (targeted gap-filling).** From the user's description, extract: the
   optimization **objective metric** and **direction** (maximize/minimize), any
   **metric limits** (e.g. "capex ≤ $50MM/yr"), and any **rule overrides** or
   **pinned selections**. Ask focused questions ONLY for the two essentials that
   block a meaningful file — the scenario name and the objective metric (see
   REFERENCE.md → "Ask vs default"). Note any companion portfolio path. Default
   everything else; don't interrogate.

2. **Ground.** Use [REFERENCE.md](REFERENCE.md) for field meanings and domain
   conventions. Only when the user uses a domain term REFERENCE.md doesn't cover,
   query the Obsidian QP vault (`mcp__obsidian__vault`) and cite the page.

3. **Author.** Build the JSON following [REFERENCE.md](REFERENCE.md) and the
   few-shot files in [EXAMPLES.md](EXAMPLES.md) (and the schema's own embedded
   `examples`). Always emit `metadata` (with `qp_file_type: "QPortfolio Scenario
   Data"`), `settings.scenario_name`, and an `optimization` block (objective +
   `direction`, defaulting to `"Maximize"`). Add `metric_limits`,
   `selection_constraints`, `selection_dependency`, `selection_group`, and
   `opportunity_selections` ONLY when the description calls for them.
   - **Rule sections are all-or-nothing overrides.** If you emit
     `selection_constraints` / `selection_dependency` / `selection_group`, it
     **replaces** the portfolio's whole section for this scenario (a present
     section is not merged). So emit the **complete** set for that section —
     seeded from the portfolio's defaults plus the user's change — not just the
     changed entries. Omit a section to inherit the portfolio's.
   - When a companion portfolio is supplied, draw real opportunity/metric names
     from it. Omit advanced solver fields (tolerances, timeout, linearization,
     local solver, Lindo params) unless the user asks.
   - Conventions: snake_case keys, string enums, omit optional fields rather than
     writing `null`, never emit `NaN`/`Infinity`. Respect the schema-enforced
     field limits (name max-lengths, `#RRGGBB` color, numeric ranges, unique
     keys) — see REFERENCE.md → "Field limits & schema-enforced constraints".

4. **Validate & repair (cap 3 passes).** Write the candidate to a scratch path
   (not the final destination) and run (add `--portfolio` whenever you have one):

   ```
   python scripts/validate_scenario.py <scratch.json> --format json [--portfolio <portfolio.json>]
   ```

   Parse the JSON output. Fix every finding with `severity: "error"` (and any
   sensible warnings) using its `json_path` + `hint`, then re-run. Repeat up to
   3 times. Without `--portfolio` the validator emits a `crossref.unchecked`
   warning — surface it so the user knows name references weren't verified.

   **No Python? (Windows)** Swap in the bundled PowerShell validator — same args,
   exit codes and JSON; drive the same loop (use `pwsh` if PowerShell 7+ is present):
   `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/validate_scenario.ps1 <scratch.json> --format json [--portfolio <portfolio.json>]`

5. **Write or surface.**
   - Exit `0` → write the final `<scenario-name>.json` (ask the user for the
     path/name if not given) and report any remaining warnings.
   - Exit `1` after 3 passes → do NOT write; show the remaining errors and ask
     the user how to resolve them.
   - Exit `2` (bad JSON / NaN) → fix the emitted file and retry.
   - Exit `3` → environment problem. If the message says `jsonschema` is not
     installed (or is too old), run `python -m pip install --upgrade 'jsonschema>=4.18'`
     yourself (once) and re-run the validator — don't make the user do it. If that
     install fails because there's **no Python/pip on the machine**, fall back to
     the PowerShell validator (above, Windows) and continue the repair loop against
     its identical output. Only if neither Python nor PowerShell is available, or
     the message says no schema was found, explain the problem to the user in plain
     language; write nothing.

## Bundled resources

- `scripts/validate_scenario.py` — schema (Draft 2020-12) + semantic validator
  with optional `--portfolio` name cross-ref; drives the repair loop. CLI in
  REFERENCE.md.
- `scripts/validate_scenario.ps1` + `scripts/qp_validation_common.ps1` — the
  Windows PowerShell 5.1+ fallback (no Python); same CLI, exit codes and JSON
  output as the `.py` validator.
- `schemas/scenario.schema.json` — bundled schema (validator prefers an in-repo
  `server/Esi.Sp.Portable/Schemas/scenario.schema.json` when present).
- `scripts/sync_schema.py` — refresh the bundled schema from the server copy.
- [REFERENCE.md](REFERENCE.md) — field meanings, the full check catalog, domain
  conventions (cited), and schema maintenance.
- [EXAMPLES.md](EXAMPLES.md) — annotated few-shot scenario files.
