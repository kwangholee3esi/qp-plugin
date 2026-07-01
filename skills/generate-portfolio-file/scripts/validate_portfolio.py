#!/usr/bin/env python3
"""Validate a QPortfolio Portable JSON *portfolio* file.

Two layers of checking:
  1. JSON Schema (Draft 2020-12) against portfolio.schema.json.
  2. Semantic cross-reference / consistency rules that the schema describes in
     prose but cannot express (opportunity-name references, numeric ordering,
     time-series shape, etc.) and that the server importer does NOT enforce.

Exit codes:
  0  valid   - no schema errors and no HARD semantic errors (warnings allowed)
  1  invalid - >=1 schema error and/or HARD semantic error
  2  io/parse error - file missing/unreadable, not JSON, or contains NaN/Infinity
  3  environment error - `jsonschema` not installed, or no schema found

Usage:
  python validate_portfolio.py <file.json> [--schema PATH]
                               [--format json|text] [--strict-nulls]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ERROR = "error"
WARNING = "warning"

# Relative path of the committed schema inside a cp-portfolio checkout.
SERVER_SCHEMA_REL = ("server", "Esi.Sp.Portable", "Schemas", "portfolio.schema.json")
EXPECTED_FILE_TYPE = "QPortfolio Data"


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

    bundled = Path(__file__).resolve().parent.parent / "schemas" / "portfolio.schema.json"
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
# of RFC-6901 JSON Pointers into each item (e.g. ["/opportunity_name"], or the
# composite ["/metric_name", "/limit_type"]). It is NOT part of Draft 2020-12,
# so jsonschema ignores it unless we register a handler. The server enforces it
# the same way (PortableSchemaValidator swaps in the array-ext meta-schema); we
# extend the validator instead so these land in the normal schema-error stream.
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
# Semantic checks
# --------------------------------------------------------------------------- #
def _opportunity_outcomes(section):
    """Safely pull an opportunity_outcomes list from input_data / master_data."""
    if not isinstance(section, dict):
        return []
    oo = section.get("opportunity_outcomes")
    return oo if isinstance(oo, list) else []


def _build_opp_index(opp_list, root_path, out):
    """Return {name: set(outcome_names)} and emit per-opp checks.

    Opportunity/outcome/metric-name uniqueness is enforced by the schema's
    `uniqueKeys`; this only builds the cross-reference index and runs the
    checks the schema cannot express (weights, time-series shape)."""
    index = {}
    for i, opp in enumerate(opp_list):
        if not isinstance(opp, dict):
            continue
        name = opp.get("opportunity_name")
        path = f"{root_path}.opportunity_outcomes[{i}]"
        outcomes = opp.get("outcomes")
        out_names = set()
        modal_len_for_opp = []
        if isinstance(outcomes, list):
            for j, oc in enumerate(outcomes):
                if not isinstance(oc, dict):
                    continue
                ocp = f"{path}.outcomes[{j}]"
                ocn = oc.get("outcome_name")
                if isinstance(ocn, str):
                    out_names.add(ocn)
                _check_weight(oc, outcomes, ocp, out)
                _check_metric_values(oc, ocp, out, modal_len_for_opp)
        index[name] = out_names
    return index


def _check_weight(outcome, siblings, ocp, out):
    weight = outcome.get("weight")
    multi = isinstance(siblings, list) and len(siblings) > 1
    if weight is None:
        if multi:
            out.append(finding(
                WARNING, "weight.missing", f"{ocp}.weight",
                "multi-outcome opportunity has an outcome with no weight "
                "(importer normalizes, but be explicit)", None,
                "Set a probability weight for every outcome of an uncertain opportunity."))
    elif isinstance(weight, (int, float)) and weight < 0:
        out.append(finding(
            ERROR, "weight.negative", f"{ocp}.weight",
            f"outcome weight {weight} is negative", weight,
            "Weights are probabilities; use a non-negative number."))


def _check_metric_values(outcome, ocp, out, modal_len_for_opp):
    mvs = outcome.get("metric_values")
    if not isinstance(mvs, list):
        return
    series_lens = []
    for k, mv in enumerate(mvs):
        if not isinstance(mv, dict):
            continue
        mvp = f"{ocp}.metric_values[{k}]"
        mname = mv.get("metric_name")
        values = mv.get("values")
        scalar = mv.get("scalar") is True
        if isinstance(values, list):
            if scalar:
                if len(values) != 1:
                    out.append(finding(
                        ERROR, "scalar.arity", f"{mvp}.values",
                        f"scalar metric '{mname}' must have exactly one value, got {len(values)}",
                        len(values), "A scalar metric carries a single value."))
            else:
                if len(values) == 0:
                    out.append(finding(
                        WARNING, "series.empty", f"{mvp}.values",
                        f"non-scalar metric '{mname}' has an empty time series", None,
                        "Provide per-period values or mark the metric scalar."))
                else:
                    series_lens.append(len(values))
    # within-outcome horizon consistency
    if len(set(series_lens)) > 1:
        out.append(finding(
            WARNING, "series.length_mismatch", ocp,
            f"time-series metrics in this outcome have differing lengths {sorted(set(series_lens))} "
            "(importer zero-fills, but verify the horizon)", sorted(set(series_lens)),
            "Use one consistent number of periods across metrics."))
    if series_lens:
        modal_len_for_opp.extend(series_lens)


def _limit_numeric_checks(limit, path, out, label):
    """Shared numeric-ordering checks for opportunity_limits and group_limits."""
    def num(key):
        v = limit.get(key)
        return v if isinstance(v, (int, float)) else None

    tmin, tmax = num("total_minimum"), num("total_maximum")
    if tmin is not None and tmax is not None and tmax < tmin:
        out.append(finding(
            ERROR, "limit.total_max_lt_min", f"{path}.total_maximum",
            f"{label}: total_maximum ({tmax}) < total_minimum ({tmin})",
            tmax, "Schema requires total_maximum >= total_minimum."))
    imin, imax = num("total_instances_minimum"), num("total_instances_maximum")
    if imin is not None and imax is not None and imax < imin:
        out.append(finding(
            ERROR, "limit.inst_max_lt_min", f"{path}.total_instances_maximum",
            f"{label}: total_instances_maximum ({imax}) < total_instances_minimum ({imin})",
            imax, "Schema requires total_instances_maximum >= total_instances_minimum."))
    for key in ("total_minimum", "total_maximum",
                "total_instances_minimum", "total_instances_maximum", "interior_limit"):
        v = num(key)
        if v is not None and v < 0:
            out.append(finding(
                ERROR, "limit.negative", f"{path}.{key}",
                f"{label}: {key} ({v}) is negative", v,
                "Selection quantities are non-negative."))
    mins = limit.get("time_period_minima")
    maxs = limit.get("time_period_maxima")
    mins = mins if isinstance(mins, list) else []
    maxs = maxs if isinstance(maxs, list) else []
    for idx, v in enumerate(mins):
        if isinstance(v, (int, float)) and v < 0:
            out.append(finding(
                ERROR, "limit.period_negative", f"{path}.time_period_minima[{idx}]",
                f"{label}: time_period_minima[{idx}] ({v}) is negative", v,
                "Per-period selections are non-negative."))
    for idx, v in enumerate(maxs):
        if isinstance(v, (int, float)) and v < 0:
            out.append(finding(
                ERROR, "limit.period_negative", f"{path}.time_period_maxima[{idx}]",
                f"{label}: time_period_maxima[{idx}] ({v}) is negative", v,
                "Per-period selections are non-negative."))
    for idx in range(min(len(mins), len(maxs))):
        lo, hi = mins[idx], maxs[idx]
        if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and hi < lo:
            out.append(finding(
                ERROR, "limit.period_max_lt_min", f"{path}.time_period_maxima[{idx}]",
                f"{label}: time_period_maxima[{idx}] ({hi}) < time_period_minima[{idx}] ({lo})",
                hi, "Each per-period maximum must be >= the matching minimum."))
    if limit.get("integer_only") is True and limit.get("interior_limit") is not None:
        out.append(finding(
            WARNING, "limit.interior_ignored", f"{path}.interior_limit",
            f"{label}: interior_limit is ignored when integer_only is true", None,
            "Drop interior_limit or set integer_only false."))
    il = num("interior_limit")
    if il is not None and tmax is not None and il > tmax:
        out.append(finding(
            WARNING, "limit.interior_gt_max", f"{path}.interior_limit",
            f"{label}: interior_limit ({il}) > total_maximum ({tmax})", il,
            "Min Fraction should not exceed the total maximum."))


def _ref_check(name, valid, path, check, out, *, what, hint):
    if isinstance(name, str) and name not in valid:
        out.append(finding(
            ERROR, check, path,
            f"references {what} '{name}' which is not defined in input_data",
            name, hint))


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

    input_opps = _opportunity_outcomes(data.get("input_data"))
    opp_index = _build_opp_index(input_opps, "$.input_data", out)
    OPP = {n for n in opp_index if isinstance(n, str)}

    master_opps = _opportunity_outcomes(data.get("master_data"))
    master_index = _build_opp_index(master_opps, "$.master_data", out)
    MASTER = {n for n in master_index if isinstance(n, str)}

    _check_attributes(data.get("attributes"), OPP, MASTER, out)
    _check_outcome_dependency(data.get("outcome_dependency"), OPP, opp_index, out)
    _check_selection_constraints(data.get("selection_constraints"), OPP, out)
    _check_selection_dependency(data.get("selection_dependency"), OPP, out)
    _check_selection_group(data.get("selection_group"), OPP, out)
    _check_master_default(data.get("master_data"), data.get("attributes"), master_opps, out)

    if strict_nulls:
        _check_explicit_nulls(data, "$", out)
    return out


def _check_attributes(attrs, OPP, MASTER, out):
    if not isinstance(attrs, dict):
        return
    declared = attrs.get("attributes")
    declared = set(declared) if isinstance(declared, list) else set()
    rows = attrs.get("opportunity_attributes")
    if not isinstance(rows, list):
        return
    seen_order = {}
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        path = f"$.attributes.opportunity_attributes[{i}]"
        name = row.get("opportunity_name")
        is_md = row.get("is_master_data") is True
        if isinstance(name, str):
            valid = OPP | MASTER if is_md else OPP
            if name not in valid:
                out.append(finding(
                    ERROR, "ref.attr_opportunity", f"{path}.opportunity_name",
                    f"attribute row references '{name}' not defined in "
                    f"{'input_data/master_data' if is_md else 'input_data'}",
                    name, "Match an existing opportunity, or set is_master_data."))
        order = row.get("order")
        if isinstance(order, int):
            if order in seen_order:
                out.append(finding(
                    WARNING, "attr.order_duplicate", f"{path}.order",
                    f"order {order} is reused (also at index {seen_order[order]})",
                    order, "Use a distinct 0-based order per opportunity."))
            else:
                seen_order[order] = i
        chars = row.get("characteristics")
        if isinstance(chars, list):
            for c, ch in enumerate(chars):
                if not isinstance(ch, dict):
                    continue
                a = ch.get("attribute")
                cp = f"{path}.characteristics[{c}].attribute"
                if isinstance(a, str):
                    if declared and a not in declared:
                        out.append(finding(
                            WARNING, "attr.undeclared", cp,
                            f"attribute '{a}' is used but not declared in attributes.attributes",
                            a, "Add it to attributes.attributes or remove the characteristic."))


def _check_outcome_dependency(dep, OPP, opp_index, out):
    if not isinstance(dep, dict):
        return
    deps = dep.get("dependencies")
    if not isinstance(deps, list):
        return
    for i, d in enumerate(deps):
        if not isinstance(d, dict):
            continue
        path = f"$.outcome_dependency.dependencies[{i}]"
        ind = d.get("independent_opportunity")
        dpd = d.get("dependent_opportunity")
        _ref_check(ind, OPP, f"{path}.independent_opportunity",
                   "ref.outcome_dep.independent", out,
                   what="independent opportunity",
                   hint="Add it to input_data or fix the name.")
        _ref_check(dpd, OPP, f"{path}.dependent_opportunity",
                   "ref.outcome_dep.dependent", out,
                   what="dependent opportunity",
                   hint="Add it to input_data or fix the name.")
        if isinstance(ind, str) and ind == dpd:
            out.append(finding(
                WARNING, "outcome_dep.self", path,
                f"independent and dependent opportunity are both '{ind}'", ind,
                "An opportunity should not depend on itself."))
        ind_out = opp_index.get(ind, set())
        dep_out = opp_index.get(dpd, set())
        cases = d.get("target_cases")
        if not isinstance(cases, list):
            continue
        seen_ind = set()
        for j, case in enumerate(cases):
            if not isinstance(case, dict):
                continue
            cpath = f"{path}.target_cases[{j}]"
            inds = case.get("independent_outcomes")
            if isinstance(inds, list):
                for o in inds:
                    if o == "*":
                        continue
                    if isinstance(o, str) and ind_out and o not in ind_out:
                        out.append(finding(
                            ERROR, "ref.outcome_dep.independent_outcome",
                            f"{cpath}.independent_outcomes",
                            f"independent outcome '{o}' is not an outcome of '{ind}'",
                            o, 'Use a real outcome name or "*" for all others.'))
                    if isinstance(o, str):
                        if o in seen_ind:
                            out.append(finding(
                                ERROR, "outcome_dep.independent_outcome_dup",
                                f"{cpath}.independent_outcomes",
                                f"independent outcome '{o}' mapped by more than one case", o,
                                "Each independent outcome maps in at most one case."))
                        seen_ind.add(o)
            weights = case.get("outcome_weights")
            if isinstance(weights, list):
                for w, ow in enumerate(weights):
                    if not isinstance(ow, dict):
                        continue
                    douts = ow.get("dependent_outcomes")
                    if isinstance(douts, list):
                        for o in douts:
                            if isinstance(o, str) and dep_out and o not in dep_out:
                                out.append(finding(
                                    ERROR, "ref.outcome_dep.dependent_outcome",
                                    f"{cpath}.outcome_weights[{w}].dependent_outcomes",
                                    f"dependent outcome '{o}' is not an outcome of '{dpd}'",
                                    o, "Use a real outcome name of the dependent opportunity."))


def _check_selection_constraints(sc, OPP, out):
    if not isinstance(sc, dict):
        return
    limits = sc.get("opportunity_limits")
    if not isinstance(limits, list):
        return
    for i, lim in enumerate(limits):
        if not isinstance(lim, dict):
            continue
        path = f"$.selection_constraints.opportunity_limits[{i}]"
        name = lim.get("opportunity_name")
        if isinstance(name, str):
            _ref_check(name, OPP, f"{path}.opportunity_name",
                       "ref.constraint_opportunity", out,
                       what="opportunity", hint="Add it to input_data or fix the name.")
        _limit_numeric_checks(lim, path, out, f"opportunity '{name}'")


def _check_selection_dependency(sd, OPP, out):
    if not isinstance(sd, dict):
        return
    deps = sd.get("dependencies")
    if not isinstance(deps, list):
        return
    for i, d in enumerate(deps):
        if not isinstance(d, dict):
            continue
        path = f"$.selection_dependency.dependencies[{i}]"
        dpd = d.get("dependent_opportunity")
        ind = d.get("independent_opportunity")
        _ref_check(dpd, OPP, f"{path}.dependent_opportunity",
                   "ref.selection_dep.dependent", out,
                   what="dependent opportunity",
                   hint="Add it to input_data or fix the name.")
        _ref_check(ind, OPP, f"{path}.independent_opportunity",
                   "ref.selection_dep.independent", out,
                   what="independent opportunity",
                   hint="Add it to input_data or fix the name.")
        if isinstance(ind, str) and ind == dpd:
            out.append(finding(
                WARNING, "selection_dep.self", path,
                f"dependent and independent opportunity are both '{ind}'", ind,
                "An opportunity should not depend on itself."))


def _check_selection_group(sg, OPP, out):
    if not isinstance(sg, dict):
        return
    groups = sg.get("groups")
    group_names = set()
    if isinstance(groups, list):
        for i, g in enumerate(groups):
            if not isinstance(g, dict):
                continue
            path = f"$.selection_group.groups[{i}]"
            gname = g.get("group_name")
            if isinstance(gname, str):
                group_names.add(gname)
            members = g.get("members")
            if isinstance(members, list):
                for m, mem in enumerate(members):
                    if not isinstance(mem, dict):
                        continue
                    mp = f"{path}.members[{m}].opportunity_name"
                    mn = mem.get("opportunity_name")
                    _ref_check(mn, OPP, mp, "ref.group_member", out,
                               what="member opportunity",
                               hint="Members must be defined opportunities.")
    limits = sg.get("group_limits")
    if isinstance(limits, list):
        for i, lim in enumerate(limits):
            if not isinstance(lim, dict):
                continue
            path = f"$.selection_group.group_limits[{i}]"
            gname = lim.get("group_name")
            if isinstance(gname, str):
                if group_names and gname not in group_names:
                    out.append(finding(
                        ERROR, "ref.group_limit", f"{path}.group_name",
                        f"group_limits references group '{gname}' with no matching group",
                        gname, "Match an existing group_name."))
            _limit_numeric_checks(lim, path, out, f"group '{gname}'")


def _check_master_default(master_data, attrs, master_opps, out):
    if not isinstance(master_data, dict) or not master_opps:
        return
    # A master set is "default" if it carries no attribute qualification: either
    # it has no row in opportunity_attributes, or its row has empty characteristics.
    qualified = set()
    if isinstance(attrs, dict):
        rows = attrs.get("opportunity_attributes")
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict) or row.get("is_master_data") is not True:
                    continue
                chars = row.get("characteristics")
                has_value = isinstance(chars, list) and any(
                    isinstance(c, dict) and c.get("value") not in (None, "") for c in chars)
                if has_value:
                    qualified.add(row.get("opportunity_name"))
    master_names = {o.get("opportunity_name") for o in master_opps if isinstance(o, dict)}
    if master_names and master_names <= qualified:
        out.append(finding(
            ERROR, "master.no_default", "$.master_data",
            "every master-data set is attribute-qualified; a default set "
            "(no attributes) must always exist", None,
            "Add a master-data set with no attribute characteristics."))


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
    ap = argparse.ArgumentParser(description="Validate a QPortfolio portfolio JSON file.")
    ap.add_argument("file", help="path to the portfolio JSON file")
    ap.add_argument("--schema", help="explicit path to portfolio.schema.json")
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
        _emit_env_error(args.format, "no portfolio.schema.json found (server copy or bundled)")
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
        bundled = Path(__file__).resolve().parent.parent / "schemas" / "portfolio.schema.json"
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
