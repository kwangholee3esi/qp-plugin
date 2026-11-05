---
name: qp-feedback
description: >-
  Wraps up a Q Portfolio working session — looks back over the conversation for
  what went wrong and what could work better, shows the user a short report, and
  sends it as feedback to the Portfolio team only after the user approves. Use
  when the user wants to finish or end their session — "bye", "that's all",
  "I'm done", "let's wrap up", "end the session", "thanks, that's it for today"
  — or runs /qp-bye or asks to send feedback about the session.
argument-hint: "[anything you want to add]"
---

Wrap up the session. Look back over **this conversation** — everything done with Q
Portfolio, its skills and its tools — and write an honest report of what got in the way
and what would have made it easier. Then show it to the user and **ask for their
approval** before sending it with the `qpmcp` server's `feedback_send` tool. End with a
short goodbye.

You can only see the current conversation. If it holds no Q Portfolio work, skip the
report and just say goodbye in one line.

## Step 1 — find the trouble

Go through the session in order. Note each place where something didn't go smoothly:

- **A tool call failed or was refused** — what was asked, the error, and what finally worked
  (or that nothing did).
- **You had to guess** — a skill or tool description left a decision open, two pieces of
  guidance pointed different ways, or you weren't sure what a word meant in Portfolio.
- **The user corrected you** — they pushed back, re-asked, or fixed something you made.
  Quote their words.
- **It took the long way** — many calls, retries or workarounds for something that should
  be one step.
- **Something was missing** — the user wanted something no skill or tool could do.
- **Something worked well** — worth keeping; one line each, only the stand-outs.

Facts only. Don't invent trouble that didn't happen, and don't blame the user. If the
session went smoothly, say that — a short report is a good report.

`$ARGUMENTS`, if given, is the user's own note — put it first, in their words.

## Step 2 — write the report

Plain text, short sections:

```
Session feedback — <one line on what the session was about>

User note: <$ARGUMENTS, or leave this line out>

1. <short title>
   What happened: <the facts, with the exact error text if short>
   Why it was hard: <what was missing, unclear or wrong>
   Suggestion: <one concrete change — to a skill, a tool, or Portfolio itself>

2. ...

Worked well: <one line, or leave this line out>
```

Most important first. Keep each point to a few lines.

**Leave out** API keys, passwords, signed links, and full file contents. Name
portfolios, scenarios and metrics when it helps — the report is stored on the user's own
Portfolio server — but don't paste data values unless they're needed to explain the problem.

## Step 3 — show, ask for approval, then send

Show the report to the user and ask for approval: *"May I send this to the Portfolio team
as feedback? It's saved on your Portfolio server with your name. Say yes, no, or tell me
what to change."* Stop and wait for the answer.

- **Yes** → call `feedback_send` with the report as written, then say it was sent.
- **Changes** → make them, show it again, ask again.
- **No** → don't send. Tell them they can copy the text above if they want to keep it.
- **`qpmcp` isn't connected** or the call fails → say so in one line, leave the report on
  screen for them to copy, and suggest `/qp-hi` to check the connection.

Never send without a clear yes. Silence, "maybe" or a change request is not a yes.

Then say goodbye in one line.
