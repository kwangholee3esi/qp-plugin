# QPortfolio authoring skills

Describe a portfolio, a what-if scenario, or a calculation model in plain
English, and this plugin writes a **validated Q Portfolio import file** for
you — ready to load through the product's normal import flow. It bundles five
skills plus the connection to the QP knowledge vault, so everything works after
one install.

- **Make a portfolio** — turn a description of your opportunities, their
  metrics/outcomes, and any selection rules into a portfolio file.
- **Make a scenario** — turn a what-if (e.g. "maximize NPV with capex ≤ $50MM/yr")
  into a scenario file, optionally checked against a portfolio you already have.
- **Make a model** — turn a description of your metrics and formulas (computed
  metrics, derived metrics, attributes) into a model file, with every formula
  reference and function checked before you import.
- **Ask a question** — ask how Portfolio works ("what is a soft constraint?",
  "how do I compare two scenarios?") and get an answer from the official QP
  knowledge base, with the source page cited.
- **Manage your portfolios** — connect to your own Portfolio installation and work
  with real data: see your portfolios and scenarios, load a file you just authored
  straight in, start an optimization and follow the job, read what the optimizer
  picked, edit a scenario in place (a limit, a forced opportunity, a rule), copy a
  scenario in one call and vary the copy — swapping the objective metric or flipping
  maximize/minimize, so your baseline stays put and you can compare the two — or copy a
  portfolio's calculation model into another portfolio. You can also leave feedback
  from the chat; it is saved on your Portfolio server. At the end of a session, say bye or run
  **`/qp-bye`** — it looks back over what went wrong and what could work better,
  shows you the report, and sends it only if you say yes.
  It remembers which portfolio and scenario you're working on, so you don't repeat
  yourself.

## Install

### In Claude Code

Paste these two lines:

```
/plugin marketplace add kwangholee3esi/qp-plugin
/plugin install qp-author@qp-author
```

### In Claude Cowork

Drop the packaged plugin file into a Cowork chat — Cowork recognizes it and loads
its skills for you to use:

1. Download the latest **[`qp-author.plugin`](https://github.com/kwangholee3esi/qp-plugin/raw/main/qp-author.plugin)**
   from the repo (it's rebuilt on every release). To build it yourself instead,
   zip the **contents** of this folder so `.claude-plugin/` sits at the archive
   root, and name the archive `qp-author.plugin` — use a tool that
   writes forward-slash paths (e.g. `zip -r`); Windows "Compress-Archive" writes
   backslash paths Cowork's Linux sandbox can't read.
2. In a **Cowork** chat, attach that file. It shows as a card badged **PLUGIN**,
   and the bundled skills become available in the conversation.
3. Just ask in plain language (see the example below).

The file drop loads the plugin for that **one conversation** — re-attach it in each
new Cowork chat. (Persistent, org-wide install needs an admin to add it via
Organization settings → Plugins → GitHub, with a private/internal repo.)

The QP knowledge vault is bundled with the plugin and connects automatically —
no sign-in required.

> Current Cowork desktop builds have no "add a personal marketplace by URL"
> option, so the GitHub marketplace route (used by Claude Code above) isn't
> available here — use the file drop. An org admin can instead publish it org-wide
> via Organization settings → Plugins → Add plugin → GitHub, but that path
> requires a **private/internal** repo.

Then just ask, in plain language — for example:

> Create a QPortfolio portfolio for two wells, each with an NPV and a capex metric over 3 years.

The right skill runs automatically and saves the file.

## Before you start (one-time)

- **Claude Code or Claude Cowork** — either one works.
- **Python 3** — only for **Claude Code**: the skills use it to check your file
  is valid before saving. Get Python at <https://www.python.org/downloads/>. The
  validators need the `jsonschema` package **≥ 4.18** (for Draft 2020-12); the
  skill installs/upgrades it automatically when missing or too old.
  In **Cowork** this is already provided, so there's nothing to install.
  - *On Windows with no Python:* the skills automatically fall back to a bundled
    **PowerShell** validator (Windows PowerShell 5.1+, present on every Windows
    box — nothing to install) that runs the same checks. Python stays the
    recommended path; Cowork and Linux always have Python.
- **QP knowledge vault:** served by your Portfolio installation at the same MCP
  address — no API key needed for it, but the address must be set (below).
- **Your Portfolio installation** — needed for the *Manage your portfolios* skill
  and for the knowledge vault; building and validating files works offline. You need
  two things: the **MCP address** (type it with no slash at the end)
  your administrator gave you (not the Portfolio web address), and an **MCP API
  key** you create under **Account Settings** in Portfolio — it's shown only once.

  - **Claude Code** asks for both when you install the plugin and remembers them.
    To change them later, run `/plugin configure qp-author@qp-author`, then restart.
    Your key goes to your system's secure credential store.
  - **Cowork** doesn't ask. Easiest: on the same Account Settings page, click
    **Download qpmcp-config.plugin** and attach that file to your Cowork chat
    alongside `qp-author.plugin`. It already holds your address and key — never
    share it; download a fresh one when the key expires.
  - **claude.ai** (or Cowork without that file) doesn't ask. Add the connection once under **Customize >
    Connectors > Add custom connector** (on Team or Enterprise plans an Owner adds it
    for everyone), plus a second one named `qpwiki` at the same address followed by
    `/wiki`, with no sign-in, for the knowledge vault.

  Run **`/qp-hi`** — it checks the connection and, if it isn't set up, walks you
  through it (your key never gets pasted into the chat).

  The key acts as **you** — it sees exactly the portfolios your own account can see,
  and it can never act as an administrator. Ask "who am I connected as" to check it's
  working.

## Updates

You'll get improvements automatically — no need to reinstall.
