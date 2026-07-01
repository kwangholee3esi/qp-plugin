---
name: generate-portfolio-file
description: >-
  Generates a validated QPortfolio portfolio file (Portable JSON,
  qp_file_type "QPortfolio Data") from a plain-language description of
  opportunities, their outcomes/metrics, and any selection rules — authoring the
  JSON, schema-validating it, and repairing it so it imports cleanly. Use when a
  user wants to create, build, author, draft, or generate a QPortfolio portfolio
  JSON; turn a description of opportunities and metrics into an importable file;
  mock up or scaffold portfolio input data; or produce a portfolio.json with
  outcomes (certain, or P90/P50/P10 expected-value cases), master data,
  attributes, outcome dependencies, or selection constraints/dependencies/groups.
---

# Generate a QPortfolio portfolio file

Produce one **validated** `*.json` file (`PortfolioData`) the user imports through
the product's normal import flow. This skill does NOT call any API.

The portfolio schema's most important rule — *every opportunity name referenced
anywhere must match a name defined in `input_data`* — is enforced by neither the
JSON Schema nor the importer. The bundled validator (`scripts/validate_portfolio.py`)
catches it, plus numeric/time-series rules. Always run it; never hand over an
unvalidated file.

## Workflow

1. **Gather (targeted gap-filling).** From the user's description, extract: the
   opportunities, each one's metrics, the horizon (number of time periods), and
   whether each opportunity is *certain* (a single outcome) or *uncertain*
   (several weighted outcomes, e.g. P90/P50/P10). Ask focused questions ONLY for
   essentials that block a valid file (see REFERENCE.md → "Ask vs default").
   Apply sensible defaults for everything else — don't interrogate.

2. **Ground.** Use [REFERENCE.md](REFERENCE.md) for field meanings and domain
   conventions. Only when the user uses a domain term REFERENCE.md doesn't cover,
   query the Obsidian QP vault (`mcp__obsidian__vault`) and cite the page.

3. **Author.** Build the JSON following [REFERENCE.md](REFERENCE.md) and the
   few-shot files in [EXAMPLES.md](EXAMPLES.md) (and the schema's own embedded
   `examples`). Always emit `metadata` (with `qp_file_type: "QPortfolio Data"`)
   and `input_data`. By default also emit `selection_constraints` with one
   `opportunity_limits` entry per opportunity defaulting to `total_minimum: 0`,
   `total_maximum: 1`, `time_period_minima: []`, and a **single-period selection
   horizon** `time_period_maxima: [1]`. The per-period maxima must be NON-empty:
   on import, an opportunity with no positive per-period maximum is never selected,
   so default the selection horizon to one period (`[1]`), never `[]`. This array
   is indexed by planning period and is NOT tied to the metric-series length (a
   3-period input series still defaults to `[1]`) — see REFERENCE.md → "Input
   periods vs planning horizon". UNLESS the user specifies different limits, honor
   theirs.
   Add `master_data`, `attributes`, `outcome_dependency`, `selection_dependency`,
   `selection_group` ONLY when the description calls for them. Conventions:
   snake_case keys, string enums, omit optional fields rather than writing
   `null`, never emit `NaN`/`Infinity`. Respect the schema-enforced field limits
   (name max-lengths, non-negative ranges, unique names) — see REFERENCE.md →
   "Field limits & schema-enforced constraints".

4. **Validate & repair (cap 3 passes).** Write the candidate to a scratch path
   (not the final destination) and run:

   ```
   python scripts/validate_portfolio.py <scratch.json> --format json
   ```

   Parse the JSON output. Fix every finding with `severity: "error"` (and any
   sensible warnings) using its `json_path` + `hint`, then re-run. Repeat up to
   3 times.

   **No Python? (Windows)** Swap in the bundled PowerShell validator — same args,
   exit codes and JSON; drive the same loop (use `pwsh` if PowerShell 7+ is present):
   `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/validate_portfolio.ps1 <scratch.json> --format json`

5. **Write or surface.**
   - Exit `0` → write the final `<portfolio-name>.json` (ask the user for the
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

- `scripts/validate_portfolio.py` — schema (Draft 2020-12) + semantic cross-ref
  validator; drives the repair loop. CLI in REFERENCE.md.
- `scripts/validate_portfolio.ps1` + `scripts/qp_validation_common.ps1` — the
  Windows PowerShell 5.1+ fallback (no Python); same CLI, exit codes and JSON
  output as the `.py` validator.
- `schemas/portfolio.schema.json` — bundled schema (validator prefers an in-repo
  `server/Esi.Sp.Portable/Schemas/portfolio.schema.json` when present).
- `scripts/sync_schema.py` — refresh the bundled schema from the server copy.
- [REFERENCE.md](REFERENCE.md) — field meanings, the full check catalog, domain
  conventions (cited), and schema maintenance.
- [EXAMPLES.md](EXAMPLES.md) — annotated few-shot portfolio files.
