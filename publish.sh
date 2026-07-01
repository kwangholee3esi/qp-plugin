#!/usr/bin/env bash
#
# Publish this plugin to its public marketplace repo as a clean single-commit
# snapshot. We deliberately do NOT use `git subtree` (it walks the monorepo's
# entire history — slow — and would expose internal commit history publicly).
# Each publish replaces the public `main` with one fresh commit containing only
# the committed contents of the plugin folder.
#
# Usage:  bash agent/qp-portfolio-authoring/publish.sh
# Run it AFTER committing your plugin changes (it publishes committed HEAD).
# Requires push access to the target repo for the current git credentials.

set -euo pipefail

REPO_URL="https://github.com/kwangholee3esi/qp-plugin.git"
PREFIX="agent/qp-portfolio-authoring"
AUTHOR_NAME="kwangholee3esi"
AUTHOR_EMAIL="kholee3esi@gmail.com"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# Publish the committed HEAD state — refuse if the plugin folder is dirty.
if ! git diff --quiet -- "$PREFIX" || ! git diff --cached --quiet -- "$PREFIX"; then
  echo "ERROR: uncommitted changes under $PREFIX — commit them first (publish uses committed HEAD)." >&2
  exit 1
fi

SRC_SHA="$(git rev-parse --short HEAD)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Snapshot only the tracked files under the prefix; the prefix becomes repo root.
git archive "HEAD:$PREFIX" | tar -x -C "$WORK"

cd "$WORK"

# Build the installable bundle so the public repo always carries a ready-to-drop
# file for Cowork (drag onto a Cowork chat to load the skills). It's a plain zip
# of the snapshot, renamed `.plugin`. Use Python's zipfile (not PowerShell
# Compress-Archive, which writes backslash paths that Cowork's Linux sandbox
# can't read); `zip` isn't available in Git Bash here. Exclude tooling files.
PLUGIN_FILE="qp-portfolio-authoring.plugin"
python - "$PLUGIN_FILE" <<'PY'
import os, sys, shutil, tempfile, zipfile
out = sys.argv[1]
skip_files = {"publish.sh"}
skip_dirs = {".git"}
# Build into the system temp dir, NOT the tree being zipped — otherwise os.walk
# would pick up the half-written archive and embed it in itself.
fd, tmp = tempfile.mkstemp(suffix=".zip")
os.close(fd)
with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for f in files:
            if f in skip_files:
                continue
            full = os.path.join(root, f)
            arc = os.path.relpath(full, ".").replace(os.sep, "/")
            z.write(full, arc)
shutil.move(tmp, out)
print("built", out)
PY

git init -q -b main
git config user.name "$AUTHOR_NAME"
git config user.email "$AUTHOR_EMAIL"
git add .
git commit -q -m "Publish qp-portfolio-authoring plugin (source $SRC_SHA)"
git remote add origin "$REPO_URL"
git push -f -u origin main

echo "Published $PREFIX @ $SRC_SHA -> $REPO_URL (main)"
