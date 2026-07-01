#!/usr/bin/env python3
"""Refresh the bundled scenario.schema.json from the committed server copy.

The schema is GENERATED on the server side from Esi.Sp.Portable/Types/*.cs (and
their [Description] attributes); never hand-edit either copy. Regenerate the
server schema first when the types change:

    UPDATE_PORTABLE_SCHEMAS=1 dotnet test Esi.Sp.Portable.Tests \
        --filter Committed_schema_matches_generator_output

(see server/Esi.Sp.Portable/Schemas/README.md), THEN run this script to copy the
fresh schema into the skill and record its provenance in .schema-sync.json.

Usage:
  python sync_schema.py [--server-root PATH]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

SERVER_SCHEMA_REL = ("server", "Esi.Sp.Portable", "Schemas", "scenario.schema.json")
SKILL_DIR = Path(__file__).resolve().parent.parent
BUNDLED = SKILL_DIR / "schemas" / "scenario.schema.json"
PROVENANCE = SKILL_DIR / ".schema-sync.json"


def find_server_schema(server_root: str | None) -> Path | None:
    if server_root:
        cand = Path(server_root).joinpath(*SERVER_SCHEMA_REL)
        return cand if cand.is_file() else None
    for base in [SKILL_DIR, *SKILL_DIR.parents]:
        cand = base.joinpath(*SERVER_SCHEMA_REL)
        if cand.is_file():
            return cand
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Sync the bundled scenario schema.")
    ap.add_argument("--server-root", help="path to a cp-portfolio checkout root")
    args = ap.parse_args(argv)

    source = find_server_schema(args.server_root)
    if source is None:
        print("ERROR: could not locate server/Esi.Sp.Portable/Schemas/scenario.schema.json.\n"
              "Run inside a cp-portfolio checkout or pass --server-root.", file=sys.stderr)
        return 1

    raw = source.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    try:
        qp_version = (json.loads(raw).get("examples") or [{}])[0] \
            .get("metadata", {}).get("qp_version")
    except (ValueError, AttributeError, IndexError):
        qp_version = None

    BUNDLED.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, BUNDLED)

    provenance = {
        "source_path": str(source),
        "sha256": sha,
        "qp_version": qp_version,
        # synced_utc intentionally omitted; stamp externally if needed.
    }
    PROVENANCE.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")

    print(f"Synced schema from: {source}")
    print(f"  -> {BUNDLED}")
    print(f"  sha256={sha}  qp_version={qp_version}")
    print("Reminder: the server schema is generated; regenerate it (dotnet test with "
          "UPDATE_PORTABLE_SCHEMAS=1) before syncing if the C# types changed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
