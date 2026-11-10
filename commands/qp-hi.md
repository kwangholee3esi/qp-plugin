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

If `$ARGUMENTS` held a URL and the connection points somewhere else, say so in one line:
this plugin connects to one fixed Portfolio installation, so another one needs its own
connector (Setup, last section).

## Step 3 — not connected: offer, don't lecture

Say what's wrong in one line, then **ask** whether they'd like to be walked through
the setup. Stop and wait for the answer. Examples:

- *"I can't reach Q Portfolio — you haven't signed in to the `qpmcp` connection yet.
  Want me to walk you through it? It takes about a minute."*
- *"Q Portfolio turned the connection down. Want me to walk you through signing in
  again?"*

If they say yes, follow **Setup** below. If they say no, tell them the file-authoring
capabilities (building portfolio, scenario and model files) work offline, and stop.

---

# Setup

Only for step 3, and only after the user asks for it.

`qpmcp` and the knowledge base `qpwiki` **ship with the plugin**, already pointed at
the Q Portfolio installation. There is no address or key to type: the user signs in
to `qpmcp` once with their own Portfolio account, and the knowledge base needs no
sign-in. **Never ask for their password in the conversation** — they type it on the
Portfolio sign-in page, which you never see.

## How to sign in

Ask which app they're in if you can't tell.

**Claude Code** — tell them to type `/mcp`, pick qp-author's `qpmcp`, and choose
**Authenticate**. A browser opens on the Portfolio sign-in page; once they're back,
run `/qp-hi` again.

**Cowork** — open the qp-author plugin's **Connectors** tab, click **Connect** on
`qpmcp`, and sign in. Then run `/qp-hi` again.

No allow rule is needed for file transfer: the links the tools mint are signed and
carry no credential.

## When it still fails

- **Sign-in page says no, or `whoami` still fails after signing in** → their
  Portfolio account can't sign in here, or has been disabled. That's a question for
  their Portfolio administrator.
- **Connection refused / no response** → the Portfolio installation isn't reachable
  right now. Try again later; if it persists, tell their administrator.
- **Two `qpmcp` servers, duplicate tools** → an older `qpmcp` entry is still around
  (a hand-made one, a `qpmcp` connector, or `qpmcp-config.plugin`). Keep the plugin's:
  `claude mcp list` shows what's there and `claude mcp remove --scope user qpmcp`
  removes a hand-made entry; in Cowork remove the extra connector or plugin.

## Another Portfolio installation

This plugin's connection is fixed to one installation. For another one, the user adds
their own connection with an MCP API key from that installation's **Account Settings**
page, which also has a ready-made Cowork plugin and Claude Code command. Never ask them
to paste the key into the conversation.

## Notes to pass on

- The connection acts as **that user** — it sees exactly the portfolios their own
  account can see, and it can never act as an administrator.
