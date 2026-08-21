# manage-portfolio — reference

Lookup material for the flows in [SKILL.md](SKILL.md).

## Connection

The `qpmcp` server is **not bundled with this plugin**. It points at the user's own
Portfolio installation and carries their personal API key, so it lives in their own
config at **user scope** — the top-level `mcpServers` object in `~/.claude.json`.
That file isn't version-controlled and survives plugin updates.

The **`/qp-connect`** command walks through setting it up. The entry looks like this:

```json
"qpmcp": {
  "type": "http",
  "url": "https://portfolio.example.com/",
  "headers": { "Authorization": "Bearer qpk_..." }
}
```

Keep the trailing slash on the URL — the MCP endpoint is served at the host root, and
the transfer recipes below append their own paths.

The key **identifies the user and nothing else** — it carries no roles and can never
be admin. All portfolio access is that user's own permissions.

If `whoami` fails: the entry is missing, the key is wrong, or the host is unreachable.
`claude mcp list` distinguishes them — it shows `qpmcp` and its connection status.
Point the user at `/qp-connect` rather than guessing which of the three broke.

## Transfer — upload and download

File transfer is **plain HTTP beside the MCP endpoint**, not MCP tools — MCP has no
upload primitive. So these are shell calls, not tool calls.

The URL and key come from the `qpmcp` entry in `~/.claude.json`. Read them with a
command substitution, never into a visible variable or an echoed string — **the key
must not appear in the transcript**:

```bash
Q='import json,os,sys;s=json.load(open(os.path.expanduser("~/.claude.json"),encoding="utf-8"))["mcpServers"]["qpmcp"];print(s["url"].rstrip("/") if sys.argv[1]=="url" else s["headers"]["Authorization"])'
```

Use `curl`: it's in `C:\Windows\System32` on Windows 10+, and PowerShell 5.1 has no
usable multipart form support (`Invoke-RestMethod -Form` is PowerShell 6+). Don't try
to parse `~/.claude.json` with PowerShell 5.1's `ConvertFrom-Json` either — it throws
on files that contain case-differing duplicate project keys, which real ones do.

**Upload** — N files of any type into one new folder; returns its token.

```bash
curl -s -X POST "$(python -c "$Q" url)/upload" -H "Authorization: $(python -c "$Q" auth)" -F "file=@my-model.json" -F "file=@my-portfolio.json"
# {"folder":"<token>","files":["my-model.json","my-portfolio.json"]}
```

Limits — **check before uploading**, the endpoint rejects the whole request:
- **32 MiB** per file
- **50 files** per request
- **128 MiB** per request in total — with many files this binds first
- every part must have a file name

**Download** — list a folder, then fetch one file by name.

```bash
curl -s "$(python -c "$Q" url)/download/<token>" -H "Authorization: $(python -c "$Q" auth)"
# {"folder":"<token>","files":[{"name":"scenario-3-7.json","bytes":4211}]}

curl -s -o scenario-3-7.json "$(python -c "$Q" url)/download/<token>/scenario-3-7.json" -H "Authorization: $(python -c "$Q" auth)"
```

A folder belongs to the user who created it. Someone else's token returns **404**,
not 403 — whether it exists isn't the caller's business, so don't read a 404 as "the
token is malformed".

## Clone and vary — full recipe

There is no in-place scenario edit. This is how you change anything about a scenario.

1. `export_scenario(portfolioId, scenarioId)` → `{ folder, files: [{ name }] }`. The
   document stays on the server; only the token comes back.
2. `curl` the file down into a **temp directory** (see the download recipe).
3. Edit the JSON. Remember the override semantics: `selection_constraints`,
   `selection_dependency` and `selection_group` are **all-or-nothing** — a section
   you emit *replaces* the portfolio's whole section for that scenario, so write the
   complete set, not just your change. Change `settings.scenario_name` too, or you
   end up with two scenarios sharing a name.
4. Validate the edited file with the `write-scenario-file` skill's validator before
   uploading — importer errors come back verbatim, but catching them locally is
   faster.
5. `POST /upload` the edited file → new token.
6. `import_scenario(portfolioId, folder)` → a **new** scenario id. The original is
   untouched.
7. `run_optimization` on both, then compare with `get_selections`.

To *copy* a scenario unchanged, skip steps 2–5: hand `export_scenario`'s token
straight to `import_scenario`. Nothing is transferred at all.

## Copy or vary a model — full recipe

The **model** is a portfolio's definitional layer: its metrics, with the expressions
that compute them, and its attribute definitions. The data the model runs on —
opportunities, outcomes and metric *values* — is **not** in this document; that lives
in the Portfolio Data document.

1. `export_model(portfolioId)` → `{ folder, files: [{ name }] }`. Pass
   `section: "metrics"` or `section: "attributes"` to write only that half.
2. To **copy** the model into another portfolio, stop here — hand the token straight
   to `import_portfolio_data(otherPortfolioId, folder)`. Nothing is transferred at all.
3. To **vary** it, `curl` the file down into a **temp directory** and edit it.
4. Validate the edited file with the `write-model-file` skill's validator before
   uploading — it checks every expression reference, function name and argument count.
5. `POST /upload` the edited file → new token.
6. `import_portfolio_data(portfolioId, folder)` → a **background job**. Follow it with
   flow 3 in SKILL.md before doing anything else with that portfolio.

Import semantics to know *before* you edit:

- **An omitted section is left alone.** A metrics-only document doesn't touch the
  portfolio's attributes, and an attributes-only document doesn't touch its metrics.
- **Except**: importing metrics still *creates* any attribute their expressions group
  by or filter on — a model has to be internally consistent.
- **An omitted optional property clears the stored value** (unit, color, format,
  category, description). An exported-then-edited file already carries them all, which
  is exactly why editing an export is safer than hand-writing a partial model.

## Tool map

Every tool answers in **snake_case**, spelled the same way the QPortfolio JSON files
these skills author spell it — what you read back is what you write.

| Tool | Does | Notes |
|---|---|---|
| `whoami` | Effective user | No permissions needed. Preflight. |
| `ping` | Connectivity + server version | |
| `list_portfolios` | id, name, lock state | |
| `list_scenarios` | id, name, lock state, `solver_status`, objective metric by name | Needs `portfolioId` |
| `list_metrics` | The model's metrics, with `scalar`, `report_only`, unit, category | Interim sub-metrics excluded; otherwise unfiltered — the skill picks what to offer. Use this for *what* the portfolio measures; `export_model` for the expressions behind it |
| `export_scenario` | Scenario document → folder token | Document does **not** enter the conversation |
| `export_model` | Model document → folder token | Whole model, or one `section`. Document does **not** enter the conversation |
| `get_selections` | `opportunity_selections` — each opportunity by name with its periods and `value` — objective value, `solver_status` | Check the staleness warning |
| `get_optimization_log` | Solver log summary, job state, trajectory | **No per-constraint binding info** |
| `run_optimization` | Starts a job | Returns job id |
| `get_job_status` | Job state | Poll this |
| `cancel_job` | Requests a stop | Soft — keep polling |
| `create_portfolio` | New portfolio, optionally imported | `temporary: true` by default |
| `import_portfolio_data` | Model + Data docs of a folder → job | Scenario docs ignored here |
| `import_scenario` | Scenario docs of a folder | Synchronous; needs model/data first |
| `delete_portfolio` | Erases everything in it | No undo. Never from implicit context |

**Not available today** (asked for often, so name it rather than improvising):
`get_scenario_results` (metric values per opportunity), `copy_scenario`,
`set_objective`, `update_metric_constraint`. Objective and constraint changes go
through clone-and-vary. There are **no MCP resources** either — every read is a
tool call, and a document only reaches you by downloading it.

## Job states

`get_job_status` returns one of:

| State | Meaning |
|---|---|
| `queued` | Waiting for the job worker to pick it up |
| `running` | In progress; may carry solver progress (elapsed, iterations, objective value, relative gap) |
| `succeeded` | Done. Carries `solver_status` (e.g. Optimal, Infeasible) |
| `failed` | Carries an error detail |
| `canceled` | Stopped on request |

`succeeded` with `solver_status` **Infeasible** is a *successful job* with no
answer — don't report it as a failure. A `warning` of "No solution exists" means the
scenario's selections were **not changed**, so `get_selections` still shows the
previous answer.

Polling cadence: ~5s for the first minute, then ~15s, stop at ~10 minutes.
<!-- ponytail: cadence is a guess, not a measurement — tune it once real solve
     times on a demo instance are known. -->

## Error recipes

| What you see | What it means | Do this |
|---|---|---|
| `whoami` fails | Key unset/wrong, or host unreachable | Check both env vars; stop, don't retry other tools |
| `Permission denied: user X lacks Y` | Expected — the key has no roles | Report as an account permission issue, not a bug |
| 404 on a download token | Expired, or belongs to another user | Re-export or re-upload; don't retry |
| `Transfer folder '<t>' holds no '<type>' document` | Wrong import tool for the folder's contents | The message lists what it *does* hold; route to the matching tool |
| Import job `failed` | A QPortfolio JSON file validation or data error | Errors come back verbatim; fix the JSON and re-upload |
| Scenario import rejects a name | Model/data import hadn't finished, or a name typo | Confirm the data job `succeeded`, then check names against the portfolio |
