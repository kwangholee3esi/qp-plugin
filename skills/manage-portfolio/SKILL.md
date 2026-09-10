---
name: manage-portfolio
description: >-
  Acts on the user's live Q Portfolio data — lists their portfolios and
  scenarios, loads authored Model/Portfolio/Scenario JSON files in, runs
  optimizations and follows the job, reads selections and optimization logs,
  clones a scenario to compare, changes what a scenario optimizes for, and
  copies or varies a portfolio's calculation model. Use when the user refers to
  their OWN live Portfolio data, or names a portfolio or scenario — "list my
  portfolios", "what scenarios are in North Sea 2027", "load this file into
  Portfolio", "optimize the Base Case", "why is my scenario infeasible", "what
  did the optimizer pick", "copy that scenario with capex capped at 50MM",
  "maximize NPV instead", "copy the model from North Sea into a new portfolio",
  "add a metric to the model in my portfolio", "who am I connected as". NOT for
  how-does-Portfolio-work questions (use `qp-help`) and NOT for authoring a JSON
  file from a description (use the `write-*-file` skills — this skill loads what
  they produce).
---

# Work with a live Q Portfolio installation

Acts on the user's **real portfolio data** through the `qpmcp` MCP server. Every
call runs as the user their API key belongs to, with that user's permissions.

## Preflight — always first

Call `ping`, then `whoami`, once at the start of the session and report in one
line: *"Connected as **j.smith**."* Relay a `WARNING:` from `ping` in that same
line, in the user's words rather than the server's, and carry on.
If `whoami` fails, the connection isn't set up — tell the
user to run **`/qp-hi`**, which offers to walk them through it, and stop. Don't
retry other tools; they will all fail the same way.

A permission denial is expected behavior, not a bug — report it as "your account
doesn't have X on that portfolio", and don't retry.

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

Each tool describes itself, and the server hands you the end-to-end sequence when
you connect. What follows is only the judgement those cannot carry.

1. **Look around.** `portfolio_list` → `scenario_list` → `model_metrics`. Report
   names, not ids.

2. **Load authored files in.** The `write-*-file` skills produce the JSON; the
   bucket flow gets it into the product. Run each file through its skill's validator
   before uploading. `portfolio_create` and `portfolio_import` start a **background
   job** — follow it with flow 3 before doing anything else with that portfolio.

   - **Settings are just another Data document.** To change a portfolio's calculation
     calendar or its discount/inflation rates, author a Data document carrying only
     `metadata` and `settings` and import it like any other file — `write-portfolio-file`
     carries the field rules, and `portfolio_import` says what the block replaces.

   - **Read before you write.** `portfolio_export` writes a portfolio's own data out
     as a Data document — the third export tool, beside `model_export` for the model and
     `scenario_export` for a scenario. Editing an export is safer than authoring a
     document blind, because these sections are replace-or-merge on import and never
     purely additive; this is the same judgement flow 6 states for scenarios. Narrow
     `sections` to what you are changing — the blast radius of a re-import is per
     section, and the tool's own description spells out what each one does. Scrap files
     go to a temp directory, not the user's working directory.

3. **Optimize and wait.** `optimization_run` → `job_wait`. Most optimizations
   finish inside that single call.

   On `wait_ended: BudgetSpent`, wait once more, and if that expires too **stop and
   tell the user**: that it is a long one, what the solver progress shows, and that
   you can keep watching or `job_cancel`. **Two waits, then hand back** — never sit
   in a wait loop on the user's behalf.

4. **Read the answer.** `scenario_selections`. When it returns a warning, **surface it,
   don't swallow it** — the user needs to know the numbers may not be current.

5. **Explain the optimization.** `optimization_log`, alongside `scenario_selections`.
   Where it says to stop, stop — and in particular don't reach for files on disk to
   fill the gap, because those may not match what's in the product.

6. **Clone and vary.** `scenario_copy` first, then edit the copy. One call gives a full
   duplicate — more than an exported document carries — so the baseline is safe by
   construction and nothing needs renaming. No tool sets an objective or changes a
   constraint, so the edit is still export → edit the file → import back, but narrowed:
   export only the section you are changing **from the copy**, and `scenario_import` it
   back with the copy's `scenarioId`. Validate the edited file with
   `write-scenario-file`'s validator first, then optimize both and compare.

   The copy exists before the edit does — if the edit or the import then fails, say so
   and name the copy you left behind; nothing deletes it.

   **Changing the objective** is that recipe with `sections: "settings, optimization"`:
   edit `optimization.objective_metric_name` and `direction` on the copy, then optimize
   both and report them side by side — objective values, not just which opportunities
   differ. Which metrics may be an objective, and why the name must be copied
   character-for-character, are in REFERENCE.md.

   Two fallbacks. **Change the original in place** only when the user asks for it, and
   say first that it overwrites that scenario's existing result. **Build a variant from
   a document** — omit `scenarioId` — only when there is no original to copy, and export
   **every** section the scenario has. What an omitted section means on create is in
   `scenario_import`'s own description — never invent an empty rule section to fill a
   gap, because an empty one becomes a complete override.

   To just *show* one part of a scenario's setup, export only that section and read it.

7. **Copy or vary a model.** `model_export` carries the recipe and the `section`
   argument for exporting only half. Validate an edited model with
   `write-model-file`'s validator before uploading, and heed the re-import warning
   in the rules below. For a plain list of what a portfolio measures, `model_metrics`
   is cheaper than exporting.

## Rules

- **Export the smallest section set that covers the change**, on every export tool
  (each names its own argument). REFERENCE.md maps each kind of change to its sections.
- **Any list the user might pick from is numbered.** Portfolios, scenarios, files in
  a bucket, metrics — always a numbered list, never bullets or prose, so the user
  can just answer "2" or "the third one".
- **Name the target before anything that changes data.** The permission prompt shows
  a tool name and a number; the user needs the portfolio's *name*.
- **Destructive calls never resolve from implicit context.**
  `portfolio_import` into a portfolio this session did not create requires the
  user to have named the target in this conversation. Otherwise ask which one, by
  name.
- **Warn before re-importing a model** into a portfolio that already has one —
  `portfolio_import` describes what a re-import overwrites, and the user
  should hear it before you start the job.
- **Always pass `temporary: true`.** Pass `false` only when the user says it's a keeper.
- **A `curl` that cannot *connect* is not an expired link** — either that host isn't
  routable from your shell, or the server's configured URL is wrong; `ping`'s warning
  tells the two apart. Hand the user the command to run.
- **Scrap files go to a temp directory**, not the user's working directory — the
  downloaded-and-edited scenario is a byproduct, and the deliverable is the new
  scenario in QP. (The `write-*-file` skills write to the working directory because
  there the file *is* the deliverable.)
- **Don't explain how Portfolio works** — that's the `qp-help` skill, which cites the
  knowledge base.

## Bundled resources

- [REFERENCE.md](REFERENCE.md) — what this installation does *not* offer, which
  metrics can be an objective, the scenario-override rule, and the handful of
  behaviours no tool description covers.
