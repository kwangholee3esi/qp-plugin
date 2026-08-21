# QPortfolio authoring skills

Describe a portfolio, a what-if scenario, or a calculation model in plain
English, and this plugin writes a **validated Q Portfolio import file** for
you — ready to load through the product's normal import flow. It bundles three
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
  picked, copy a scenario into a variant and compare the two, or copy a portfolio's
  calculation model into another portfolio. It remembers which
  portfolio and scenario you're working on, so you don't repeat yourself.

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
- **QP knowledge vault:** bundled with the plugin and available automatically —
  no sign-in or setup required.
- **Your Portfolio installation** — needed only for the *Manage your portfolios*
  skill; everything else works offline. This connection is **not bundled** with the
  plugin, because it points at your installation and carries your personal key.

  Run **`/qp-connect`** and it walks you through it (your key never gets pasted into
  the chat). By hand:

  1. In Portfolio, go to **Account Settings** and create an **MCP API key**. Copy it
     — it's shown only once.
  2. Add it to your own Claude Code config, then restart Claude Code:

     ```
     claude mcp add --scope user --transport http qpmcp https://portfolio.example.com/ --header "Authorization: Bearer qpk_your_key_here"
     ```

     Or open `~/.claude.json` and add one entry to the top-level `mcpServers` object:

     ```json
     "qpmcp": {
       "type": "http",
       "url": "https://portfolio.example.com/",
       "headers": { "Authorization": "Bearer qpk_your_key_here" }
     }
     ```

     Keep the trailing slash. Running Portfolio locally? Use `http://localhost:5300/`.

  Your key lives in your own config file, so a plugin update never overwrites it, and
  it's never in version control. It acts as **you** — it sees exactly the portfolios
  your own account can see, and it can never act as an administrator. Ask "who am I
  connected as" to check it's working.

## Updates

You'll get improvements automatically — no need to reinstall.
