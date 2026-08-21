---
name: manage-portfolio
description: >-
  Connects to the user's Q Portfolio installation and acts on their real data —
  lists their portfolios and scenarios, loads authored Model/Portfolio/Scenario
  JSON files in, runs optimizations and follows the job, reads selections and
  optimization logs, clones a scenario into a variant to compare, and copies or
  varies a portfolio's calculation model. Use when
  the user refers to their OWN live Portfolio data, or names a portfolio or
  scenario — "list my portfolios", "what scenarios are in North Sea 2027", "load
  this file into Portfolio", "optimize the Base Case", "why is my scenario
  infeasible", "what did the optimizer pick", "copy that scenario with capex
  capped at 50MM", "copy the model from North Sea into a new portfolio", "add a
  metric to the model in my portfolio", "delete the temp portfolio", "who am I
  connected as". NOT for
  how-does-Portfolio-work questions (use `help`) and NOT for authoring a JSON
  file from a description (use the `write-*-file` skills — this skill loads what
  they produce).
---

# Work with a live Q Portfolio installation

Acts on the user's **real portfolio data** through the `qpmcp` MCP server. Every
call runs as the user their API key belongs to, with that user's permissions.

## Preflight — always first

Call `whoami` once at the start of the session and report it in one line:
*"Connected as **k.holee**."* If it fails, the connection isn't set up — tell the
user to run **`/qp-connect`**, which walks them through it (details in
[REFERENCE.md](REFERENCE.md) → "Connection"), and stop. Don't retry other tools; they will all fail the same way.

An API key carries **no roles at all** — never admin. A permission denial is
expected behavior, not a bug; report it as "your account doesn't have X on that
portfolio".

## Current portfolio and scenario

Track which portfolio and scenario the user is working on, so they can say "optimize
it" instead of repeating ids. This lives in the conversation only — nothing is
written to disk or to the server.

- **Set explicitly** when the user names one ("switch to North Sea 2027").
- **Set implicitly** by the last successful call that used a portfolio or scenario
  id. Last touched wins.
- **Switching portfolio clears the current scenario.** Scenario ids are scoped to a
  portfolio; carrying one across is how you optimize the wrong thing.
- **Name the target before acting** — one short line: *"Optimizing **Base Case** in
  **North Sea 2027**…"*. Not needed for plain reads, and never as a footer on every
  message.
- If the user says "what am I working on", answer from this context.
- If nothing is current and the request needs one, ask — don't guess at the only
  portfolio in the list.

## Flows

1. **Look around.** `list_portfolios` → `list_scenarios(portfolioId)`. Both return
   names, ids and lock state; scenarios also carry `solver_status` and the objective
   metric **by name** with its direction. `list_metrics(portfolioId)` lists what the
   portfolio measures. Report names, not ids.

2. **Load authored files in.** The `write-*-file` skills produce the JSON; this
   flow gets it into the product.
   - `POST /upload` the files → a **folder token** comes back (see REFERENCE.md →
     "Transfer" for the recipe and the size limits — check them *before* uploading).
   - New portfolio: `create_portfolio(name, temporary: true, selectionTimePeriodCount,
     uploadFolder: <token>)` — creates and imports in one call. Match
     `selectionTimePeriodCount` to the model's time period count.
   - Existing portfolio: `import_portfolio_data(portfolioId, folder)`.
   - Both start a **background job** — follow it with flow 3 before doing anything
     else with that portfolio.
   - Scenarios import **after** the model/data job succeeds, with
     `import_scenario(portfolioId, folder)` — synchronous, ids come straight back.
     A scenario references model and data entries by name, so this order is not
     optional.

3. **Optimize and wait.** `run_optimization(portfolioId, scenarioId)` returns a job
   id. Then poll `get_job_status` — every ~5s for the first minute, then ~15s. After
   ~10 minutes stop polling and tell the user the job is still running and that you
   can check again. Never poll in a tight loop. `cancel_job` requests a stop; it's
   soft, so keep polling until the state is terminal.

4. **Read the answer.** `get_selections` — one entry per selected opportunity, by
   name, each carrying the periods it was selected in and a `value` (the
   opportunity's interest; `1` is a full selection), plus the objective value and
   `solver_status`. **Only trust selections when the status is a solved one**; the
   tool returns a warning when they're stale or were never produced. Surface that
   warning, don't swallow it.

5. **Explain the optimization.** `get_optimization_log` gives the solver's own story:
   status, objective vs best bound (their difference is the optimality gap), solve
   time, how it terminated, and the solve trajectory. Combine with `get_selections`.
   **Stop honestly there:** it carries no per-constraint binding information, and no
   tool returns metric values per opportunity, so *which* constraint binds cannot be
   computed from the server today. Say that plainly rather than inferring it from
   files on disk — those may not match what's in the product.

6. **Clone and vary.** There is **no way to edit a scenario in place** — no tool sets
   an objective or changes a constraint. To change one you clone it:
   `export_scenario` → download the file → edit → `POST /upload` → `import_scenario`,
   which creates a **new scenario beside the original**. Then optimize both and
   compare. Full recipe in REFERENCE.md → "Clone and vary". Use
   `write-scenario-file`'s validator on the edited file before uploading.
   To just *show* a scenario's setup, do the same export and download, then read the
   file — `export_scenario` never puts the document in the conversation itself.
   **Changing the objective metric or direction has its own skill** — hand off to
   `change-objective`, which runs this recipe and already knows which metrics can be
   an objective.

7. **Copy or vary a model.** The **model** is the portfolio's metrics-and-expressions
   layer, not its data. `export_model(portfolioId)` writes it to a folder and returns
   the token; `section: "metrics"` or `"attributes"` writes only that half. To **copy**
   the model into another portfolio, hand the token straight to
   `import_portfolio_data` — nothing is transferred. To **vary** it, download the file,
   edit, validate with `write-model-file`'s validator, upload, then
   `import_portfolio_data`, which starts a job (flow 3). Full recipe and the
   section-by-section import semantics in REFERENCE.md → "Copy or vary a model".
   Heed the clearing rule below first. To just *show* a model's expressions, export and
   download, then read the file; for a plain list of what's measured, `list_metrics` is
   cheaper.

## Rules

- **Name the target before anything that changes data.** The permission prompt shows
  a tool name and a number; the user needs the portfolio's *name*.
- **Destructive calls never resolve from implicit context.** `delete_portfolio`, and
  `import_portfolio_data` into a portfolio this session did not create, require the
  user to have named the target in this conversation. Otherwise ask which one, by
  name. `delete_portfolio` erases model, data, scenarios and results — no undo.
- **Re-importing a model can clear fields.** An omitted optional property (unit,
  color, format, category, description) *clears* the stored value. Warn before
  importing a model into a portfolio that already has one.
- **New portfolios default to `temporary: true`**, which prefixes the name with
  `[agent-tmp] ` so it can be found and deleted later. Pass `false` only when the
  user says it's a keeper.
- **Scrap files go to a temp directory**, not the user's working directory — the
  downloaded-and-edited scenario is a byproduct, and the deliverable is the new
  scenario in QP. (The `write-*-file` skills write to the working directory because
  there the file *is* the deliverable.)
- **Don't explain how Portfolio works** — that's the `help` skill, which cites the
  knowledge base.

## Bundled resources

- [REFERENCE.md](REFERENCE.md) — connection setup, the `curl` transfer recipes,
  the full tool map, job states, and error recipes.
