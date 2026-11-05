---
name: manage-portfolio
description: >-
  Acts on the user's live Q Portfolio data — lists their portfolios and
  scenarios, loads authored Model/Portfolio/Scenario JSON files in, runs
  optimizations and follows the job, reads selections and optimization logs,
  clones a scenario to compare, edits a scenario in place (a metric limit,
  a forced opportunity, a rule override), edits the model in place (a metric's
  unit or formula, a new metric), copies a portfolio's calculation model, and opens items in the web UI.
  Use when the user refers to their OWN live Portfolio data, or names a
  portfolio or scenario — "list my portfolios", "what scenarios are in North
  Sea 2027", "load this file into Portfolio", "optimize the Base Case", "why
  is my scenario infeasible", "what did it pick", "cap capex at
  50MM", "maximize NPV instead", "change NPV's unit", "add a metric to my
  model", "copy a model to a new portfolio", "open North Sea 2027".
  NOT for how-does-Portfolio-work questions (use `qp-help`)
  nor for authoring a JSON file (use the `write-*-file` skills).
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

A permission denial or a lock is expected behavior, not a bug — relay it plainly
("your account doesn't have X on that portfolio", "that portfolio is locked"), and
don't retry.

## Current portfolio and scenario

Track which portfolio and scenario the user is working on, so they can say "optimize
it" instead of repeating ids. This lives in the conversation only — nothing is
written to disk or to the server.

- **Set explicitly** when the user names one ("switch to North Sea 2027").
- **Set implicitly** by the last successful call that used a portfolio or scenario
  id. Last touched wins. A successful `navigate` counts: its reply names the ids now open.
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
   before uploading. `portfolio_import` starts a **background job** — follow it with
   flow 3 before doing anything else with that portfolio.

   - **Read before you write.** Editing an export is safer than authoring a document
     blind: a Data file re-imports section by section and can remove outcomes, group
     members, dependencies and attribute values, but never an opportunity or
     master-data set (wiki
     `concepts/data-source.md`). Narrow `sections` to what you are changing.
   - **Deleting an opportunity or master-data set** is not an import and no tool does
     it: tell the user to delete it in the web app. A file that still names it in
     `input_data`, `master_data`, `attributes` or `selection_constraints` brings it
     back on the next import (a master-data set possibly as an opportunity), so
     take it out of every section first.
   - **Master data length.** `portfolio_import` warns about a series too short for an
     optimization; lengthen it (wiki `concepts/master-data.md`).

3. **Optimize and wait.** `optimization_run` → `job_wait`. Most optimizations
   finish inside that single call.

   On `wait_ended: BudgetSpent`, wait once more, and if that expires too **stop and
   tell the user**: that it is a long one, what the solver progress shows, and that
   you can keep watching or `job_cancel`. **Two waits, then hand back** — never sit
   in a wait loop on the user's behalf.

   If the `job_wait` call itself errors, the job is left as it was — call
   `job_status` to read its state (a failed job says why there), then `job_wait` again.

4. **Read the answer.** `scenario_selections`. When it returns a warning, **surface it,
   don't swallow it**, and the same when `scenario_list` says `stale: true` (say so
   first and offer `optimization_run` again) — the user needs to know the numbers may not be current.

5. **Explain the optimization.** `optimization_log`, alongside `scenario_selections`.
   It cannot show which metric limit binds: say so rather than inferring it, and don't
   reach for files on disk to fill the gap, because those may not match what's in the product.
   When the user wants the full solver log, use `optimization_log_export` and give them its `download_url`.

6. **Edit a scenario in place.** A metric limit, the objective, a forced opportunity, a
   rule override: `scenario_describe` / `scenario_read`, then `scenario_patch` — no
   files. To override or reset a whole rule section, use `scenario_rules`. Patch
   **echoing the paths the read answered with**; the ops cheat-sheet and the traps
   are in REFERENCE.md. To keep the baseline, use flow 7. When the answer
   carries a `warning`, **pass it on** — the patch is valid, but it may do nothing.

7. **Clone and vary.** `scenario_copy` takes `scenario_patch`'s `ops`, so the copy and
   the change are one call. Optimize both and report them side by side — objective
   values, not just which opportunities differ. Fallbacks are in REFERENCE.md.

8. **Copy or vary a model.** `model_export` carries the recipe and the `section`
   argument for exporting only half. Validate an edited model with
   `write-model-file`'s validator before uploading, and heed the re-import warning
   in the rules below. For a plain list of what a portfolio measures, `model_metrics`
   is cheaper than exporting.

9. **Edit the model in place.** A metric's unit, expressions or derived types, a new
   metric or characteristic: `model_describe` / `model_read`, then `model_patch` —
   `dryRun` first, echoing the paths the read answered with. A filter on an
   attribute or characteristic the model lacks needs no separate patch first: add it
   under `/attributes` in the same patch, or the patch is refused. What it can't carry is
   refused, and the answer names where to do it instead. When the answer carries a
   `warning`, **pass it on** — the patch is valid, but its effect may surprise.

10. **Edit a portfolio's rules or settings in place.** A group limit, an opportunity's
    selection limit, a dependency, the planning horizon or the discount rate:
    `portfolio_describe` / `portfolio_read`, then `portfolio_patch` — no files. Patch
    **echoing the paths the read answered with**. The portfolio's rules are the defaults, so
    the change reaches every scenario that does not own that rule section.
    What is patchable, the ops cheat-sheet and the traps are in REFERENCE.md.

11. **Open it in the web UI.** "Open North Sea 2027", "show me that scenario": call
    `navigate`. Say so in one line.

## Rules

- **Export the smallest section set that covers the change**, on every export tool
  (each names its own argument).
- **Any list the user might pick from is numbered.** Portfolios, scenarios, files in
  a bucket, metrics — always a numbered list, never bullets or prose, so the user
  can just answer "2" or "the third one". When the answer is a bare number, say the
  option it picks in one line before acting: "1." may refer to an earlier list.
- **A patch is already saved.** `scenario_patch`, `portfolio_patch` and `model_patch`
  write when they answer `applied: true`; nothing needs importing after them. When the
  user says "import" right after patches, import only files they named; if none were
  named, say the edits are already saved and ask what to import.
- **Name the target before anything that changes data.** The permission prompt shows
  a tool name and a number; the user needs the portfolio's *name*.
- **Destructive calls never resolve from implicit context.** `portfolio_import`
  into an existing portfolio only when the user named it in this conversation or
  this session created it. Otherwise ask which one, by name.
- **Get a go-ahead before re-importing a model** into a portfolio that already has
  one: tell the user what it clears first.
- **Always mark scratch work `[agent-tmp] `.** On `portfolio_create` that is
  `temporary: true`; on `portfolio_import` you write the prefix into
  `settings.portfolio_name` yourself. Skip it only when the user says it's a keeper.
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
