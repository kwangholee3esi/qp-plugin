#!/usr/bin/env python3
"""Validate a QPortfolio Portable JSON *model* file.

Two layers of checking:
  1. JSON Schema (Draft 2020-12) against model.schema.json.
  2. Semantic rules the schema describes in prose but cannot express: metric
     naming (case-insensitive uniqueness, reserved "#<Type>" derived names),
     type/expression consistency, level/group_by/criteria interactions, and a
     tokenizer-level check of every formula (${...} references resolve inside
     the file, function names come from the closed 26-name set, argument
     counts match). Full grammar/type validation stays with the server
     importer; this catches the realistic authoring mistakes before import.

Exit codes:
  0  valid   - no schema errors and no HARD semantic errors (warnings allowed)
  1  invalid - >=1 schema error and/or HARD semantic error
  2  io/parse error - file missing/unreadable, not JSON, or contains NaN/Infinity
  3  environment error - `jsonschema` not installed, or no schema found

Usage:
  python validate_model.py <file.json> [--schema PATH]
                           [--format json|text] [--strict-nulls]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ERROR = "error"
WARNING = "warning"

# Relative path of the committed schema inside a cp-portfolio checkout.
SERVER_SCHEMA_REL = ("server", "Esi.Sp.Portable", "Schemas", "model.schema.json")
EXPECTED_FILE_TYPE = "QPortfolio Model"

# The ten derivation types (lowercase). Mirrors the `derived` enum in the
# schema and MetricFunctions.cs (last-'#' suffix match, case-insensitive).
DERIVED_TYPES = {
    "pt", "disc", "inf", "cumsum", "cumsumdisc", "cumsuminf",
    "total", "totaldisc", "totalinf", "maxat",
}

# The closed set of 26 expression functions with (min_args, max_args);
# max_args None = unbounded. Source of truth: server
# Esi.Sp.Parsing/Converter/FunctionDef.cs — keep in sync when it changes.
FUNCTIONS = {
    "getmetricvalue": (1, 2),
    "getdiscounted": (1, 2),
    "getinflated": (1, 2),
    "getcumulative": (1, 3),
    "getcumulativeinflated": (1, 3),
    "getmaxacrosstime": (1, 3),
    "getirr": (1, 3),
    "getcumulativediscounted": (1, 4),
    "getcurrenttime": (0, 0),
    "getattributevalue": (1, 1),
    "sum": (1, None),
    "abs": (1, 1),
    "min": (2, 2),
    "max": (2, 2),
    "if": (3, 3),
    "npv": (2, None),
    "pt": (1, 1),
    "disc": (1, 1),
    "inf": (1, 1),
    "cumsum": (1, 1),
    "cumsumdisc": (1, 1),
    "cumsuminf": (1, 1),
    "total": (1, 1),
    "totaldisc": (1, 1),
    "totalinf": (1, 1),
    "maxat": (1, 1),
}


# --------------------------------------------------------------------------- #
# Schema discovery
# --------------------------------------------------------------------------- #
def _walk_up_for_server_schema(start: Path) -> Path | None:
    """From `start`, walk up looking for server/Esi.Sp.Portable/Schemas/...."""
    for base in [start, *start.parents]:
        candidate = base.joinpath(*SERVER_SCHEMA_REL)
        if candidate.is_file():
            return candidate
    return None


def discover_schema(explicit: str | None, target: Path) -> tuple[Path | None, str]:
    """Return (path, source). Prefer an in-repo server copy over the bundled one."""
    if explicit:
        return Path(explicit), "explicit"

    for start in (target.resolve().parent, Path.cwd()):
        found = _walk_up_for_server_schema(start)
        if found:
            return found, "server-in-repo"

    bundled = Path(__file__).resolve().parent.parent / "schemas" / "model.schema.json"
    if bundled.is_file():
        return bundled, "bundled"
    return None, "none"


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


# --------------------------------------------------------------------------- #
# Small finding helper
# --------------------------------------------------------------------------- #
def finding(severity, check, json_path, message, offending_value=None, hint=None):
    return {
        "severity": severity,
        "check": check,
        "json_path": json_path,
        "message": message,
        "offending_value": offending_value,
        "hint": hint,
    }


# --------------------------------------------------------------------------- #
# Custom `uniqueKeys` keyword (JsonSchema.Net.ArrayExt parity)
#
# The generated schema declares per-array uniqueness with `uniqueKeys`: a list
# of RFC-6901 JSON Pointers into each item (e.g. ["/metric_name"]). It is NOT
# part of Draft 2020-12, so jsonschema ignores it unless we register a
# handler. The server enforces it the same way (PortableSchemaValidator swaps
# in the array-ext meta-schema); we extend the validator instead so these land
# in the normal schema-error stream.
# --------------------------------------------------------------------------- #
def _resolve_pointer(item, pointer):
    """Resolve an RFC-6901 pointer against one array item; return a hashable key.

    A missing field yields a constant sentinel (two items both missing the key
    collide, which a `required` error already covers). Object/array targets are
    canonicalized so they remain hashable and comparable."""
    cur = item
    for token in pointer.split("/")[1:]:
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(cur, dict) and token in cur:
            cur = cur[token]
        else:
            return ("__missing__", pointer)
    return json.dumps(cur, sort_keys=True) if isinstance(cur, (dict, list)) else cur


def _make_validator(Draft202012Validator):
    """Return a validator class that also enforces the custom `uniqueKeys`."""
    from jsonschema.exceptions import ValidationError
    from jsonschema.validators import extend

    def unique_keys(validator, key_pointers, instance, schema):
        if not isinstance(instance, list) or not isinstance(key_pointers, list):
            return  # null/non-array -> no-op (mirrors the server stripping nulls)
        seen = {}
        for idx, item in enumerate(instance):
            key = tuple(_resolve_pointer(item, p) for p in key_pointers)
            if key in seen:
                yield ValidationError(
                    f"array items must be unique by {key_pointers}: "
                    f"index {idx} duplicates index {seen[key]}")
            else:
                seen[key] = idx

    return extend(Draft202012Validator, {"uniqueKeys": unique_keys})


# --------------------------------------------------------------------------- #
# Name handling (NormalName + CaseIgnoreName parity)
# --------------------------------------------------------------------------- #
def _norm_name(s):
    """Tabs/newlines/CRs become spaces, then trim (mirrors NormalName.cs)."""
    return re.sub(r"[\t\r\n]", " ", s).strip()


def _name_key(s):
    """Comparison key: normalized + lowercased (metric names are case-insensitive)."""
    return _norm_name(s).lower()


def _derived_suffix(name):
    """Return the derivation type after the LAST '#', or None (case-insensitive)."""
    norm = _norm_name(name)
    if "#" not in norm:
        return None
    suffix = norm.rpartition("#")[2]
    return suffix if suffix.lower() in DERIVED_TYPES else None


# --------------------------------------------------------------------------- #
# Formula tokenizer (depth (b): references, function names, argument counts).
# Full grammar/type validation stays with the server importer.
# --------------------------------------------------------------------------- #
_NUMBER_RE = re.compile(r"\d+(\.\d+)?([eE][+-]?\d+)?")
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_ATTR_CALL_RE = re.compile(r"(?i)getattributevalue\(\s*\$\{([^}]*)\}\s*\)")
_REF_RE = re.compile(r"\$\{([^}]*)\}")
_UNSIGNED_EXP_RE = re.compile(r"\d+(\.\d+)?[eE]\d")
# Non-linearity signals (conservative): non-linear functions, and a
# product/quotient of two metric references (linear only when one side is
# master data). Used for the derived-metric guidance warning.
_NONLINEAR_CALL_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_])(if|min|max|abs|getirr|getmaxacrosstime|maxat)\(")
_REF_PRODUCT_RE = re.compile(r"\$\{([^}]*)\}\s*[*/]\s*(?=\$\{([^}]*)\})")


def _blank_strings(src):
    """Blank out double-quoted string literals ("" escapes a quote).

    Returns (sanitized, unterminated); on an unterminated literal the rest of
    the string is dropped."""
    chars = []
    i = 0
    unterminated = False
    while i < len(src):
        if src[i] == '"':
            j = i + 1
            closed = False
            while j < len(src):
                if src[j] == '"':
                    if j + 1 < len(src) and src[j + 1] == '"':
                        j += 2
                        continue
                    closed = True
                    break
                j += 1
            if not closed:
                unterminated = True
                break
            chars.append("1")
            i = j + 1
        else:
            chars.append(src[i])
            i += 1
    return "".join(chars), unterminated


def _ref_md_key(raw):
    """Comparison key of a reference for master-data lookup: a derived
    reference resolves to its origin metric."""
    norm = _norm_name(raw)
    if _derived_suffix(raw) is not None:
        return norm.rpartition("#")[0].lower()
    return norm.lower()


def _looks_nonlinear(src, masterdata_keys):
    """Conservative heuristic: does this formula look non-linear?

    Linear = only +/- and multiplication/division by constants or master-data
    metrics. Flags: '^', If/Min/Max/Abs/GetIRR/GetMaxAcrossTime/MaxAT calls,
    or a product/quotient of two non-master-data metric references."""
    san, _ = _blank_strings(src)
    if "^" in san:
        return True
    if _NONLINEAR_CALL_RE.search(san):
        return True
    for m in _REF_PRODUCT_RE.finditer(san):
        if (_ref_md_key(m.group(1)) not in masterdata_keys
                and _ref_md_key(m.group(2)) not in masterdata_keys):
            return True
    return False


def _arity_desc(mn, mx):
    if mx == mn:
        return f"exactly {mn}"
    if mx is None:
        return f"at least {mn}"
    return f"{mn} to {mx}"


def _check_formula(src, path, declared_metrics, attrs_declared, out):
    """Tokenize one formula string and emit findings in a fixed phase order.

    Phases (mirrored 1:1 by validate_model.ps1 — keep in lockstep):
      1 unterminated string literal   4 unclosed ${...}
      2 macro FlagUpToMax             5 unsigned exponent (warn)
      3 attribute refs (warn) then    6 scan: bare identifiers, unknown
        metric/derived refs             functions, argument counts
                                      7 unbalanced parentheses
                                      8 '&'/'%' discarded (warn)
                                      9 GetIRR vs optimization (warn)
    """
    # Phase 1: blank out string literals ("" escapes a quote).
    san, unterminated = _blank_strings(src)
    if unterminated:
        out.append(finding(
            ERROR, "formula.unbalanced", path,
            "unterminated string literal", src,
            "Balance quotes, braces and parentheses."))

    # Phase 2: macros are Excel-import only.
    if re.search(r"(?i)flaguptomax", san):
        out.append(finding(
            ERROR, "formula.macro_unsupported", path,
            "macro function FlagUpToMax is not supported in JSON model files", src,
            "Break the macro into explicit metrics/expressions instead."))

    # Phase 3: GetAttributeValue(${...}) resolves against attributes; every
    # remaining ${...} is a metric reference (rewrite order per the importer).
    for m in _ATTR_CALL_RE.finditer(san):
        attr = m.group(1)
        if attrs_declared is not None and _name_key(attr) not in attrs_declared:
            out.append(finding(
                WARNING, "formula.attr_undeclared", path,
                f"GetAttributeValue references attribute '{attr}' not declared in "
                "this file's attributes (the importer silently creates it)", attr,
                "Declare the attribute or fix the name."))
    san = _ATTR_CALL_RE.sub("1", san)

    for m in _REF_RE.finditer(san):
        raw = m.group(1)
        norm = _norm_name(raw)
        suffix = _derived_suffix(raw)
        if suffix is not None:
            origin = norm.rpartition("#")[0]
            if origin.lower() not in declared_metrics:
                out.append(finding(
                    ERROR, "formula.derived_origin_undefined", path,
                    f"derived reference '${{{raw}}}' has origin '{origin}' "
                    "which is not defined in this file", raw,
                    "Declare the origin metric in this file."))
        elif norm.lower() not in declared_metrics:
            out.append(finding(
                ERROR, "formula.ref_undefined", path,
                f"reference '${{{raw}}}' does not match a metric defined in this file",
                raw, "Every ${...} must name a metric declared in this file's metrics."))
    san = _REF_RE.sub("1", san)

    # Phase 4: an unmatched "${" means an unclosed reference.
    if "${" in san:
        out.append(finding(
            ERROR, "formula.unbalanced", path,
            "unclosed ${...} reference", src,
            "Balance quotes, braces and parentheses."))

    # Phase 5: the grammar requires a signed exponent (1e+5, never 1e5).
    if _UNSIGNED_EXP_RE.search(san):
        out.append(finding(
            WARNING, "formula.exponent_unsigned", path,
            "scientific-notation literal without a signed exponent "
            "(write 1e+5, not 1e5)", src,
            "Add an explicit + or - to the exponent."))

    # Phase 6: linear scan — function frames, argument counts, bare identifiers.
    stack = []  # each frame: [name_or_None, comma_count, has_content]
    unbalanced = False
    discarded = False

    def mark_content():
        if stack:
            stack[-1][2] = True

    i = 0
    while i < len(san):
        c = san[i]
        if c in " \t":
            i += 1
        elif c.isdigit():
            m = _NUMBER_RE.match(san, i)
            mark_content()
            i = m.end()
        elif c.isalpha() or c == "_":
            m = _IDENT_RE.match(san, i)
            ident = m.group(0)
            j = m.end()
            if j < len(san) and san[j] == "(":
                mark_content()
                stack.append([ident, 0, False])
                i = j + 1
            else:
                if ident.lower() not in ("true", "false"):
                    out.append(finding(
                        ERROR, "formula.bare_identifier", path,
                        f"bare identifier '{ident}' - metric references must be "
                        "wrapped in ${...}", ident,
                        "Write ${Name} to reference a metric."))
                mark_content()
                i = j
        elif c == "(":
            mark_content()
            stack.append([None, 0, False])
            i += 1
        elif c == ")":
            if not stack:
                unbalanced = True
            else:
                name, commas, content = stack.pop()
                if name is not None:
                    args = commas + 1 if content else 0
                    lname = name.lower()
                    if lname == "flaguptomax":
                        pass  # already reported as a macro
                    elif lname not in FUNCTIONS:
                        out.append(finding(
                            ERROR, "formula.unknown_function", path,
                            f"unknown function '{name}'", name,
                            "Only the 26 QPortfolio expression functions are "
                            "supported (see REFERENCE.md)."))
                    else:
                        mn, mx = FUNCTIONS[lname]
                        if args < mn or (mx is not None and args > mx):
                            out.append(finding(
                                ERROR, "formula.arity", path,
                                f"{name} takes {_arity_desc(mn, mx)} argument(s), "
                                f"got {args}", name,
                                "Fix the argument count."))
                mark_content()
            i += 1
        elif c == ",":
            if stack:
                stack[-1][1] += 1
            i += 1
        elif c in "+-*/^=<>":
            i += 1
        elif c in "&%":
            discarded = True
            mark_content()
            i += 1
        else:
            i += 1  # unknown character; the server parser is the real gate

    # Phase 7-9.
    if stack or unbalanced:
        out.append(finding(
            ERROR, "formula.unbalanced", path,
            "unbalanced parentheses", src,
            "Balance quotes, braces and parentheses."))
    if discarded:
        out.append(finding(
            WARNING, "formula.discarded_operator", path,
            "'&' or '%' is parsed but silently discarded by the calculator", src,
            "Remove it; concatenation and percent are not supported."))
    if re.search(r"(?i)getirr\(", san):
        out.append(finding(
            WARNING, "formula.getirr_optimization", path,
            "GetIRR imports and calculates, but any optimization of a scenario "
            "using it will fail", src,
            "Avoid GetIRR in metrics used by optimization."))


# --------------------------------------------------------------------------- #
# Semantic checks
# --------------------------------------------------------------------------- #
def semantic_checks(data, strict_nulls):
    out = []
    if not isinstance(data, dict):
        return [finding(ERROR, "root.type", "$", "document root is not a JSON object")]

    # metadata
    meta = data.get("metadata")
    if isinstance(meta, dict):
        ft = meta.get("qp_file_type")
        if ft != EXPECTED_FILE_TYPE:
            out.append(finding(
                ERROR, "metadata.qp_file_type", "$.metadata.qp_file_type",
                f"qp_file_type must be exactly '{EXPECTED_FILE_TYPE}', got {ft!r}",
                ft, f'Set metadata.qp_file_type to "{EXPECTED_FILE_TYPE}".'))
        ver = meta.get("qp_version")
        if ver is not None and not isinstance(ver, (int, float)):
            out.append(finding(
                WARNING, "metadata.qp_version", "$.metadata.qp_version",
                f"qp_version should be a number, got {ver!r}", ver,
                "Use a numeric version like 4.5."))

    # Attribute names declared by THIS file (None = file carries no attributes
    # section, so undeclared-attribute warnings are suppressed: the attribute
    # may live in a sibling file of the import or in the existing model).
    attrs = data.get("attributes")
    attrs_declared = None
    if isinstance(attrs, list):
        attrs_declared = {
            _name_key(a["attribute_name"]) for a in attrs
            if isinstance(a, dict) and isinstance(a.get("attribute_name"), str)}

    metrics = data.get("metrics")
    if isinstance(metrics, list):
        if len(metrics) == 0:
            out.append(finding(
                WARNING, "metrics.empty_deletes_computed", "$.metrics",
                "metrics is an empty list: importing this file deletes every "
                "computed metric of the model", None,
                "Omit the metrics property entirely to leave metrics untouched."))
        declared = {
            _name_key(m["metric_name"]) for m in metrics
            if isinstance(m, dict) and isinstance(m.get("metric_name"), str)
            and _name_key(m["metric_name"])}
        masterdata = {
            _name_key(m["metric_name"]) for m in metrics
            if isinstance(m, dict) and isinstance(m.get("metric_name"), str)
            and _name_key(m["metric_name"])
            and m.get("metric_type") == "MasterData"}
        seen = {}
        for i, metric in enumerate(metrics):
            if isinstance(metric, dict):
                _check_metric(metric, i, declared, masterdata, seen,
                              attrs_declared, out)

    if isinstance(attrs, list):
        for i, attr in enumerate(attrs):
            if not isinstance(attr, dict):
                continue
            path = f"$.attributes[{i}]"
            _check_blank_name(attr.get("attribute_name"),
                              f"{path}.attribute_name", out)
            chars = attr.get("characteristics")
            if isinstance(chars, list):
                for j, ch in enumerate(chars):
                    if isinstance(ch, dict):
                        _check_blank_name(
                            ch.get("characteristic_name"),
                            f"{path}.characteristics[{j}].characteristic_name", out)

    if strict_nulls:
        _check_explicit_nulls(data, "$", out)
    return out


def _check_blank_name(name, path, out):
    if isinstance(name, str) and name and not _norm_name(name):
        out.append(finding(
            ERROR, "name.blank", path,
            "name is blank after normalization (whitespace only)", name,
            "Use a non-empty name."))


def _check_metric(metric, i, declared, masterdata, seen, attrs_declared, out):
    path = f"$.metrics[{i}]"
    name = metric.get("metric_name")
    label = name if isinstance(name, str) else f"metrics[{i}]"

    if isinstance(name, str):
        key = _name_key(name)
        if name and not key:
            out.append(finding(
                ERROR, "name.blank", f"{path}.metric_name",
                "name is blank after normalization (whitespace only)", name,
                "Use a non-empty name."))
        elif key:
            if key in seen:
                out.append(finding(
                    ERROR, "metric.duplicate_name", f"{path}.metric_name",
                    f"metric name '{name}' duplicates the metric at index {seen[key]} "
                    "(names are compared case-insensitively)", name,
                    "Metric names must be unique case-insensitively."))
            else:
                seen[key] = i
            suffix = _derived_suffix(name)
            if suffix is not None:
                out.append(finding(
                    ERROR, "metric.reserved_derived_name", f"{path}.metric_name",
                    f"metric name '{name}' ends in '#{suffix}' which is reserved "
                    "for derived metrics", name,
                    "List the derivation type under the origin metric's "
                    "derived instead."))

    mtype = metric.get("metric_type")
    computed = mtype == "Computed"
    exprs = metric.get("expressions")
    has_exprs = isinstance(exprs, list) and len(exprs) > 0
    if has_exprs and not computed:
        out.append(finding(
            ERROR, "metric.expressions_not_computed", f"{path}.expressions",
            f"metric '{label}' carries expressions but is not Computed", mtype,
            "Set metric_type to Computed, or remove the expressions."))
    if computed and not has_exprs:
        out.append(finding(
            ERROR, "metric.computed_no_expressions", f"{path}.expressions",
            f"computed metric '{label}' has no expressions", None,
            "A Computed metric needs at least one expression."))

    level = metric.get("level")
    if computed and level is None:
        out.append(finding(
            WARNING, "level.missing", f"{path}.level",
            f"computed metric '{label}' does not state its level", None,
            "State level explicitly (Outcome, Opportunity, Group or Scenario); "
            "the effective default is ambiguous."))

    group_by = metric.get("group_by")
    has_group_by = isinstance(group_by, list) and len(group_by) > 0
    if level == "Group" and not has_group_by:
        out.append(finding(
            ERROR, "metric.group_missing_group_by", f"{path}.group_by",
            f"Group-level metric '{label}' has no group_by", None,
            "Name the attribute(s) whose values define the groups."))
    if has_group_by and level != "Group":
        out.append(finding(
            WARNING, "metric.group_by_ignored", f"{path}.group_by",
            f"group_by on metric '{label}' is ignored when level is not Group",
            level, "Set level to Group or remove group_by."))

    # Derived-metric guidance: derived transforms are recommended only for
    # linear, Interest-scaled origins (elsewhere the derived value may differ
    # from the equivalent explicit expression).
    derived = metric.get("derived")
    has_derived = isinstance(derived, list) and len(derived) > 0
    if has_derived and metric.get("scale_by") == "Instance":
        out.append(finding(
            WARNING, "derived.instance_scaled", f"{path}.derived",
            f"metric '{label}' has derived metrics but is scaled by Instance; "
            "the derived values may differ from an explicit computed metric",
            "Instance",
            "Derived metrics are recommended only for linear, Interest-scaled "
            "origins; write an explicit computed metric instead."))
    if has_derived and computed and isinstance(exprs, list):
        nonlinear = False
        for ex in exprs:
            if not isinstance(ex, dict):
                continue
            for field in ("formula", "first_period_formula"):
                v = ex.get(field)
                if isinstance(v, str) and _looks_nonlinear(v, masterdata):
                    nonlinear = True
        if nonlinear:
            out.append(finding(
                WARNING, "derived.nonlinear_origin", f"{path}.derived",
                f"metric '{label}' has derived metrics but its expressions "
                "look non-linear; the derived value may differ from the "
                "equivalent explicit expression", None,
                "Derived metrics are recommended only for linear, "
                "Interest-scaled origins; write an explicit computed metric "
                "instead."))

    if not isinstance(exprs, list):
        return
    seen_orders = {}
    for j, ex in enumerate(exprs):
        if not isinstance(ex, dict):
            continue
        expath = f"{path}.expressions[{j}]"
        order = ex.get("order")
        eff = order if isinstance(order, int) else 0
        if eff in seen_orders:
            out.append(finding(
                WARNING, "expr.order_duplicate", f"{expath}.order",
                f"order {eff} is reused (also at expressions[{seen_orders[eff]}])",
                eff, "Give each expression of a metric a distinct order "
                "(lower evaluates first)."))
        else:
            seen_orders[eff] = j
        criteria = ex.get("criteria")
        if isinstance(criteria, list) and criteria:
            if level == "Scenario":
                out.append(finding(
                    WARNING, "criteria.scenario_level", f"{expath}.criteria",
                    "criteria on a Scenario-level metric: scenario-level "
                    "expressions cannot be filtered", None,
                    "Move the metric to Outcome/Opportunity/Group level or "
                    "drop the criteria."))
            for k, crit in enumerate(criteria):
                if not isinstance(crit, dict):
                    continue
                cpath = f"{expath}.criteria[{k}]"
                oc = crit.get("outcome")
                if level == "Opportunity" and isinstance(oc, list) and oc:
                    out.append(finding(
                        WARNING, "criteria.outcome_on_opportunity",
                        f"{cpath}.outcome",
                        "outcome filter on an Opportunity-level metric: only "
                        "Outcome-level expressions can filter by outcome", None,
                        "Use level Outcome for outcome-filtered expressions."))
                a = crit.get("attribute")
                if (isinstance(a, str) and attrs_declared is not None
                        and _name_key(a) not in attrs_declared):
                    out.append(finding(
                        WARNING, "criteria.attribute_undeclared",
                        f"{cpath}.attribute",
                        f"criterion attribute '{a}' is not declared in this "
                        "file's attributes (the importer silently creates it)", a,
                        "Declare the attribute or fix the name."))
        for field in ("formula", "first_period_formula"):
            v = ex.get(field)
            if isinstance(v, str):
                _check_formula(v, f"{expath}.{field}", declared,
                               attrs_declared, out)


def _check_explicit_nulls(node, path, out):
    if isinstance(node, dict):
        for k, v in node.items():
            if v is None:
                out.append(finding(
                    WARNING, "style.explicit_null", f"{path}.{k}",
                    f"'{k}' is explicitly null; omit optional fields instead", None,
                    "Remove the key rather than writing null."))
            else:
                _check_explicit_nulls(v, f"{path}.{k}", out)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _check_explicit_nulls(v, f"{path}[{i}]", out)


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def main(argv=None):
    ap = argparse.ArgumentParser(description="Validate a QPortfolio model JSON file.")
    ap.add_argument("file", help="path to the model JSON file")
    ap.add_argument("--schema", help="explicit path to model.schema.json")
    ap.add_argument("--format", choices=["json", "text"], default="json")
    ap.add_argument("--strict-nulls", action="store_true",
                    help="warn on explicit nulls for optional fields")
    args = ap.parse_args(argv)

    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        try:
            import jsonschema as _js
            _ver = getattr(_js, "__version__", "unknown")
        except ImportError:
            _ver = None
        if _ver is None:
            msg = ("the 'jsonschema' package is not installed; "
                   "run: pip install 'jsonschema>=4.18'")
        else:
            msg = (f"'jsonschema' {_ver} is too old (Draft 2020-12 needs >=4.18); "
                   "run: pip install --upgrade 'jsonschema>=4.18'")
        _emit_env_error(args.format, msg)
        return 3

    target = Path(args.file)

    def _reject_nonfinite(token):
        raise ValueError(f"non-finite literal '{token}' is not allowed")

    try:
        text = target.read_text(encoding="utf-8")
    except OSError as e:
        _emit_io_error(args.format, f"cannot read {target}: {e}")
        return 2
    try:
        data = json.loads(text, parse_constant=_reject_nonfinite)
    except ValueError as e:
        _emit_io_error(args.format, f"{target} is not valid JSON (or contains NaN/Infinity): {e}")
        return 2

    schema_path, source = discover_schema(args.schema, target)
    if schema_path is None or not schema_path.is_file():
        _emit_env_error(args.format, "no model.schema.json found (server copy or bundled)")
        return 3
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        _emit_env_error(args.format, f"cannot load schema {schema_path}: {e}")
        return 3

    validator = _make_validator(Draft202012Validator)(schema)
    schema_errors = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
        loc = "$" + "".join(
            f"[{p}]" if isinstance(p, int) else f".{p}" for p in err.absolute_path)
        schema_errors.append({
            "json_path": loc,
            "message": err.message,
            "validator": err.validator,
        })

    semantic = semantic_checks(data, args.strict_nulls)
    hard = [f for f in semantic if f["severity"] == ERROR]
    warns = [f for f in semantic if f["severity"] == WARNING]

    # cross-schema drift note (server vs bundled)
    drift = None
    if source == "server-in-repo":
        bundled = Path(__file__).resolve().parent.parent / "schemas" / "model.schema.json"
        if bundled.is_file() and _sha256(bundled) != _sha256(schema_path):
            drift = "bundled schema differs from the in-repo server schema; run sync_schema.py"

    ok = not schema_errors and not hard
    result = {
        "ok": ok,
        "schema_path_used": str(schema_path),
        "schema_source": source,
        "summary": {
            "schema_errors": len(schema_errors),
            "hard_errors": len(hard),
            "warnings": len(warns),
        },
        "schema_errors": schema_errors,
        "semantic": semantic,
    }
    if drift:
        result["drift_warning"] = drift

    if args.format == "json":
        print(json.dumps(result, indent=2))
    else:
        _print_text(result)
    return 0 if ok else 1


def _emit_io_error(fmt, msg):
    if fmt == "json":
        print(json.dumps({"ok": False, "error": "io", "message": msg}, indent=2))
    else:
        print(f"IO/PARSE ERROR: {msg}", file=sys.stderr)


def _emit_env_error(fmt, msg):
    if fmt == "json":
        print(json.dumps({"ok": False, "error": "environment", "message": msg}, indent=2))
    else:
        print(f"ENVIRONMENT ERROR: {msg}", file=sys.stderr)


def _print_text(result):
    s = result["summary"]
    status = "VALID" if result["ok"] else "INVALID"
    print(f"{status}  (schema={result['schema_source']}: {result['schema_path_used']})")
    print(f"  schema_errors={s['schema_errors']} hard_errors={s['hard_errors']} "
          f"warnings={s['warnings']}")
    if result.get("drift_warning"):
        print(f"  ! {result['drift_warning']}")
    for e in result["schema_errors"]:
        print(f"  [schema] {e['json_path']}: {e['message']} ({e['validator']})")
    for f in result["semantic"]:
        tag = "ERROR" if f["severity"] == ERROR else "warn "
        print(f"  [{tag}] {f['check']} @ {f['json_path']}: {f['message']}")
        if f.get("hint"):
            print(f"          hint: {f['hint']}")


if __name__ == "__main__":
    sys.exit(main())
