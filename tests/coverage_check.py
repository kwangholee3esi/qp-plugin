#!/usr/bin/env python3
"""Schema-coverage checker for QPortfolio Portable-JSON fixtures.

Walks a JSON Schema and asserts that a set of fixture JSON files, taken
together, exercise EVERY property defined in the schema and EVERY allowed
value of every enum. This turns "the fixtures cover all components and fields"
into a hard, repeatable assertion that stays honest as the (generated) schema
evolves.

Coverage model
--------------
Paths are normalised with array levels collapsed to ``[]`` so a single array
entry covers the path for all entries, e.g.::

    input_data.opportunity_outcomes[].outcomes[].metric_values[].scalar
    selection_dependency.dependencies[].timing

For enum properties, each non-null allowed value must appear at least once,
recorded as ``<path>=<value>`` (e.g. ``...dependencies[].timing=Before``).
A fixture field set to ``null`` does NOT count as coverage.

Only the standard library is used (no jsonschema dependency).

Usage:
    python coverage_check.py --schema <schema.json> <fixture.json> [<fixture.json> ...]
Exit:
    0  every path and every enum value is covered
    1  one or more paths/enum values are uncovered
    2  IO/parse error (missing file, bad JSON)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def resolve_ref(root: dict, node):
    """Follow in-document ``$ref`` chains (``#/a/b/c``) to the target node."""
    seen = 0
    while isinstance(node, dict) and "$ref" in node:
        ref = node["$ref"]
        if not ref.startswith("#/"):
            raise ValueError(f"only in-document $ref is supported, got: {ref}")
        target = root
        for part in ref[2:].split("/"):
            target = target[part]
        node = target
        seen += 1
        if seen > 50:
            raise ValueError("$ref resolution exceeded 50 hops (cycle?)")
    return node


def walk_schema(root, node, path, required: set, enum_values: dict):
    """Collect every property path and every enum's allowed (non-null) values."""
    node = resolve_ref(root, node)
    if not isinstance(node, dict):
        return
    if "enum" in node:
        enum_values[path] = {v for v in node["enum"] if v is not None}
        return  # an enum node is a leaf
    props = node.get("properties")
    if isinstance(props, dict):
        for prop, subschema in props.items():
            cp = f"{path}.{prop}" if path else prop
            required.add(cp)
            walk_schema(root, subschema, cp, required, enum_values)
    items = node.get("items")
    if isinstance(items, dict):
        walk_schema(root, items, path + "[]", required, enum_values)


def walk_value(value, path, enum_paths: set, present: set, present_enum: set):
    """Record every non-null path present in a fixture, plus enum values seen."""
    if isinstance(value, dict):
        for key, val in value.items():
            cp = f"{path}.{key}" if path else key
            if val is None:
                continue
            present.add(cp)
            if cp in enum_paths and not isinstance(val, (dict, list)):
                present_enum.add(f"{cp}={val}")
            walk_value(val, cp, enum_paths, present, present_enum)
    elif isinstance(value, list):
        for item in value:
            walk_value(item, path + "[]", enum_paths, present, present_enum)


def load_json(p: Path):
    with p.open(encoding="utf-8") as fh:
        return json.load(fh)


def main() -> int:
    ap = argparse.ArgumentParser(description="QPortfolio schema-coverage checker")
    ap.add_argument("--schema", required=True, help="path to the JSON Schema")
    ap.add_argument("fixtures", nargs="+", help="fixture JSON file(s) to measure")
    args = ap.parse_args()

    try:
        schema = load_json(Path(args.schema))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: could not read schema {args.schema}: {exc}")
        return 2

    required: set = set()
    enum_values: dict = {}
    walk_schema(schema, schema, "", required, enum_values)
    enum_paths = set(enum_values)

    present: set = set()
    present_enum: set = set()
    for fx in args.fixtures:
        try:
            data = load_json(Path(fx))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ERROR: could not read fixture {fx}: {exc}")
            return 2
        walk_value(data, "", enum_paths, present, present_enum)

    missing_paths = sorted(required - present)
    missing_enums = sorted(
        f"{path}={val}"
        for path, vals in enum_values.items()
        for val in vals
        if f"{path}={val}" not in present_enum
    )

    total_enum_vals = sum(len(v) for v in enum_values.values())
    print(f"schema:   {args.schema}")
    print(f"fixtures: {', '.join(args.fixtures)}")
    print(f"paths:    {len(required) - len(missing_paths)}/{len(required)} covered")
    print(f"enums:    {total_enum_vals - len(missing_enums)}/{total_enum_vals} values covered")

    if missing_paths:
        print(f"\nMISSING {len(missing_paths)} path(s):")
        for p in missing_paths:
            print(f"  - {p}")
    if missing_enums:
        print(f"\nMISSING {len(missing_enums)} enum value(s):")
        for e in missing_enums:
            print(f"  - {e}")

    if missing_paths or missing_enums:
        return 1
    print("\nOK: full schema coverage.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
