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
addresses and the shell check. A *connection* failure is not an expired link — see the
error table below.

**Read a 404's body before you retry, and retry at most once.** A 404 with an **empty
body** is not a bad link at all — nothing is serving `ping`'s `server=` address, so
no link will ever work until an administrator fixes the configuration. Stop and tell
the user.

A 404 carrying a JSON `error` body names its cause — follow its message. When it points
at the link itself, re-export or `bucket_create_upload` again, **once**. If the fresh
link fails the same way, stop treating it as expiry and tell the user: a body shape is a
hint about which server answered, not a promise, and a proxy in front of Portfolio can
make a configuration failure look like a link failure.

## Editing an exported document

`scenario_export` and `model_export` each describe the export-edit-import recipe.
What they don't tell you, and you need before you edit:

- **Leave `settings.scenario_name` alone** when the import updates an existing scenario —
  under copy-first that is the normal case, and `scenario_copy` has already named the copy.
  Only when you build a variant by importing a document as a NEW scenario must you set it.
- **A document that creates a new scenario** must carry each rule section it overrides
  complete — seeded from the portfolio's rules plus the change, not just the change.
  How a section meets a scenario that already has one is `scenario_import`'s
  `replaceList`'s question.
- **Filter `attributes` rows yourself** if an edit should only reach one kind of
  opportunity.
- **Export only the sections the change touches** — `portfolio_export`'s `sections`
  says what each one holds.

For a **scenario** no export is needed: an in-place change is a `scenario_patch` (next
section), and a variant is one `scenario_copy` carrying the same `ops`. Export a scenario
only to build one from a document where there is no original to copy.

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
| cap a metric | `add /metric_limits/-` with `{metric_name, limit_type: "Maximum", targets: [{period, value}]}` |
| change a limit's value | `replace /metric_limits/<name>/targets/<i>/value` |
| drop a limit | `remove /metric_limits/<name>` |
| pin selections | `replace /opportunity_selections/<name>/selections` |
| disable one rule | `replace .../disabled` with `true` |

- **Echo, never construct.** Patch with the `path` and `entity_paths` spellings a read
  answers with.
- **On `selection_constraints`, prefer ops on named `opportunity_limits` entries.** Read
  the section, change only the entries meant, leave the rest as they came.
- **`dryRun: true` before a batch you are unsure of**; a `test` op guards a value the
  change depends on.
- **Metric names carry `$` (`… ($MM)`), and a shell eats it.** Build ops strings and
  edited documents without shell interpolation (single quotes, or a file written by a
  tool) — `$MM` silently expanding to nothing produces an unknown-metric refusal that
  looks like a server bug and isn't.
- To just *show* one part of a scenario's setup, `scenario_read` it — no file needed.

## Cloning and varying a scenario

`scenario_copy` with `ops` is the normal way to make a variant. What its description
cannot carry:

- **The baseline is safe by construction** and nothing needs renaming. Read the source
  first when the ops need real paths, and patch the copy again later with
  `scenario_patch`.
- **If the ops fail, the copy is still real** — name it and offer to patch it or leave
  it; nothing deletes it.
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
  model may have no scalar metrics at all), widen to just `report_only: false`, ask
  which period, or default to the scenario's existing `objective_time_period`.
- **Never abbreviate or retype a `metric_name`** — copy it as `model_metrics` gave it.
- Carry the original `direction` over unless the user asked to flip it.

The scenario's *current* objective is already on `scenario_list`. Say it back in one
line before changing anything, so the user knows the starting point.

## Not available today

Asked for often, so name it rather than improvising: `scenario_results` (metric
values per opportunity).
In-place scenario changes go through `scenario_patch`, and a variant through
`scenario_copy` with `ops`; building a scenario from a document still goes
through export-edit-import. Portfolio data and the model have no patch —
export-edit-import only. There are **no MCP resources** either — every read is a tool
call, and a document only reaches you by downloading it.

## Error recipes

Most failures name their own remedy in the message; follow it. These don't:

| What you see | What it means | Do this |
|---|---|---|
| `whoami` fails | Key unset or wrong, or the host is unreachable | Have the user run `/qp-hi`, which re-checks the entry and the key; stop, don't retry other tools |
| `curl` cannot connect to a bucket link | Routing or configuration, not an expired link — a working MCP connection proves nothing about the transfer address | A fresh link can never fix it. Call `ping` and follow what it says about `server=`, relaying any `WARNING:`. A Portfolio on `localhost` or a private address answers from the user's machine, not necessarily from where your commands run — give the user the exact `curl` and ask for the result |
| 404 with an **empty** body | Nothing is serving `ping`'s `server=` address — a misconfigured URL, not a bad link | A fresh link cannot help and retrying loops forever. Tell the user an administrator must correct the Portfolio server address |
| 404 **with** a JSON `error` body | Its message names the cause | Follow the message. If it is the link, re-export or mint a new bucket **once**; never retry the same link, and if the fresh one fails identically, stop and tell the user — it is configuration, not expiry |
