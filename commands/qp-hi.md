---
description: Start a Q Portfolio session — check the connection, and show what you can ask for
argument-hint: "[portfolio url]"
---

Bootstrap a Q Portfolio working session: verify the connection, greet the user, and
tell them in one sentence what this plugin can do for them.

Do the steps in order. Keep the whole reply short — a greeting, a connection line, the
one-sentence capability summary, and one invitation to start. Do **not** paste setup instructions
unless the user asks for them.

## Vocabulary for this session

These words carry their **Q Portfolio** meaning, not their everyday one. This is a
disambiguation cue for reading the user's intent — one clause each, with the page that
actually defines it. Don't print this list back.

- **Portfolio** — one portable collection of data and a model; the unit of work, not an
  investment holding. `wiki/concepts/portfolio.md`
- **Opportunity** — an investable option or project the optimizer chooses among and
  schedules in time. `wiki/concepts/opportunity.md`
- **Outcome** — one weighted case of an opportunity (a certain one has a single outcome;
  an uncertain one splits into P90/P50/P10). `wiki/expressions/data-considerations.md`
- **Metric** — a variable in the model: input, master data, or computed.
  `wiki/concepts/metric.md`
- **Model** — the definitional layer of a portfolio (its metrics and attribute
  definitions), not the data it runs on. `wiki/concepts/portfolio-model.md`
- **Scenario** — a single what-if case within a portfolio, solved and compared against
  others. `wiki/concepts/scenario.md`
- **Attribute** — the name of a grouping category; its populated value is a
  **characteristic**. The two are not interchangeable. `wiki/concepts/attribute.md`
- **Master data** — array input constant period-to-period, matched via attributes.
  `wiki/concepts/master-data.md`
- **Rule** — governs when and how much of each opportunity may be selected; four
  families. `wiki/concepts/rule.md`
- **Selection** — which opportunities a scenario chooses and when.
  `wiki/concepts/selection.md`
- **Optimization** — solving a scenario against an objective and its constraints.
  `wiki/concepts/optimization.md`

Cues only — never answer from this list. If the user asks what one of these means or how
it behaves, read the cited page and answer with a citation.

## Step 1 — check the connection

Call the `qpmcp` server's `ping` tool, then `whoami`.

- If both succeed → go to step 2.
- If `qpmcp` isn't available at all, or either call fails → go to step 3.

Relay any `WARNING:` from `ping` in one line, in the user's words. Don't soften it:
`ping` itself says which of the two cases it is, and one of them means file transfer is
broken until an administrator fixes the configured URL.

## Step 2 — connected: greet and orient

Report the effective user, the installation they're connected to, and what you can do,
in roughly this shape:

> Hi **j.smith** — connected to `https://portfolio.example.com/`. I can **answer how
> Portfolio works** from the official knowledge base, **work with your live data**
> (portfolios, scenarios, imports, optimization runs and their results), and **build
> validated portfolio, scenario and model files** from a description.
>
> What would you like to start with?

Use the URL `ping` reports — that's the only place you learn it, so don't guess it or
reuse `$ARGUMENTS`. If `ping` returned a WARNING about that URL, greet without it and
relay the warning instead.

Adapt the wording to the user, but keep the capabilities to a single sentence — one
short phrase each, no bullet list — and don't name the underlying skills or tools;
describe what the user gets.

If `$ARGUMENTS` held a URL and the existing connection points somewhere else, say so
in one line and offer to repoint it (step 3, last bullet).

## Step 3 — not connected: offer, don't lecture

Say what's wrong in one line, then **ask** whether they'd like to be walked through
the setup. Stop and wait for the answer. Examples:

- *"I can't reach Q Portfolio — the `qpmcp` connection isn't configured yet. Want me
  to walk you through setting it up? It takes about a minute."*
- *"Q Portfolio rejected the connection (invalid API key). Want me to walk you
  through replacing it?"*

If they say yes, follow **Setup** below. If they say no, tell them the file-authoring
capabilities (building portfolio, scenario and model files) work offline, and stop.

---

# Setup

Only for step 3, and only after the user asks for it.

`qpmcp` is **not bundled with the plugin** — it points at the user's own Portfolio
installation and carries their personal API key, so it lives in their own config at
**user scope**: the top-level `mcpServers` object in `~/.claude.json`. That file isn't
version-controlled and survives plugin updates.

**Never ask the user to paste their API key into the conversation.** Give them a
command to run themselves with the `!` prefix, so the key stays out of the transcript.

## The URL

Use `$ARGUMENTS` if the user supplied a URL. Otherwise ask for the base URL of their
Portfolio installation, e.g. `https://portfolio.example.com` — whichever address their
administrator gave them. If they don't know it, that's a question for their
administrator, not a guess.

## Write the entry

Tell the user, in this order:

1. In Portfolio, open **Account Settings** and create an **MCP API key**. Copy it —
   it's shown only once.
2. Run this in the prompt with `!` at the front, substituting the real URL and pasting
   their key over `PASTE_KEY_HERE`:

   ```
   ! claude mcp add --scope user --transport http qpmcp https://portfolio.example.com/ --header "Authorization: Bearer PASTE_KEY_HERE"
   ```

   The `--scope user` flag is what puts it in `~/.claude.json` for every project.
   Keep the trailing slash on the URL — the MCP endpoint is served at the host root.

   **If they'd rather edit the file by hand**, tell them to open `~/.claude.json` and
   add this to the top-level `mcpServers` object (alongside whatever is already
   there), then save:

   ```json
   "qpmcp": {
     "type": "http",
     "url": "https://portfolio.example.com/",
     "headers": { "Authorization": "Bearer PASTE_KEY_HERE" }
   }
   ```

   That file is large and holds other settings — add the one entry, change nothing
   else. Don't offer to edit it for them: the key would pass through this
   conversation.
3. **Restart Claude Code**, so the new server is picked up, then run `/qp-hi`
   again.

No allow rule is needed for file transfer: the links the tools mint are signed and
carry no API key.

## When it still fails

- **`qpmcp` not listed in `claude mcp list` or `/mcp`** → the entry didn't save, or
  the restart didn't happen.
- **401 / invalid API key** → the key is wrong, expired, or revoked. Mint a new one
  and redo the steps above. `claude mcp remove --scope user qpmcp` first if replacing
  it.
- **Connection refused / no response** → the URL is unreachable or the Portfolio MCP
  host isn't running. Check for a typo and the trailing slash.
- **Two `qpmcp`-ish servers, duplicate tools** → an old entry is still around at
  another scope. `claude mcp list` shows which; remove the one you don't want.

## Notes to pass on

- The key acts as **that user** — it sees exactly the portfolios their own account
  can see, and it can never act as an administrator.
- It's stored in plain text in `~/.claude.json`, like any bearer token. Treat it as a
  password: never commit it, never paste it in chat, revoke it in Account Settings if
  it leaks.
- To point at a different installation later, re-run the steps above — `claude mcp
  add` overwrites the entry at the same scope.
