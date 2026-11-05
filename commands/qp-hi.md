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
  investment holding. `concepts/portfolio.md`
- **Opportunity** — an investable option or project the optimizer chooses among and
  schedules in time. `concepts/opportunity.md`
- **Outcome** — one weighted case of an opportunity (a certain one has a single outcome;
  an uncertain one splits into P90/P50/P10). `expressions/data-considerations.md`
- **Metric** — a variable in the model: input, master data, or computed.
  `concepts/metric.md`
- **Model** — the definitional layer of a portfolio (its metrics and attribute
  definitions), not the data it runs on. `concepts/portfolio-model.md`
- **Scenario** — a single what-if case within a portfolio, solved and compared against
  others. `concepts/scenario.md`
- **Attribute** — the name of a grouping category; its populated value is a
  **characteristic**. The two are not interchangeable. `concepts/attribute.md`
- **Master data** — array input constant period-to-period, matched via attributes.
  `concepts/master-data.md`
- **Rule** — governs when and how much of each opportunity may be selected; four
  families. `concepts/rule.md`
- **Selection** — which opportunities a scenario chooses and when.
  `concepts/selection.md`
- **Optimization** — solving a scenario against an objective and its constraints.
  `concepts/optimization.md`

Cues only — never answer from this list. If the user asks what one of these means or how
it behaves, read the cited page and answer with a citation.

## Step 1 — check the connection

Call the `qpmcp` server's `ping` tool, then `whoami`.

- If both succeed → step 1b.
- If `qpmcp` isn't available at all, or either call fails → go to step 3.

Relay every `WARNING:` from `ping` in one line, in the user's words — there can be more
than one. Don't soften it; `ping` itself says what each one means.

## Step 1b — check both URLs from your own shell

Once per session: your shell is what uploads and downloads go through, and `ping` cannot
test it for you. Curl both URLs from `ping`'s reply:

- `curl -s <mcp= URL>/ping` answers `pong …`.
- `curl -s <server= URL>`, exactly as given (with its trailing slash), answers
  `Aucerna Portfolio …` naming the build and tenant.

No `WARNING` from `ping` does not mean `server=` is reachable; only this curl tells you.
One timeout is not proof: try once more before calling an address unreachable. A curl you
were not allowed to run tells you nothing — carry on and report no outage.

**Both reachable → go straight to step 2 and say nothing about it.** A working connection
is not news.

If only `mcp=` is unreachable from your shell, say nothing: tool calls don't go through your
shell, and uploads and downloads go to `server=`.

If `server=` is genuinely unreachable from your shell, still go to step 2 and greet normally,
but add one plain line, and hand every curl you are given later — uploads, downloads — to the
user to run, e.g.:

> One thing: I can't reach the Portfolio server at `<server= URL>` from here, so **I'll
> hand you the upload and download commands to run yourself.** Reading your data still
> works.

## Step 2 — connected: greet and orient

Report the effective user, the installation they're connected to, and what you can do,
in roughly this shape:

> Hi **j.smith** — connected to `https://portfolio-mcp.example.com`. I can **answer how
> Portfolio works** from the official knowledge base, **work with your live data**
> (portfolios, scenarios, imports, optimization runs and their results), and **build
> validated portfolio, scenario and model files** from a description.
>
> What would you like to start with? (When you're done, say bye or run `/qp-bye` —
> I'll sum up anything that got in the way and, if you agree, send it to the
> Portfolio team as feedback.)

Use `ping`'s `mcp=` URL — that's the installation they're connected to, and the only
place you learn it, so don't guess it or reuse `$ARGUMENTS`. (`server=` is a different
address; never greet with it.) If `mcp=` reads `(unset)` or `ping` warned about it, greet
without a URL and relay the warning instead.

Adapt the wording to the user, but keep the capabilities to a single sentence — one
short phrase each, no bullet list — and don't name the underlying skills or tools;
describe what the user gets. The one exception is `/qp-bye`: always end with the short
note about it, so the user knows how to wrap up and give feedback.

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

`qpmcp` **ships with the plugin**, but its address and API key are the user's own:
the plugin asks for them once and saves them. The address is kept in their Claude
settings, the key in their system's secure credential store. Both survive plugin
updates.

**Never ask the user to paste their API key into the conversation.** They type it into
the plugin's own settings form, which masks it and never shows it to you.

## What they need

1. **The Q Portfolio MCP address** their administrator gave them, e.g.
   `https://portfolio-mcp.example.com` — not the address of the Portfolio web page they
   log in to, which is a different application. If they don't know it, that's a
   question for their administrator, not a guess. Type it with **no slash at the
   end** — the plugin adds `/wiki` to it for the knowledge base.
2. **An MCP API key**: in Portfolio, open **Account Settings** and create one. Copy
   it — it's shown only once.

## Where to enter them

Ask which app they're in if you can't tell.

**Claude Code** — tell them to type this here (it opens the plugin's settings form;
the values never reach this conversation):

```
/plugin configure qp-author@qp-author
```

Fill in both fields, then **restart Claude Code** and run `/qp-hi` again. The same
command changes the address or replaces the key later.

**Cowork** — the easiest way is a personal connection plugin:

1. In Portfolio, open **Account Settings**, create an MCP API key, and click
   **Download qpmcp-config.plugin** on the same page. The file already holds their
   address and key, so there's nothing to type.
2. Attach that file to the Cowork chat alongside `qp-author.plugin`, the same way.
3. Run `/qp-hi` again.

The file contains their key: tell them never to share it. When the key expires or is
replaced, they download a fresh file the same way.

**claude.ai, or Cowork without the file** — these apps don't show the plugin's
settings form, so the user adds the connection once as a connector:

1. Open **Customize > Connectors > Add custom connector**. (On a Team or Enterprise
   plan only an Owner can add it — under **Organization settings > Connectors** — and
   members then just click **Connect**.)
2. Name it `qpmcp` and paste the MCP address.
3. Choose **No sign-in**, then under **Request headers** add `authorization` with the
   value `Bearer ` followed by their key (keep the space). If there's no **Request
   headers** section, their organization doesn't have that option yet — that's a
   question for their administrator.
4. Add a second connector the same way for the knowledge base: name it `qpwiki`,
   paste the MCP address followed by `/wiki`, choose **No sign-in**, and add no
   request headers — the knowledge base needs no key.
5. Start a new chat and run `/qp-hi` again.

No allow rule is needed for file transfer: the links the tools mint are signed and
carry no API key.

## When it still fails

- **`qpmcp` not listed in `/mcp`** → the form was left empty, or the restart didn't
  happen. Run `/plugin configure qp-author@qp-author` again.
- **401 / invalid API key** → the key is wrong, expired, or revoked. Mint a new one
  and enter it again the same way — in Cowork, download a fresh `qpmcp-config.plugin`.
- **Connection refused / no response** → the address is unreachable or the Portfolio
  MCP host isn't running. Check for a typo, and that there's no slash at the end.
- **Two `qpmcp` servers, duplicate tools** → an older hand-made entry is still around,
  from before the plugin asked for these settings, or a `qpmcp` connector added in
  claude.ai is showing up in Claude Code too, or in Cowork both a `qpmcp` connector and
  `qpmcp-config.plugin` are present. Keep one: `claude mcp remove --scope
  user qpmcp` removes the old hand-made entry; `claude mcp list` shows what's there.
  In Cowork, remove either the `qpmcp` connector (**Customize > Connectors**) or
  `qpmcp-config.plugin`.

## Notes to pass on

- The key acts as **that user** — it sees exactly the portfolios their own account
  can see, and it can never act as an administrator.
- Treat it as a password: never commit it, never paste it in chat, revoke it in
  Account Settings if it leaks.
