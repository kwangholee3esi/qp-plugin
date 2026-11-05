# manage-portfolio — reference

The tool descriptions and the server's connect-time instructions are the source of
truth for what each tool does and the order to call them in. This file holds only
what they cannot: how this installation is wired, what it does **not** offer, and the
few behaviours no tool description covers.

## Connection

The `qpmcp` server ships with this plugin, but its address and API key are the user's
own: Claude Code asks for them when the plugin is installed and saves them; in Cowork
the user attaches their personal `qpmcp-config.plugin` from Portfolio's Account
Settings, or adds a connector; in claude.ai they add a connector.

**`/qp-hi`** sets it up, and is the only place the steps are spelled out. When `whoami`
fails, point the user there (see the error table below).

## File transfer

Uploads and downloads are **plain HTTP beside the MCP endpoint** — MCP has no file
primitive. `bucket_create_upload` carries the upload recipe and the size limits, the
server's connect-time instructions carry the download recipe, the signed-link rules and
which failed link a new one can fix, and `ping` describes the two addresses. The shell
check of both addresses is `/qp-hi` step 1b.

## Editing an exported document

`scenario_export` and `model_export` each describe the export-edit-import recipe.
What they don't tell you, and you need before you edit:

- **Export only the sections the change touches** — what each one holds is in the
  wiki's field reference (`schemas/portfolio-fields.md`, `schemas/scenario-fields.md`).
- **Narrow a scenario export when updating, not when copying**: imported as a new
  scenario, a file without `settings` gets a generated name, and a rule section it leaves
  out is inherited (wiki `import-export/scenario-file-format.md`).
- **To remove scenario entries**, use `scenario_patch`; `scenario_import` only merges
  into a list section.

For a **scenario** no export is needed: an in-place change is a `scenario_patch` (next
section), a variant is one `scenario_copy` carrying the same `ops`, and a scenario with no
original is `scenario_create` then `scenario_patch`. Export a scenario only when the user
wants it as a document.

Every edited file goes through the matching `write-*-file` validator before it is
uploaded.

## Patching a scenario in place

`scenario_describe`/`scenario_read`/`scenario_patch` describe their own mechanics, and
`scenario_copy`'s `ops` are the same ops in the same format, so everything here covers
those too. What they cannot carry:

**Common edits, as ops** — read first, echo the paths the read returns:

| The user wants | The op |
|---|---|
| change the objective | `replace /optimization/objective_metric_name` (and `/optimization/direction`) |
| cap a metric | `add /metric_limits/-` with a limit entry (`scenario_describe` on `/metric_limits` lists its fields) |
| change a limit's value | `replace /metric_limits/<metric>:<limit type>/targets/<i>/value` |
| drop a limit | `remove /metric_limits/<metric>:<limit type>` |
| force an opportunity in | `replace /selection_constraints/opportunity_limits/<name>/total_minimum` with a positive value (or a period's `time_period_minima/<i>`). NOT `opportunity_selections`: that is the solve's answer, and a run replaces it |
| disable one rule | `replace .../disabled` with `true` |

- **Echo, never construct.** Patch with the `path` and `entity_paths` spellings a read
  answers with.
- **Keep an edit of named `opportunity_limits` entries in its own `scenario_patch` call**,
  also after a `scenario_copy` — a batch confined to named entries writes only those rows,
  which is faster than rewriting the section.
- **`dryRun: true` before a batch you are unsure of**; a `test` op guards a value the
  change depends on.
- **Metric names carry `$` (`… ($MM)`), and a shell eats it.** Build ops strings and
  edited documents without shell interpolation (single quotes, or a file written by a
  tool) — `$MM` silently expanding to nothing produces an unknown-metric refusal that
  looks like a server bug and isn't.
- To just *show* one part of a scenario's setup, `scenario_read` it — no file needed.

## Patching a portfolio's rules and settings in place

`portfolio_describe` / `portfolio_read` / `portfolio_patch` are the scenario triple for the
portfolio's own data, and describe their own mechanics. Same flow: describe or read, then
patch **echoing the paths the read answered with** — never construct them.

**Common edits, as ops:**

| The user wants | The op |
|---|---|
| change an opportunity's selection limit | `replace /selection_constraints/opportunity_limits/<opportunity>/total_maximum` |
| change a group's limit | `replace /selection_group/group_limits/<group>/total_maximum` |
| switch a group or a group limit off | `replace /selection_group/groups/<group>/disabled` (or `.../group_limits/<group>/disabled`) with `true` |
| add a member to a group | `add /selection_group/groups/<group>/members/-` with a member entry |
| drop a group | `remove .../groups/<group>` **and** `remove .../group_limits/<group>`, in one batch — the group alone is refused while its limit remains |
| switch a dependency off | `portfolio_read` with `find` `{"dependent_opportunity": "<name>"}` under `/selection_dependency/dependencies`, then `replace <the path it answered>/disabled` with `true` (the path carries the rule's xid, e.g. `sd-271679`) |
| change the planning horizon | `replace /settings/selection_time_period_count` |
| change the discount rate | `replace /settings/adjustment_policy/annual_discount_rate` |

Rules, groups and dependencies are switched off with `disabled`, never `active`.

The planning horizon and the input periods are separate settings: raising the horizon
does not shorten or invalidate the input data (write-portfolio-file REFERENCE.md,
"Input periods vs planning horizon").

After a whole-section write of `selection_dependency` (the answer warns that the xids changed) or
an import, re-read before patching a rule by xid.

**Prefer names wherever the read gave you one, and keep a small named edit in its own
batch** — a batch confined to named opportunity limits, groups, or dependency rules by xid
writes only those rows; any other batch rewrites the section.

**Before a whole-section rewrite:** add a `test` op on each value the change depends on, and
run it with `dryRun: true` first — a failed `test` stops the batch.

**Defaults reach every scenario that inherits them.** The portfolio's rules are the defaults: a
patch changes every scenario that does not own that rule section, and leaves one that owns it
alone. The answer does not list them — `scenario_describe` shows a section the scenario does
not carry as null. To change one scenario only, patch the scenario instead.

## Cloning and varying a scenario

`scenario_copy` with `ops` is the normal way to make a variant. What its description
cannot carry:

- **The baseline is safe by construction** and nothing needs renaming. Read the source
  first when the ops need real paths, and patch the copy again later with
  `scenario_patch`.
- **An answer with `scenario_id` means the copy exists**, even when its `patch` reports
  errors — name it and offer to patch it or leave it. An answer that says "Nothing was
  copied." means there is no copy: say so, and never name one.
- **Changing the objective** on the copy is one `replace` op on
  `/optimization/objective_metric_name` (and `/optimization/direction`). Which metrics
  may be an objective, and why the name must be copied character-for-character, are in
  the next section.
- **Change the original in place** instead only when the user asks for it. A patch leaves
  its last optimization out of date; only a re-run replaces its selections.
- **Build a scenario from a document** — `scenario_import` with no `scenarioId` — only
  when the user already has that document, and export **every** section the scenario has. What
  an omitted section means on create is in wiki `import-export/scenario-file-format.md`; never
  invent an empty rule section to fill a gap, because an empty one replaces the
  portfolio's rules for that section with nothing.

## Which metrics can be an objective

`model_metrics` returns dozens and most make no sense as an objective. Never show the
user the whole list.

- **Offer only `scalar: true` and `report_only: false`** — usually a handful out of
  dozens, and a scalar is what a user asking "maximize NPV" almost always means. Show
  `metric_name`, `unit` and `description` when present, and mark which one is the
  current objective.
- **If the user wants something outside that shortlist**, or the shortlist is empty (a
  model may have no scalar metrics at all), widen to just `report_only: false`, ask
  which period, or default to the scenario's existing `objective_time_period`.
- **Never abbreviate or retype a `metric_name`** — copy it as `model_metrics` gave it.
- Carry the original `direction` over unless the user asked to flip it.

The scenario's *current* objective is already on `scenario_list`. Say it back in one
line before changing anything, so the user knows the starting point.

## Not available today

Asked for often, so name it rather than improvising: `scenario_results` (metric
values per opportunity). There are **no MCP resources** either — every read is a tool
call, and a document only reaches you by downloading it.

## Error recipes

Most failures name their own remedy in the message; follow it. These don't:

| What you see | What it means | Do this |
|---|---|---|
| `whoami` fails | Key unset or wrong, or the host is unreachable | Have the user run `/qp-hi`, which re-checks the entry and the key; stop, don't retry other tools |
| A transfer link fails | The server's connect-time instructions say what each failure means | Follow them. A Portfolio on `localhost` or a private address answers from the user's machine, not necessarily from where your commands run — give the user the exact `curl` and ask for the result |
