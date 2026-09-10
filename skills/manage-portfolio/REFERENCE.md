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
including the size limits and the signed-link rules. One thing they don't say:

- **Your shell may have no route to that host.** A Portfolio on `localhost` or a private
  address answers from the user's machine, not necessarily from wherever your commands
  run. A *connection* failure — refused, timed out, no such host — is that, and not an
  expired link: hand the user the exact `curl` to run and ask them for the result.

An expired, tampered-with or swept **link** is a **404** on either route — the three
look identical, and that is deliberate. Don't read a 404 as "the token is
malformed"; re-export or `bucket_create_upload` again for a fresh one.

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

| The user wants to change, on the copy or in place | `scenario_export` sections |
|---|---|
| the objective | `settings, optimization` (see below) |
| a metric limit | `metric_limits` |
| pinned selections | `opportunity_selections` |
| a scenario's own selection rules | that rule section — complete, see above |
| remove a metric limit, selection or group | that section, re-imported with `replaceList: true` |

Scrap files go to a temp directory, and every edited file goes through the matching
`write-*-file` validator before it is uploaded.

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
values per opportunity), `scenario_objective_set`,
`scenario_metric_limit_update`. These are spelled `<entity>_<verb>` like every real
tool, so an agent reading this list does not learn a second naming style.
Objective and constraint changes go through export-edit-import: `scenario_copy` first,
then import the edited section back onto the copy with `scenario_import`'s `scenarioId`. There are **no MCP
resources** either — every read is a tool call, and a document only reaches you by
downloading it.

## Error recipes

Most failures name their own remedy in the message; follow it. These three don't:

| What you see | What it means | Do this |
|---|---|---|
| `whoami` fails | Key unset or wrong, or the host is unreachable | Have the user run `/qp-hi`, which re-checks the entry and the key; stop, don't retry other tools |
| `curl` cannot connect to a bucket link | The host isn't routable from where your commands run, or the server's configured URL is wrong | Call `ping`: a `WARNING:` means the URL — relay it, an administrator fixes it. No warning — give the user the command to run |
| A transfer tool refuses with `No transfer link can be built` | The server has no usable configured MCP URL | Relay the message — an administrator sets the URL; nothing to retry |
| `Permission denied: user '<name>' lacks <Permission> on portfolio <id>` | Expected — the key carries no roles and can never be admin | Report as an account permission issue, not a bug |
| 404 on a download or upload link | Expired, tampered with, or the bucket was swept — indistinguishable by design | Re-export or mint a new bucket; don't retry the same link |
