---
name: write-model-file
description: >-
  Generates a validated QPortfolio model file (Portable JSON, qp_file_type
  "QPortfolio Model") from a plain-language description of a portfolio's
  calculation model — its metrics (inputs, master data, computed metrics with
  expressions), derived metrics, and attribute definitions — authoring the JSON,
  schema-validating it, and repairing it so it imports cleanly. Use when a user
  wants to create, build, author, draft, or generate a QPortfolio model JSON;
  define metrics or computed/expression metrics (revenue, cashflow, tax
  formulas); write model expressions or formulas; set up derived metrics
  (cumulative, discounted, inflated, totals); or define attributes and their
  characteristics for grouping, filtering, and master-data matching.
---

# Generate a QPortfolio model file

Produce one **validated** `*.json` file (`ModelData`) the user imports through
the product's normal import flow. This skill only writes the file — loading it into a live installation is the
`manage-portfolio` skill's job.

A model is the **definitional layer** of a portfolio: its metrics and attribute
definitions. The data those metrics run on lives in a separate portfolio data
file — **names are the join key**, so every name here must match the data file
exactly. The rules the schema alone can't catch are the expression rules: every
`${...}` reference must resolve to a metric defined in this same file, and
formulas must use the closed QPortfolio function set with the right argument
counts — the bundled validator checks all of this. Always run it; never hand
over an unvalidated file.

**Companion files.** When creating a full import set from scratch, author in
the order **model → portfolio → scenario** (the model defines the vocabulary).
Keep metric/attribute names and units identical across model and portfolio
data — they are the join key and no validator checks the join.

## Workflow

1. **Gather (targeted gap-filling).** From the user's description, extract: the
   **input metrics** (per-opportunity values), any **master-data metrics**
   (prices, FX, inflation), the **computed metrics** with their **formulas**,
   any **derived metrics** (cumulative/discounted/total transforms), and any
   **attributes**. Ask focused questions ONLY for what blocks a meaningful
   file — a computed metric whose formula you cannot infer (see REFERENCE.md →
   "Ask vs default"). Default everything else; don't interrogate.

2. **Ground.** Use [REFERENCE.md](REFERENCE.md) for the expression language,
   calculation levels, and domain conventions. Only when the user uses a domain
   term REFERENCE.md doesn't cover, query the QP knowledge vault (the `qpwiki`
   MCP server's `vault` tool) and cite the page.

3. **Author.** Build the JSON following [REFERENCE.md](REFERENCE.md) and the
   few-shot files in [EXAMPLES.md](EXAMPLES.md) (and the schema's own embedded
   `examples`). Always emit `metadata` (with `qp_file_type: "QPortfolio
   Model"`). For every computed metric state `metric_type: "Computed"`, an
   explicit `level`, and its `expressions`. Add `attributes` only when the
   model filters, groups, or matches master data by them.
   - **A metric definition is complete.** On re-import into an existing model,
     an omitted optional property (unit, color, format, category, description)
     CLEARS the stored value — state every property the user wants kept. For a
     brand-new model there is nothing to clear: omit optionals freely. Never
     emit `"metrics": []` unless the user explicitly wants every computed
     metric deleted (see REFERENCE.md → "Re-import semantics").
   - Use a `derived` entry (`["CumSum", "Disc"]`) instead of hand-writing the
     equivalent expression whenever the origin metric is linear and
     Interest-scaled (see REFERENCE.md); reference it as `${Name#Type}`.
   - Conventions: snake_case keys, string enums, omit optional fields rather
     than writing `null`, never emit `NaN`/`Infinity`. Respect the
     schema-enforced field limits (name max-lengths, no braces in names,
     `#RRGGBB` colors) — see REFERENCE.md → "Field limits & schema-enforced
     constraints".

4. **Validate & repair (cap 3 passes).** Write the candidate to a scratch path
   (not the final destination) and run:

   ```
   python scripts/validate_model.py <scratch.json> --format json
   ```

   Parse the JSON output. Fix every finding with `severity: "error"` (and any
   sensible warnings) using its `json_path` + `hint`, then re-run. Repeat up to
   3 times.

   **No Python? (Windows)** Swap in the bundled PowerShell validator — same args,
   exit codes and JSON; drive the same loop (use `pwsh` if PowerShell 7+ is present):
   `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/validate_model.ps1 <scratch.json> --format json`

5. **Write or surface.**
   - Exit `0` → write the final file — when the user gave no path, default to
     `<kebab-case-topic>-model.json` in the working directory and ask only if
     that file already exists — and report any remaining warnings.
     Then **offer** to load it in: when the `qpmcp` MCP server is connected, the
     `manage-portfolio` skill uploads and imports it. Offer, don't do it unasked.
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

- `scripts/validate_model.py` — schema (Draft 2020-12) + semantic validator
  incl. a formula tokenizer (references, function names, argument counts);
  drives the repair loop. CLI in REFERENCE.md.
- `scripts/validate_model.ps1` + `scripts/qp_validation_common.ps1` — the
  Windows PowerShell 5.1+ fallback (no Python); same CLI, exit codes and JSON
  output as the `.py` validator.
- `schemas/model.schema.json` — bundled schema (validator prefers an in-repo
  `server/Esi.Sp.Portable/Schemas/model.schema.json` when present).
- `scripts/sync_schema.py` — refresh the bundled schema from the server copy.
- [REFERENCE.md](REFERENCE.md) — the expression language, re-import semantics,
  the full check catalog, domain conventions (cited), and schema maintenance.
- [EXAMPLES.md](EXAMPLES.md) — annotated few-shot model files.
