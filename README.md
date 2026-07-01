# QPortfolio authoring skills

Describe a portfolio or a what-if scenario in plain English, and this plugin
writes a **validated Q Portfolio import file** for you — ready to load through
the product's normal import flow. It bundles two skills plus the connection to
the QP knowledge vault, so everything works after one install.

- **Make a portfolio** — turn a description of your opportunities, their
  metrics/outcomes, and any selection rules into a portfolio file.
- **Make a scenario** — turn a what-if (e.g. "maximize NPV with capex ≤ $50MM/yr")
  into a scenario file, optionally checked against a portfolio you already have.

## Install

### In Claude Code

Paste these two lines:

```
/plugin marketplace add kwangholee3esi/qp-plugin
/plugin install qp-portfolio-authoring@qp-portfolio-authoring
```

### In Claude Cowork

Drop the packaged plugin file into a Cowork chat — Cowork recognizes it and loads
its skills for you to use:

1. Download the latest **[`qp-portfolio-authoring.plugin`](https://github.com/kwangholee3esi/qp-plugin/raw/main/qp-portfolio-authoring.plugin)**
   from the repo (it's rebuilt on every release). To build it yourself instead,
   zip the **contents** of this folder so `.claude-plugin/` sits at the archive
   root, and name the archive `qp-portfolio-authoring.plugin` — use a tool that
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

## Updates

You'll get improvements automatically — no need to reinstall.
