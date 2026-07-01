#!/usr/bin/env python3
"""Validate a QPortfolio Portable JSON *scenario* file.

Two layers of checking:
  1. JSON Schema (Draft 2020-12) against scenario.schema.json.
  2. Semantic / consistency rules that the schema describes in prose but cannot
     express (qp_file_type discriminator, numeric ordering on limits, metric-limit
     uniqueness, selection-dependency direction, per-period shape, etc.).

A scenario does NOT define opportunities or metrics; it references names defined
in its portfolio. With --portfolio PATH the validator also cross-checks every
referenced name against that portfolio:
  - opportunity names are fully enumerable in the portfolio -> a miss is a HARD error.
  - metric names may be COMPUTED/expression metrics absent from input_data -> a miss
    is a WARNING, not an error.
Without --portfolio it emits one warning that cross-references are unchecked.

Exit codes:
  0  valid   - no schema errors and no HARD semantic errors (warnings allowed)
  1  invalid - >=1 schema error and/or HARD semantic error
  2  io/parse error - file missing/unreadable, not JSON, or contains NaN/Infinity
  3  environment error - `jsonschema` not installed, or no schema found

Usage:
  python validate_scenario.py <file.json> [--schema PATH] [--portfolio PATH]
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
SERVER_SCHEMA_REL = ("server", "Esi.Sp.Portable", "Schemas", "scenario.schema.json")
EXPECTED_FILE_TYPE = "QPortfolio Scenario Data"


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

    bundled = Path(__file__).resolve().parent.parent / "schemas" / "scenario.schema.json"
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
# of RFC-6901 JSON Pointers into each item (e.g. ["/group_name"], or the
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
# Shared numeric-ordering checks for opportunity_limits and group_limits
# --------------------------------------------------------------------------- #
def _limit_numeric_checks(limit, path, out, label):
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
            f"references {what} '{name}' which is not defined in the portfolio",
            name, hint))


# --------------------------------------------------------------------------- #
# Portfolio extraction (for --portfolio cross-reference)
# --------------------------------------------------------------------------- #
def _opportunity_outcomes(section):
    if not isinstance(section, dict):
        return []
    oo = section.get("opportunity_outcomes")
    return oo if isinstance(oo, list) else []


def extract_portfolio_names(portfolio):
    """Return (opportunity_names:set, metric_names:set) from a portfolio document."""
    opps, metrics = set(), set()
    if not isinstance(portfolio, dict):
        return opps, metrics
    for section in ("input_data", "master_data"):
        for opp in _opportunity_outcomes(portfolio.get(section)):
            if not isinstance(opp, dict):
                continue
            name = opp.get("opportunity_name")
            if isinstance(name, str):
                opps.add(name)
            outcomes = opp.get("outcomes")
            if isinstance(outcomes, list):
                for oc in outcomes:
                    if not isinstance(oc, dict):
                        continue
                    for mv in oc.get("metric_values") or []:
                        if isinstance(mv, dict) and isinstance(mv.get("metric_name"), str):
                            metrics.add(mv["metric_name"])
    return opps, metrics


# --------------------------------------------------------------------------- #
# Semantic checks
# --------------------------------------------------------------------------- #
def semantic_checks(data, strict_nulls, portfolio_names):
    """portfolio_names: (opps, metrics) sets, or None when no portfolio supplied."""
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

    _check_settings(data.get("settings"), out)
    _check_optimization(data.get("optimization"), out)
    _check_metric_limits(data.get("metric_limits"), data.get("settings"), out)
    sel_names = _check_opportunity_selections(data.get("opportunity_selections"), out)
    constraint_names = _check_selection_constraints(data.get("selection_constraints"), out)
    dep_names = _check_selection_dependency(data.get("selection_dependency"), out)
    group_names = _check_selection_group(data.get("selection_group"), out)

    _cross_reference(data, portfolio_names, out)

    if strict_nulls:
        _check_explicit_nulls(data, "$", out)
    return out


def _check_settings(settings, out):
    if settings is None:
        out.append(finding(
            WARNING, "settings.missing", "$.settings",
            "scenario has no settings block; a scenario_name is recommended", None,
            "Add settings.scenario_name to identify the scenario."))
        return
    if not isinstance(settings, dict):
        return
    name = settings.get("scenario_name")
    if isinstance(name, str) and not name.strip():
        out.append(finding(
            WARNING, "settings.scenario_name_blank", "$.settings.scenario_name",
            "scenario_name is blank", name,
            "Give the scenario a meaningful, unique name."))
    thr = settings.get("instance_selection_threshold")
    if isinstance(thr, (int, float)) and not (0 <= thr <= 1):
        out.append(finding(
            WARNING, "settings.threshold_range", "$.settings.instance_selection_threshold",
            f"instance_selection_threshold ({thr}) is outside the expected 0..1 range", thr,
            "Use a fractional interest between 0 and 1."))


def _check_optimization(opt, out):
    if not isinstance(opt, dict):
        return
    obj = opt.get("objective_metric_name")
    if not (isinstance(obj, str) and obj.strip()):
        out.append(finding(
            WARNING, "optimization.objective_missing", "$.optimization.objective_metric_name",
            "optimization block has no objective_metric_name", obj,
            "Name the metric to optimize, e.g. an NPV metric."))
    tp = opt.get("objective_time_period")
    if isinstance(tp, int) and tp < 0:
        out.append(finding(
            ERROR, "optimization.objective_period_negative", "$.optimization.objective_time_period",
            f"objective_time_period ({tp}) is negative", tp,
            "Time periods are 0-based and non-negative."))
    mls = opt.get("max_local_solver")
    if isinstance(mls, int) and not (0 <= mls <= 100):
        out.append(finding(
            WARNING, "optimization.max_local_solver_range", "$.optimization.max_local_solver",
            f"max_local_solver ({mls}) is outside the supported 0..100 range", mls,
            "Use up to 100 local solvers."))


def _check_metric_limits(limits, settings, out):
    if not isinstance(limits, list):
        return
    soft_enabled = isinstance(settings, dict) and settings.get("enable_soft_constraints") is True
    for i, lim in enumerate(limits):
        if not isinstance(lim, dict):
            continue
        path = f"$.metric_limits[{i}]"
        mname = lim.get("metric_name")
        ltype = lim.get("limit_type")
        if ltype is None:
            out.append(finding(
                WARNING, "metric_limit.no_type", f"{path}.limit_type",
                f"metric_limit for '{mname}' has no limit_type", None,
                "Set limit_type to Minimum or Maximum."))
        targets = lim.get("targets")
        if isinstance(targets, list):
            for t, tg in enumerate(targets):
                if not isinstance(tg, dict):
                    continue
                p = tg.get("period")
                if isinstance(p, int) and p < 0:
                    out.append(finding(
                        ERROR, "metric_limit.period_negative", f"{path}.targets[{t}].period",
                        f"target period ({p}) is negative", p,
                        "Time periods are 0-based and non-negative."))
        if lim.get("soft") is True and not soft_enabled:
            out.append(finding(
                WARNING, "metric_limit.soft_disabled", f"{path}.soft",
                f"metric_limit '{mname}' is soft but settings.enable_soft_constraints is not true",
                None, "Set settings.enable_soft_constraints true, or make the limit hard."))


def _check_opportunity_selections(sel, out):
    names = set()
    if not isinstance(sel, list):
        return names
    seen = set()
    for i, s in enumerate(sel):
        if not isinstance(s, dict):
            continue
        path = f"$.opportunity_selections[{i}]"
        name = s.get("opportunity_name")
        if isinstance(name, str):
            if name in seen:
                out.append(finding(
                    ERROR, "unique.selection_opportunity", f"{path}.opportunity_name",
                    f"duplicate opportunity_selections entry for '{name}'", name,
                    "List each opportunity's selections once."))
            seen.add(name)
            names.add(name)
        for j, pv in enumerate(s.get("selections") or []):
            if not isinstance(pv, dict):
                continue
            period = pv.get("period")
            value = pv.get("value")
            if isinstance(period, int) and period < 0:
                out.append(finding(
                    ERROR, "selection.period_negative", f"{path}.selections[{j}].period",
                    f"selection period ({period}) is negative", period,
                    "Time periods are 0-based and non-negative."))
            if isinstance(value, (int, float)) and value < 0:
                out.append(finding(
                    ERROR, "selection.value_negative", f"{path}.selections[{j}].value",
                    f"selected quantity ({value}) is negative", value,
                    "Selected quantities are non-negative (0 = not selected)."))
    return names


def _check_selection_constraints(sc, out):
    names = set()
    if not isinstance(sc, dict):
        return names
    limits = sc.get("opportunity_limits")
    if not isinstance(limits, list):
        return names
    for i, lim in enumerate(limits):
        if not isinstance(lim, dict):
            continue
        path = f"$.selection_constraints.opportunity_limits[{i}]"
        name = lim.get("opportunity_name")
        if isinstance(name, str):
            names.add(name)
        _limit_numeric_checks(lim, path, out, f"opportunity '{name}'")
    return names


def _check_selection_dependency(sd, out):
    names = set()
    if not isinstance(sd, dict):
        return names
    deps = sd.get("dependencies")
    if not isinstance(deps, list):
        return names
    seen_pairs = set()
    for i, d in enumerate(deps):
        if not isinstance(d, dict):
            continue
        path = f"$.selection_dependency.dependencies[{i}]"
        dpd = d.get("dependent_opportunity")
        ind = d.get("independent_opportunity")
        for n in (dpd, ind):
            if isinstance(n, str):
                names.add(n)
        if isinstance(ind, str) and ind == dpd:
            out.append(finding(
                WARNING, "selection_dep.self", path,
                f"dependent and independent opportunity are both '{ind}'", ind,
                "An opportunity should not depend on itself."))
        if isinstance(dpd, str) and isinstance(ind, str):
            pair = (dpd, ind)
            if pair in seen_pairs:
                out.append(finding(
                    WARNING, "selection_dep.duplicate_pair", path,
                    f"more than one rule for dependent '{dpd}' / independent '{ind}'",
                    list(pair), "Combine duplicate dependency rules for the same pair."))
            seen_pairs.add(pair)
    return names


def _check_selection_group(sg, out):
    names = set()
    if not isinstance(sg, dict):
        return names
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
                for mem in members:
                    if not isinstance(mem, dict):
                        continue
                    mn = mem.get("opportunity_name")
                    if isinstance(mn, str):
                        names.add(mn)
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
    return names


def _cross_reference(data, portfolio_names, out):
    if portfolio_names is None:
        out.append(finding(
            WARNING, "crossref.unchecked", "$",
            "no --portfolio supplied; opportunity/metric name references were NOT "
            "cross-checked against a portfolio", None,
            "Re-run with --portfolio <portfolio.json> to verify every referenced name."))
        return
    opps, metrics = portfolio_names

    # metric names may be computed/expression metrics absent from input_data -> WARN
    opt = data.get("optimization")
    if isinstance(opt, dict):
        obj = opt.get("objective_metric_name")
        if isinstance(obj, str) and obj.strip() and obj not in metrics:
            out.append(finding(
                WARNING, "crossref.objective_metric", "$.optimization.objective_metric_name",
                f"objective metric '{obj}' was not found among the portfolio's input/master "
                "metrics (it may be a computed/expression metric)", obj,
                "Confirm it is a valid model metric name."))
    for i, lim in enumerate(data.get("metric_limits") or []):
        if isinstance(lim, dict):
            mname = lim.get("metric_name")
            if isinstance(mname, str) and mname not in metrics:
                out.append(finding(
                    WARNING, "crossref.limit_metric", f"$.metric_limits[{i}].metric_name",
                    f"metric_limit metric '{mname}' was not found among the portfolio's "
                    "input/master metrics (it may be a computed/expression metric)", mname,
                    "Confirm it is a valid model metric name."))

    # opportunity names are fully enumerable -> HARD
    for i, s in enumerate(data.get("opportunity_selections") or []):
        if isinstance(s, dict):
            _ref_check(s.get("opportunity_name"), opps,
                       f"$.opportunity_selections[{i}].opportunity_name",
                       "crossref.selection_opportunity", out,
                       what="opportunity", hint="Match an opportunity defined in the portfolio.")
    sc = data.get("selection_constraints")
    if isinstance(sc, dict):
        for i, lim in enumerate(sc.get("opportunity_limits") or []):
            if isinstance(lim, dict):
                _ref_check(lim.get("opportunity_name"), opps,
                           f"$.selection_constraints.opportunity_limits[{i}].opportunity_name",
                           "crossref.constraint_opportunity", out,
                           what="opportunity", hint="Match an opportunity defined in the portfolio.")
    sd = data.get("selection_dependency")
    if isinstance(sd, dict):
        for i, d in enumerate(sd.get("dependencies") or []):
            if isinstance(d, dict):
                _ref_check(d.get("dependent_opportunity"), opps,
                           f"$.selection_dependency.dependencies[{i}].dependent_opportunity",
                           "crossref.dep_dependent", out,
                           what="dependent opportunity", hint="Match a portfolio opportunity.")
                _ref_check(d.get("independent_opportunity"), opps,
                           f"$.selection_dependency.dependencies[{i}].independent_opportunity",
                           "crossref.dep_independent", out,
                           what="independent opportunity", hint="Match a portfolio opportunity.")
    sg = data.get("selection_group")
    if isinstance(sg, dict):
        for i, g in enumerate(sg.get("groups") or []):
            if isinstance(g, dict):
                for m, mem in enumerate(g.get("members") or []):
                    if isinstance(mem, dict):
                        _ref_check(mem.get("opportunity_name"), opps,
                                   f"$.selection_group.groups[{i}].members[{m}].opportunity_name",
                                   "crossref.group_member", out,
                                   what="member opportunity", hint="Match a portfolio opportunity.")


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
    ap = argparse.ArgumentParser(description="Validate a QPortfolio scenario JSON file.")
    ap.add_argument("file", help="path to the scenario JSON file")
    ap.add_argument("--schema", help="explicit path to scenario.schema.json")
    ap.add_argument("--portfolio", help="path to the companion portfolio.json for name cross-ref")
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
        _emit_env_error(args.format, "no scenario.schema.json found (server copy or bundled)")
        return 3
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        _emit_env_error(args.format, f"cannot load schema {schema_path}: {e}")
        return 3

    # Optional portfolio for cross-reference. A bad/unreadable portfolio downgrades
    # to a warning (cross-ref skipped) rather than failing the scenario validation.
    portfolio_names = None
    portfolio_note = None
    if args.portfolio:
        ppath = Path(args.portfolio)
        try:
            ptext = ppath.read_text(encoding="utf-8")
            pdata = json.loads(ptext, parse_constant=_reject_nonfinite)
            portfolio_names = extract_portfolio_names(pdata)
        except (OSError, ValueError) as e:
            portfolio_note = f"could not load --portfolio {ppath} for cross-ref: {e}"

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

    semantic = semantic_checks(data, args.strict_nulls, portfolio_names)
    if portfolio_note:
        semantic.insert(0, finding(
            WARNING, "crossref.portfolio_unreadable", "$", portfolio_note, None,
            "Fix the portfolio path/content to enable cross-reference checks."))
    hard = [f for f in semantic if f["severity"] == ERROR]
    warns = [f for f in semantic if f["severity"] == WARNING]

    # cross-schema drift note (server vs bundled)
    drift = None
    if source == "server-in-repo":
        bundled = Path(__file__).resolve().parent.parent / "schemas" / "scenario.schema.json"
        if bundled.is_file() and _sha256(bundled) != _sha256(schema_path):
            drift = "bundled schema differs from the in-repo server schema; run sync_schema.py"

    ok = not schema_errors and not hard
    result = {
        "ok": ok,
        "schema_path_used": str(schema_path),
        "schema_source": source,
        "portfolio_path_used": str(Path(args.portfolio)) if args.portfolio else None,
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
    if result.get("portfolio_path_used"):
        print(f"  portfolio={result['portfolio_path_used']}")
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
