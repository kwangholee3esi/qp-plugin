# manage-portfolio — reference

The tool descriptions and the server's connect-time instructions are the source of
truth for what each tool does and the order to call them in. This file holds only
what they cannot: how this installation is wired, what it does **not** offer, and the
few behaviours no tool description covers.

## Connection

The `qpmcp` server is **not bundled with this plugin**. It points at the user's own
Portfolio installation and carries their personal API key, so it lives in their own
config at **user scope** — the top-level `mcpServers` object in `~/.claude.json`.
That file isn't version-controlled and survives plugin updates. Some environments
define it at **project scope** instead (a `.mcp.json` next to the project root) — the
user's `claude mcp list` shows which.

**`/qp-hi`** sets it up, and is the only place the entry is spelled out.

If `whoami` fails: the entry is missing, the key is wrong, or the host is unreachable.
Point the user at `/qp-hi` rather than guessing which of the three broke; the user's
own `claude mcp list` tells the three apart.

## File transfer

Uploads and downloads are **plain HTTP beside the MCP endpoint** — MCP has no file
primitive. `bucket_create_upload` and the export tools each carry their own recipe,
including the size limits and the signed-link rules, and `ping` describes the two
addresses and the shell check. One thing none of them say:

- **A *connection* failure is not an expired link.** Refused, timed out, no such host —
  that is routing or configuration, and a fresh link can never fix it. A Portfolio on
  `localhost` or a private address answers from the user's machine, not necessarily from
  wherever your commands run: hand the user the exact `curl` and ask them for the result.

**Read a 404's body before you retry, and retry at most once.** A 404 with an **empty
body** is not a bad link at all — nothing is serving `ping`'s `server=` address, so
no link will ever work until an administrator fixes the configuration. `ping` does not
catch this, because it only checks that the URL is well-formed. Stop and tell the user.

A 404 carrying a JSON `error` body is an expired, tampered-with or swept **link** — the
three look identical, and that is deliberate, so don't read one as "the token is
malformed". Re-export or `bucket_create_upload` again, **once**. If the fresh link fails
the same way, stop treating it as expiry and tell the user: a body shape is a hint about
which server answered, not a promise, and a proxy in front of Portfolio can make a
configuration failure look like a link failure.

## Editing an exported document

`scenario_export` and `model_export` each describe the export-edit-import recipe.
What they don't tell you, and you need before you edit:

- **Leave `settings.scenario_name` alone** when the import updates an existing scenario —
  under copy-first that is the normal case, and `scenario_copy` has already named the copy.
  Only when you build a variant by importing a document as a NEW scenario must you set it.
- **A scenario's rule sections override the portfolio's all-or-nothing** — write the
  complete set, not just your change; `write-scenario-file` covers this in full. How a
  section meets a scenario that already has one is a different question, and
  `scenario_import`'s `replaceList` owns that one.
- **Filter `attributes` rows yourself** if an edit should only reach one kind of
  opportunity — the export is the whole table.

### Which sections to export for a change

Export only these.

| The user wants to change | `portfolio_export` sections |
|---|---|
| discount or inflation rate, calendar | `settings` |
| an opportunity's input values | `input_data` |
| a master-data set's values | `master_data, attributes` |
| an attribute value | `attributes` |
| an outcome dependency | `outcome_dependency` |
| a selection limit | `selection_constraints` |
| a selection dependency | `selection_dependency` |
| a group's members or its limits | `selection_group` |

For a **scenario** no export is needed: an in-place change is a `scenario_patch` (next
section), and a variant is one `scenario_copy` carrying the same `ops`. Export a scenario
only to build one from a document where there is no original to copy.

Scrap files go to a temp directory, and every edited file goes through the matching
`write-*-file` validator before it is uploaded.

## Patching a scenario in place

`scenario_describe`/`scenario_read`/`scenario_patch` describe their own mechanics, and
`scenario_copy`'s `ops` are the same ops in the same format, so everything here covers
those too. What they cannot carry:

**Common edits, as ops** — read first, echo the paths the read returns:

| The user wants | The op |
|---|---|
| change the objective | `replace /optimization/objective_metric_name` (and `/optimization/direction`) |
| cap a metric | `add /metric_limits/-` with `{metric_name, limit_type: "Maximum", targets: [{period, value}]}` |
| change a limit's value | `replace /metric_limits/<name>/targets/<i>/value` |
| drop a limit | `remove /metric_limits/<name>` |
| pin selections | `replace /opportunity_selections/<name>/selections` |
| disable one rule | `replace .../disabled` with `true` |

- **Echo, never construct.** Every read answers with `path` and `entity_paths` —
  patch with those spellings. In a name, `/` is written `~1` and `~` is `~0`; a name
  inside a list matches case-insensitively and the answer carries the stored spelling,
  but a field segment — the section name among them — does not.
- **An echoed index is good for one write.** Any list in the document may come back in a
  different order after a write — `metric_limits` targets re-sort by period, and
  `settings/characteristics` re-sorts too — so an index that was right before the write may
  address a different row after it. Names survive a write; positions do not. Re-read before
  addressing by index a second time.
- **A name is never patchable.** `scenario_name`, `metric_name`, `opportunity_name`,
  `group_name` and `attribute` are how an entry is addressed, so the patch refuses them — as
  a leaf, and inside a whole-entry replace that carries a different name. Rename a *scenario*
  by copying it under the new name (`scenario_copy`'s `name` argument). Rename something
  *inside* a scenario by replacing the **whole section**, carrying the renamed entry and
  every row that refers to it — not remove-then-add, which on a selection group was measured
  to leave the removed entry behind alongside the new one. `objective_metric_name` is not a
  name in this sense — it picks which metric to optimize, and patches normally; nor are a
  selection dependency's `dependent_opportunity`/`independent_opportunity`, which are
  references and re-point like any other field.
- **A metric can carry two limits** (a Minimum and a Maximum), so its name alone can be
  ambiguous — the refusal lists the index paths; pick the right one from a read.
- **Selection dependencies have no name.** First touch goes through `scenario_read`'s
  `find` with field/value pairs (e.g. `{"dependent_opportunity": "X"}`); patch the
  path it answers with.
- **A patched section replaces that whole section.** That is what makes `remove` work —
  and it is why patching `selection_constraints` deserves care: as `scenario_import`'s
  `replaceList` warns, an opportunity left without any selection constraint cannot be
  selected at all. Read the section, change only the entries meant, leave the rest as
  they came.
- **`dryRun: true` before a batch you are unsure of**; a `test` op guards a value the
  change depends on, and a failed op writes nothing — there is no partial apply.
- **Metric names carry `$` (`… ($MM)`), and a shell eats it.** Build ops strings and
  edited documents without shell interpolation (single quotes, or a file written by a
  tool) — `$MM` silently expanding to nothing produces an unknown-metric refusal that
  looks like a server bug and isn't.
- A rule section the scenario does not override is `null` in the document — `add` the
  complete section to create the override (all-or-nothing, as above).

## Cloning and varying a scenario

`scenario_copy` with `ops` is the normal way to make a variant. What its description
cannot carry:

- **The copy is made before the ops are applied.** If they fail, the answer's `patch`
  field says so and the copy is real but unpatched — name it and offer to patch it or
  leave it; nothing deletes it.
- **Changing the objective** on the copy is one `replace` op on
  `/optimization/objective_metric_name` (and `/optimization/direction`). Which metrics
  may be an objective, and why the name must be copied character-for-character, are in
  the next section.
- **Change the original in place** instead only when the user asks for it — say first
  that it overwrites that scenario's existing result.
- **Build a scenario from a document** — `scenario_import` with no `scenarioId` — only
  when there is no original to copy, and export **every** section the scenario has. What
  an omitted section means on create is in `scenario_import`'s own description; never
  invent an empty rule section to fill a gap, because an empty one becomes a complete
  override.

## Which metrics can be an objective

`model_metrics` returns dozens and most make no sense as an objective. Never show the
user the whole list.

- **Offer only `scalar: true` and `report_only: false`** — usually a handful out of
  dozens, and a scalar is what a user asking "maximize NPV" almost always means. Show
  `metric_name`, `unit` and `description` when present, and mark which one is the
  current objective.
- **If the user wants something outside that shortlist**, or the shortlist is empty (a
  model may have no scalar metrics at all), widen to just `report_only: false` and say
  plainly that these are per-period metrics, so you also need a period — ask which one,
  or default to the scenario's existing `objective_time_period`.
- **Copy `metric_name` exactly.** The names are long and carry punctuation
  (`Discounted Cash Flow ($ MM)- With Sum`). Abbreviate or retype it and the import
  fails with `Optimization Objective Metric Not Found`.
- Carry the original `direction` over unless the user asked to flip it.

The scenario's *current* objective is already on `scenario_list`
(`objective_metric_name`, `direction`, `objective_time_period`). Say it back in one line
before changing anything, so the user knows the starting point.

## Response shape

Every tool that answers with JSON answers in **snake_case**, spelled the same way the
QPortfolio JSON files these skills author spell it — what you read back is what you
write. Some answers and some refusals come back as a plain sentence instead of JSON;
read those as written rather than trying to parse them.

## Not available today

Asked for often, so name it rather than improvising: `scenario_results` (metric
values per opportunity). It is spelled `<entity>_<verb>` like every real tool, so an
agent reading this list does not learn a second naming style.
In-place scenario changes go through `scenario_patch`, and a variant through
`scenario_copy` with `ops`; building a scenario from a document still goes
through export-edit-import. Portfolio and model changes have no patch yet —
export-edit-import only. There are **no MCP resources** either — every read is a tool
call, and a document only reaches you by downloading it.

## Error recipes

Most failures name their own remedy in the message; follow it. These don't:

| What you see | What it means | Do this |
|---|---|---|
| `whoami` fails | Key unset or wrong, or the host is unreachable | Have the user run `/qp-hi`, which re-checks the entry and the key; stop, don't retry other tools |
| `curl` cannot connect to a bucket link | Routing or configuration, not an expired link — a working MCP connection proves nothing about the transfer address | Call `ping` and follow what it says about `server=`, relaying any `WARNING:`. Give the user the command to run |
| A transfer tool refuses with `No transfer link can be built` | The server has no usable configured file transfer URL | Relay the message — an administrator sets the URL; nothing to retry |
| `Permission denied: user '<name>' lacks <Permission> on portfolio <id>` | Expected — the key carries no roles and can never be admin | Report as an account permission issue, not a bug |
| 404 with an **empty** body | Nothing is serving `ping`'s `server=` address — a misconfigured URL, not a bad link | A fresh link cannot help and retrying loops forever. Tell the user an administrator must fix `McpSettings:ServerRoot` |
| 404 **with** a JSON `error` body | Most likely expired, tampered with, or swept — those three are indistinguishable by design | Re-export or mint a new bucket **once**; never retry the same link, and if the fresh one fails identically, stop and tell the user — it is configuration, not expiry |
