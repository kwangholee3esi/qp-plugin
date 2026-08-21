# Skill feedback — knapsack camping session (2026-08-05)

Agent thought-process report for the `qp-author` skills, from the
session that produced `knapsack-camping-model.json` + `knapsack-camping-portfolio.json`.
Format per section: what I had to decide → what the skill gave me → what I did → suggested improvement.

## 1. Routing and ordering across skills

**Decision:** "portfolio with model" → which skill first?
**What the skills gave me:** Nothing. Each skill is self-contained; neither
mentions the other (except scenario's optional cross-validation against a
portfolio file). Model REFERENCE says "get names from the user's actual
portfolio wherever possible" but there was no portfolio yet.
**What I did:** Model first (it defines the vocabulary), then portfolio, keeping
names/units in sync by memory within one conversation.
**Improvement:** A short "companion files" note in both skills: recommended
generation order for a from-scratch set (model → portfolio → scenario), and a
reminder that metric names + units must match across the pair. Even better: a
`--companion <model.json>` flag on the portfolio validator (mirroring what the
scenario skill already does) that checks metric-name and unit agreement. That
join is the stated cardinal failure mode, and today no tool checks it.

## 2. Mapping a non-O&G problem onto the domain

**Decision:** foods = opportunities, value = time series, weight/cost = one-time.
**What the skills gave me:** Portfolio EXAMPLES.md §5 is literally
"knapsack-style" — this was the single most useful artifact in the whole
session; I lifted `integer_only` + `total_maximum: 1` + `time_period_maxima: [1]`
straight from it. The model skill has no equivalent non-O&G example.
**Improvement:** Add the *model side* of example 5 to the model skill's
EXAMPLES.md (see §6 below for why the missing model half is actively dangerous).

## 3. Derived vs explicit computed totals (the user caught this)

**Decision:** `Trip Value = Total(${Daily Value})` as explicit computed metrics,
vs `derived: ["Total"]`.
**What the skills gave me:** Conflicting-strength guidance. REFERENCE: "Prefer a
derived metric over hand-writing …". EXAMPLES §1: "write an explicit expression
only when the user wants a metric of their own naming." Neither states the
concrete tie-breakers.
**What I did:** Explicit metrics, for (a) scenario-dropdown-friendly names
(`Trip Value` vs `Daily Value#Total`) and (b) unit correctness — a derived
metric inherits the origin's unit, so `Daily Value#Total` would be labelled
`pts/day`, wrong for a whole-trip total. The user immediately asked why I
didn't use `derived`, i.e. the guidance as written points the other way.
**Improvement:** Make the rule decision-procedure-shaped: "Default to `derived`.
Go explicit only when: the metric will be referenced by name in a scenario
objective/limit and the user cares about the name, OR the total's unit differs
from the origin's (derived inherits the origin unit label)." The unit-inheritance
consequence is documented nowhere and is the strongest real argument.

## 4. The "one-time cost at period 0" pattern

**Decision:** Weight/Cost as `[w, 0, 0]` series, or `scalar: true` with one value?
**What the skills gave me:** REFERENCE says omit `scalar` unless the user gives
it — so I zero-padded a series. Neither skill discusses the extremely common
pattern "a value that occurs once at decision time" (capex-like), even though
every knapsack/capex problem has one.
**Improvement:** One paragraph in both REFERENCEs: when a quantity is one-off,
either (a) scalar metric in model + single-value in data, or (b) period-0 series
with zero padding — and which one the calculators/optimizer prefer. I guessed (b);
I don't actually know if (a) behaves identically under `Total()`.

## 5. Re-import "omission clears" warning on a brand-new file

**What the skills gave me:** The model skill hammers "omitted optional property
CLEARS the stored value on re-import." Correct and important — but for a
from-scratch file it's irrelevant, and it pushed me to defensively write
descriptions on every metric.
**Improvement:** One clause: "for a brand-new model there is nothing to clear —
omit freely." Saves both tokens and defensive bloat in generated files.

## 6. Example 5's data shape silently conflicts with a Total() model

**Observation, not a decision I faced:** portfolio EXAMPLES §5 gives Candy
`Capex: [10, 10, 10]` — a *flat* series. If the (unshown) companion model
computes `Total(${Capex})`, the knapsack "weight" is silently 30, not 10. My
files avoid this only because I authored both halves and used `[w, 0, 0]`.
**Improvement:** Examples that demonstrate a data shape should show (or at least
name) the model formula they pair with. A matched model+portfolio example pair
would close the biggest blind spot: each validator passes files that are
individually clean but jointly wrong, and nothing in either skill even warns
that this class of error exists.

## 7. Final-file naming: "ask the user" vs autonomous flow

**What the skills gave me:** Step 5: "write the final `<name>.json` (ask the
user for the path/name if not given)."
**What I did:** Didn't ask — defaulted to `knapsack-camping-{model,portfolio}.json`
in the project root. Asking would have blocked an otherwise fully-autonomous run.
**Improvement:** Replace "ask" with a default convention: "derive
`<kebab-case-topic>-<kind>.json` in the working directory unless the user gave a
path." Reserve asking for overwrite conflicts.

## 8. Things that worked well (keep)

- **Validator-first loop.** Both files passed on pass 1; the JSON output shape
  (`summary` / `json_path` / `hint`) is exactly what a repair loop needs. The
  scratch-path-then-copy discipline is cheap and good.
- **"Input periods vs planning horizon" section.** This trap documentation is
  excellent — it is the only reason I did not pad `time_period_maxima` to `[1,1,1]`.
  The repetition (REFERENCE + workflow step 3 + example 5 annotation) is justified.
- **Closed 26-function table with arities.** Removed all temptation to reach for
  `ROUND`/`SUM`-style Excel names.
- **"Ask vs default" split.** I asked the user nothing and still produced valid
  files; the defaults were all inferable. This is the right interrogation budget.
- **PowerShell fallback.** Not needed (Python present) but clearly specified;
  no ambiguity about when to switch.

## 9. Minor

- `qp_version: 4.5` is cargo-culted from the examples; neither skill says how to
  determine the real target version. A line ("use 4.5 unless the user's product
  version is known") would make the copying deliberate.
- The qpwiki vault escape hatch was never needed for this problem — fine, but it
  means non-O&G sessions exercise zero grounding; the examples carry all the load
  (which is why §2/§6 matter).
