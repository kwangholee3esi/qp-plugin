---
description: Connect the plugin to a Q Portfolio installation, or check an existing connection
argument-hint: "[portfolio url]"
---

Set up (or verify) the `qpmcp` MCP server that the `manage-portfolio` skill uses.

`qpmcp` is **not bundled with the plugin** — it points at the user's own Portfolio
installation and carries their personal API key, so it lives in their own config at
**user scope**: the top-level `mcpServers` object in `~/.claude.json`. That file isn't
version-controlled and survives plugin updates.

**Never ask the user to paste their API key into the conversation.** Give them a
command to run themselves with the `!` prefix, so the key stays out of the transcript.

## Step 1 — is it already configured?

```
claude mcp list
```

Look for `qpmcp`. If it's listed and healthy, skip to step 4. If it's missing,
continue.

## Step 2 — the URL

Use `$ARGUMENTS` if the user supplied a URL. Otherwise ask for the base URL of their
Portfolio installation, e.g. `https://portfolio.example.com`. If they run Portfolio
locally, it's `http://localhost:5300`.

## Step 3 — write the entry

Tell the user, in this order:

1. In Portfolio, open **Account Settings** and create an **MCP API key**. Copy it —
   it's shown only once.
2. Run this in the prompt with `!` at the front, substituting the real URL from step
   2 and pasting their key over `PASTE_KEY_HERE`:

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
3. **Restart Claude Code**, so the new server is picked up.

Then stop. Don't try to verify in this session.

## Step 4 — verify

In the new session, call the `qpmcp` server's `whoami` tool and report the effective
user in one line: *"Connected as **k.holee**."*

If it fails:

- **`qpmcp` not listed in `claude mcp list` or `/mcp`** → the entry didn't save, or
  the restart didn't happen.
- **401 / invalid API key** → the key is wrong, expired, or revoked. Mint a new one
  and redo step 3. `claude mcp remove --scope user qpmcp` first if replacing it.
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
- To point at a different installation later, re-run step 3 — `claude mcp add`
  overwrites the entry at the same scope.
