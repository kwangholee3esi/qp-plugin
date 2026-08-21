# PowerShell fallback validator for a QPortfolio Portable JSON *model* file.
# Used only when Python is unavailable; mirrors validate_model.py (the source
# of truth) - same CLI, same exit codes, same JSON output contract.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File validate_model.ps1 `
#       <file.json> [--schema PATH] [--format json|text] [--strict-nulls]
#
# Exit codes: 0 valid | 1 invalid | 2 io/parse error | 3 environment error.

. (Join-Path $PSScriptRoot 'qp_validation_common.ps1')

$ExpectedFileType = 'QPortfolio Model'

# The ten derivation types (lowercase). Mirrors the `derived` enum in the
# schema and MetricFunctions.cs (last-'#' suffix match, case-insensitive).
$DerivedTypes = New-Object 'System.Collections.Generic.HashSet[string]'
foreach ($t in @('pt', 'disc', 'inf', 'cumsum', 'cumsumdisc', 'cumsuminf',
        'total', 'totaldisc', 'totalinf', 'maxat')) { [void]$DerivedTypes.Add($t) }

# The closed set of 26 expression functions with @(min_args, max_args);
# $null max = unbounded. Source of truth: server
# Esi.Sp.Parsing/Converter/FunctionDef.cs — keep in sync when it changes.
$Functions = @{
    'getmetricvalue'          = @(1, 2)
    'getdiscounted'           = @(1, 2)
    'getinflated'             = @(1, 2)
    'getcumulative'           = @(1, 3)
    'getcumulativeinflated'   = @(1, 3)
    'getmaxacrosstime'        = @(1, 3)
    'getirr'                  = @(1, 3)
    'getcumulativediscounted' = @(1, 4)
    'getcurrenttime'          = @(0, 0)
    'getattributevalue'       = @(1, 1)
    'sum'                     = @(1, $null)
    'abs'                     = @(1, 1)
    'min'                     = @(2, 2)
    'max'                     = @(2, 2)
    'if'                      = @(3, 3)
    'npv'                     = @(2, $null)
    'pt'                      = @(1, 1)
    'disc'                    = @(1, 1)
    'inf'                     = @(1, 1)
    'cumsum'                  = @(1, 1)
    'cumsumdisc'              = @(1, 1)
    'cumsuminf'               = @(1, 1)
    'total'                   = @(1, 1)
    'totaldisc'               = @(1, 1)
    'totalinf'                = @(1, 1)
    'maxat'                   = @(1, 1)
}

$AttrCallRe = [regex]'(?i)getattributevalue\(\s*\$\{([^}]*)\}\s*\)'
$RefRe = [regex]'\$\{([^}]*)\}'
$UnsignedExpRe = [regex]'\d+(\.\d+)?[eE]\d'
$NumberRe = [regex]'^\d+(\.\d+)?([eE][+-]?\d+)?'
$IdentRe = [regex]'^[A-Za-z_][A-Za-z0-9_]*'
# Non-linearity signals (conservative): non-linear functions, and a
# product/quotient of two metric references (linear only when one side is
# master data). Used for the derived-metric guidance warning.
$NonlinearCallRe = [regex]'(?i)(?<![A-Za-z0-9_])(if|min|max|abs|getirr|getmaxacrosstime|maxat)\('
$RefProductRe = [regex]'\$\{([^}]*)\}\s*[*/]\s*(?=\$\{([^}]*)\})'

# Name handling (NormalName + CaseIgnoreName parity).
function Get-NameNorm($s) { return ([regex]::Replace($s, "[\t\r\n]", ' ')).Trim() }
function Get-ModelNameKey($s) { return (Get-NameNorm $s).ToLowerInvariant() }

# Return the derivation type after the LAST '#', or $null (case-insensitive).
function Get-DerivedSuffix($name) {
    $norm = Get-NameNorm $name
    $idx = $norm.LastIndexOf('#')
    if ($idx -lt 0) { return $null }
    $suffix = $norm.Substring($idx + 1)
    if ($DerivedTypes.Contains($suffix.ToLowerInvariant())) { return $suffix }
    return $null
}

# Blank out double-quoted string literals ("" escapes a quote). Returns
# @{ san = <sanitized>; unterminated = <bool> }; on an unterminated literal
# the rest of the string is dropped.
function Get-BlankedFormula($src) {
    $sb = New-Object System.Text.StringBuilder
    $i = 0
    $unterminated = $false
    while ($i -lt $src.Length) {
        if ($src[$i] -eq '"') {
            $j = $i + 1
            $closed = $false
            while ($j -lt $src.Length) {
                if ($src[$j] -eq '"') {
                    if (($j + 1 -lt $src.Length) -and ($src[$j + 1] -eq '"')) { $j += 2; continue }
                    $closed = $true
                    break
                }
                $j++
            }
            if (-not $closed) { $unterminated = $true; break }
            [void]$sb.Append('1')
            $i = $j + 1
        } else {
            [void]$sb.Append($src[$i])
            $i++
        }
    }
    return @{ san = $sb.ToString(); unterminated = $unterminated }
}

# Comparison key of a reference for master-data lookup: a derived reference
# resolves to its origin metric.
function Get-RefMdKey($raw) {
    $norm = Get-NameNorm $raw
    if ($null -ne (Get-DerivedSuffix $raw)) {
        return $norm.Substring(0, $norm.LastIndexOf('#')).ToLowerInvariant()
    }
    return $norm.ToLowerInvariant()
}

# Conservative heuristic: does this formula look non-linear? Linear = only
# +/- and multiplication/division by constants or master-data metrics.
function Test-LooksNonlinear($src, $masterdataKeys) {
    $b = Get-BlankedFormula $src
    $san = $b.san
    if ($san.IndexOf('^') -ge 0) { return $true }
    if ($NonlinearCallRe.IsMatch($san)) { return $true }
    foreach ($m in $RefProductRe.Matches($san)) {
        if ((-not $masterdataKeys.Contains((Get-RefMdKey $m.Groups[1].Value))) -and
            (-not $masterdataKeys.Contains((Get-RefMdKey $m.Groups[2].Value)))) { return $true }
    }
    return $false
}

function Get-ArityDesc($mn, $mx) {
    if ($mx -eq $mn) { return "exactly $mn" }
    if ($null -eq $mx) { return "at least $mn" }
    return "$mn to $mx"
}

# Tokenize one formula string and emit findings in a fixed phase order
# (mirrored 1:1 from validate_model.py _check_formula — keep in lockstep).
function Add-FormulaChecks($src, $path, $declaredMetrics, $attrsDeclared, $out) {
    # Phase 1: blank out string literals ("" escapes a quote).
    $blanked = Get-BlankedFormula $src
    $san = $blanked.san
    if ($blanked.unterminated) {
        [void]$out.Add((New-Finding $SevError 'formula.unbalanced' $path `
                    'unterminated string literal' $src 'Balance quotes, braces and parentheses.'))
    }

    # Phase 2: macros are Excel-import only.
    if ([regex]::IsMatch($san, '(?i)flaguptomax')) {
        [void]$out.Add((New-Finding $SevError 'formula.macro_unsupported' $path `
                    'macro function FlagUpToMax is not supported in JSON model files' $src `
                    'Break the macro into explicit metrics/expressions instead.'))
    }

    # Phase 3: GetAttributeValue(${...}) resolves against attributes; every
    # remaining ${...} is a metric reference (rewrite order per the importer).
    foreach ($m in $AttrCallRe.Matches($san)) {
        $attr = $m.Groups[1].Value
        if (($null -ne $attrsDeclared) -and (-not $attrsDeclared.Contains((Get-ModelNameKey $attr)))) {
            [void]$out.Add((New-Finding $SevWarning 'formula.attr_undeclared' $path `
                        ("GetAttributeValue references attribute '" + $attr + "' not declared in this file's attributes (the importer silently creates it)") `
                        $attr 'Declare the attribute or fix the name.'))
        }
    }
    $san = $AttrCallRe.Replace($san, '1')

    foreach ($m in $RefRe.Matches($san)) {
        $raw = $m.Groups[1].Value
        $norm = Get-NameNorm $raw
        $suffix = Get-DerivedSuffix $raw
        if ($null -ne $suffix) {
            $origin = $norm.Substring(0, $norm.LastIndexOf('#'))
            if (-not $declaredMetrics.Contains($origin.ToLowerInvariant())) {
                [void]$out.Add((New-Finding $SevError 'formula.derived_origin_undefined' $path `
                            ("derived reference '`${" + $raw + "}' has origin '" + $origin + "' which is not defined in this file") `
                            $raw 'Declare the origin metric in this file.'))
            }
        } elseif (-not $declaredMetrics.Contains($norm.ToLowerInvariant())) {
            [void]$out.Add((New-Finding $SevError 'formula.ref_undefined' $path `
                        ("reference '`${" + $raw + "}' does not match a metric defined in this file") `
                        $raw 'Every ${...} must name a metric declared in this file''s metrics.'))
        }
    }
    $san = $RefRe.Replace($san, '1')

    # Phase 4: an unmatched "${" means an unclosed reference.
    if ($san.IndexOf('${') -ge 0) {
        [void]$out.Add((New-Finding $SevError 'formula.unbalanced' $path `
                    'unclosed ${...} reference' $src 'Balance quotes, braces and parentheses.'))
    }

    # Phase 5: the grammar requires a signed exponent (1e+5, never 1e5).
    if ($UnsignedExpRe.IsMatch($san)) {
        [void]$out.Add((New-Finding $SevWarning 'formula.exponent_unsigned' $path `
                    'scientific-notation literal without a signed exponent (write 1e+5, not 1e5)' `
                    $src 'Add an explicit + or - to the exponent.'))
    }

    # Phase 6: linear scan — function frames, argument counts, bare identifiers.
    $stack = New-Object System.Collections.ArrayList  # frames: @(name_or_null, commas, has_content)
    $unbalanced = $false
    $discarded = $false
    $i = 0
    while ($i -lt $san.Length) {
        $c = $san[$i]
        if (($c -eq ' ') -or ($c -eq "`t")) {
            $i++
        } elseif ([char]::IsDigit($c)) {
            $m = $NumberRe.Match($san.Substring($i))
            if ($stack.Count -gt 0) { $stack[$stack.Count - 1][2] = $true }
            $i += $m.Length
        } elseif ([char]::IsLetter($c) -or ($c -eq '_')) {
            $m = $IdentRe.Match($san.Substring($i))
            $ident = $m.Value
            $j = $i + $ident.Length
            if (($j -lt $san.Length) -and ($san[$j] -eq '(')) {
                if ($stack.Count -gt 0) { $stack[$stack.Count - 1][2] = $true }
                [void]$stack.Add(@($ident, 0, $false))
                $i = $j + 1
            } else {
                $l = $ident.ToLowerInvariant()
                if (($l -ne 'true') -and ($l -ne 'false')) {
                    [void]$out.Add((New-Finding $SevError 'formula.bare_identifier' $path `
                                ("bare identifier '" + $ident + "' - metric references must be wrapped in `${...}") `
                                $ident 'Write ${Name} to reference a metric.'))
                }
                if ($stack.Count -gt 0) { $stack[$stack.Count - 1][2] = $true }
                $i = $j
            }
        } elseif ($c -eq '(') {
            if ($stack.Count -gt 0) { $stack[$stack.Count - 1][2] = $true }
            [void]$stack.Add(@($null, 0, $false))
            $i++
        } elseif ($c -eq ')') {
            if ($stack.Count -eq 0) {
                $unbalanced = $true
            } else {
                $fr = $stack[$stack.Count - 1]
                $stack.RemoveAt($stack.Count - 1)
                if ($null -ne $fr[0]) {
                    $fnArgs = if ($fr[2]) { $fr[1] + 1 } else { 0 }
                    $lname = ([string]$fr[0]).ToLowerInvariant()
                    if ($lname -eq 'flaguptomax') {
                        # already reported as a macro
                    } elseif (-not $Functions.ContainsKey($lname)) {
                        [void]$out.Add((New-Finding $SevError 'formula.unknown_function' $path `
                                    ("unknown function '" + $fr[0] + "'") $fr[0] `
                                    'Only the 26 QPortfolio expression functions are supported (see REFERENCE.md).'))
                    } else {
                        $mn = $Functions[$lname][0]
                        $mx = $Functions[$lname][1]
                        if (($fnArgs -lt $mn) -or (($null -ne $mx) -and ($fnArgs -gt $mx))) {
                            [void]$out.Add((New-Finding $SevError 'formula.arity' $path `
                                        ("" + $fr[0] + " takes " + (Get-ArityDesc $mn $mx) + " argument(s), got " + $fnArgs) `
                                        $fr[0] 'Fix the argument count.'))
                        }
                    }
                }
                if ($stack.Count -gt 0) { $stack[$stack.Count - 1][2] = $true }
            }
            $i++
        } elseif ($c -eq ',') {
            if ($stack.Count -gt 0) { $stack[$stack.Count - 1][1] = $stack[$stack.Count - 1][1] + 1 }
            $i++
        } elseif ('+-*/^=<>'.IndexOf($c) -ge 0) {
            $i++
        } elseif (($c -eq '&') -or ($c -eq '%')) {
            $discarded = $true
            if ($stack.Count -gt 0) { $stack[$stack.Count - 1][2] = $true }
            $i++
        } else {
            $i++  # unknown character; the server parser is the real gate
        }
    }

    # Phase 7-9.
    if (($stack.Count -gt 0) -or $unbalanced) {
        [void]$out.Add((New-Finding $SevError 'formula.unbalanced' $path `
                    'unbalanced parentheses' $src 'Balance quotes, braces and parentheses.'))
    }
    if ($discarded) {
        [void]$out.Add((New-Finding $SevWarning 'formula.discarded_operator' $path `
                    "'&' or '%' is parsed but silently discarded by the calculator" $src `
                    'Remove it; concatenation and percent are not supported.'))
    }
    if ([regex]::IsMatch($san, '(?i)getirr\(')) {
        [void]$out.Add((New-Finding $SevWarning 'formula.getirr_optimization' $path `
                    'GetIRR imports and calculates, but any optimization of a scenario using it will fail' `
                    $src 'Avoid GetIRR in metrics used by optimization.'))
    }
}

function Add-BlankNameCheck($name, $path, $out) {
    if (($name -is [string]) -and ($name.Length -gt 0) -and ((Get-NameNorm $name).Length -eq 0)) {
        [void]$out.Add((New-Finding $SevError 'name.blank' $path `
                    'name is blank after normalization (whitespace only)' $name 'Use a non-empty name.'))
    }
}

function Add-MetricChecks($metric, $i, $declared, $masterdata, $seen, $attrsDeclared, $out) {
    $path = "`$.metrics[$i]"
    $name = Get-Prop $metric 'metric_name'
    $label = if ($name -is [string]) { $name } else { "metrics[$i]" }

    if ($name -is [string]) {
        $key = Get-ModelNameKey $name
        if (($name.Length -gt 0) -and ($key.Length -eq 0)) {
            [void]$out.Add((New-Finding $SevError 'name.blank' "$path.metric_name" `
                        'name is blank after normalization (whitespace only)' $name 'Use a non-empty name.'))
        } elseif ($key.Length -gt 0) {
            if ($seen.ContainsKey($key)) {
                [void]$out.Add((New-Finding $SevError 'metric.duplicate_name' "$path.metric_name" `
                            ("metric name '" + $name + "' duplicates the metric at index " + $seen[$key] + " (names are compared case-insensitively)") `
                            $name 'Metric names must be unique case-insensitively.'))
            } else {
                $seen[$key] = $i
            }
            $suffix = Get-DerivedSuffix $name
            if ($null -ne $suffix) {
                [void]$out.Add((New-Finding $SevError 'metric.reserved_derived_name' "$path.metric_name" `
                            ("metric name '" + $name + "' ends in '#" + $suffix + "' which is reserved for derived metrics") `
                            $name "List the derivation type under the origin metric's derived instead."))
            }
        }
    }

    $mtype = Get-Prop $metric 'metric_type'
    $computed = ($mtype -is [string]) -and ($mtype -ceq 'Computed')
    $exprs = Get-Prop $metric 'expressions'
    $hasExprs = (Test-IsArray $exprs) -and (@($exprs).Count -gt 0)
    if ($hasExprs -and (-not $computed)) {
        [void]$out.Add((New-Finding $SevError 'metric.expressions_not_computed' "$path.expressions" `
                    ("metric '" + $label + "' carries expressions but is not Computed") $mtype `
                    'Set metric_type to Computed, or remove the expressions.'))
    }
    if ($computed -and (-not $hasExprs)) {
        [void]$out.Add((New-Finding $SevError 'metric.computed_no_expressions' "$path.expressions" `
                    ("computed metric '" + $label + "' has no expressions") $null `
                    'A Computed metric needs at least one expression.'))
    }

    $level = Get-Prop $metric 'level'
    if ($computed -and ($null -eq $level)) {
        [void]$out.Add((New-Finding $SevWarning 'level.missing' "$path.level" `
                    ("computed metric '" + $label + "' does not state its level") $null `
                    'State level explicitly (Outcome, Opportunity, Group or Scenario); the effective default is ambiguous.'))
    }
    $levelIsGroup = ($level -is [string]) -and ($level -ceq 'Group')
    $levelIsScenario = ($level -is [string]) -and ($level -ceq 'Scenario')
    $levelIsOpportunity = ($level -is [string]) -and ($level -ceq 'Opportunity')

    $groupBy = Get-Prop $metric 'group_by'
    $hasGroupBy = (Test-IsArray $groupBy) -and (@($groupBy).Count -gt 0)
    if ($levelIsGroup -and (-not $hasGroupBy)) {
        [void]$out.Add((New-Finding $SevError 'metric.group_missing_group_by' "$path.group_by" `
                    ("Group-level metric '" + $label + "' has no group_by") $null `
                    'Name the attribute(s) whose values define the groups.'))
    }
    if ($hasGroupBy -and (-not $levelIsGroup)) {
        [void]$out.Add((New-Finding $SevWarning 'metric.group_by_ignored' "$path.group_by" `
                    ("group_by on metric '" + $label + "' is ignored when level is not Group") $level `
                    'Set level to Group or remove group_by.'))
    }

    # Derived-metric guidance: derived transforms are recommended only for
    # linear, Interest-scaled origins (elsewhere the derived value may differ
    # from the equivalent explicit expression).
    $derived = Get-Prop $metric 'derived'
    $hasDerived = (Test-IsArray $derived) -and (@($derived).Count -gt 0)
    $scaleBy = Get-Prop $metric 'scale_by'
    if ($hasDerived -and ($scaleBy -is [string]) -and ($scaleBy -ceq 'Instance')) {
        [void]$out.Add((New-Finding $SevWarning 'derived.instance_scaled' "$path.derived" `
                    ("metric '" + $label + "' has derived metrics but is scaled by Instance; the derived values may differ from an explicit computed metric") `
                    'Instance' 'Derived metrics are recommended only for linear, Interest-scaled origins; write an explicit computed metric instead.'))
    }
    if ($hasDerived -and $computed -and (Test-IsArray $exprs)) {
        $nonlinear = $false
        foreach ($ex in $exprs) {
            if (-not (Test-IsObject $ex)) { continue }
            foreach ($field in @('formula', 'first_period_formula')) {
                $v = Get-Prop $ex $field
                if (($v -is [string]) -and (Test-LooksNonlinear $v $masterdata)) { $nonlinear = $true }
            }
        }
        if ($nonlinear) {
            [void]$out.Add((New-Finding $SevWarning 'derived.nonlinear_origin' "$path.derived" `
                        ("metric '" + $label + "' has derived metrics but its expressions look non-linear; the derived value may differ from the equivalent explicit expression") `
                        $null 'Derived metrics are recommended only for linear, Interest-scaled origins; write an explicit computed metric instead.'))
        }
    }

    if (-not (Test-IsArray $exprs)) { return }
    $seenOrders = @{}
    $j = 0
    foreach ($ex in $exprs) {
        if (-not (Test-IsObject $ex)) { $j++; continue }
        $expath = "$path.expressions[$j]"
        $order = Get-Prop $ex 'order'
        $eff = if (Test-IsInt $order) { $order } else { 0 }
        if ($seenOrders.ContainsKey($eff)) {
            [void]$out.Add((New-Finding $SevWarning 'expr.order_duplicate' "$expath.order" `
                        ("order " + $eff + " is reused (also at expressions[" + $seenOrders[$eff] + "])") $eff `
                        'Give each expression of a metric a distinct order (lower evaluates first).'))
        } else {
            $seenOrders[$eff] = $j
        }
        $criteria = Get-Prop $ex 'criteria'
        if ((Test-IsArray $criteria) -and (@($criteria).Count -gt 0)) {
            if ($levelIsScenario) {
                [void]$out.Add((New-Finding $SevWarning 'criteria.scenario_level' "$expath.criteria" `
                            'criteria on a Scenario-level metric: scenario-level expressions cannot be filtered' $null `
                            'Move the metric to Outcome/Opportunity/Group level or drop the criteria.'))
            }
            $k = 0
            foreach ($crit in $criteria) {
                if (-not (Test-IsObject $crit)) { $k++; continue }
                $cpath = "$expath.criteria[$k]"
                $oc = Get-Prop $crit 'outcome'
                if ($levelIsOpportunity -and (Test-IsArray $oc) -and (@($oc).Count -gt 0)) {
                    [void]$out.Add((New-Finding $SevWarning 'criteria.outcome_on_opportunity' "$cpath.outcome" `
                                'outcome filter on an Opportunity-level metric: only Outcome-level expressions can filter by outcome' $null `
                                'Use level Outcome for outcome-filtered expressions.'))
                }
                $a = Get-Prop $crit 'attribute'
                if (($a -is [string]) -and ($null -ne $attrsDeclared) -and (-not $attrsDeclared.Contains((Get-ModelNameKey $a)))) {
                    [void]$out.Add((New-Finding $SevWarning 'criteria.attribute_undeclared' "$cpath.attribute" `
                                ("criterion attribute '" + $a + "' is not declared in this file's attributes (the importer silently creates it)") `
                                $a 'Declare the attribute or fix the name.'))
                }
                $k++
            }
        }
        foreach ($field in @('formula', 'first_period_formula')) {
            $v = Get-Prop $ex $field
            if ($v -is [string]) {
                Add-FormulaChecks $v "$expath.$field" $declared $attrsDeclared $out
            }
        }
        $j++
    }
}

function Get-ModelSemantic($data, $strict, $portfolioNames) {
    $out = New-Object System.Collections.ArrayList
    if (-not (Test-IsObject $data)) {
        [void]$out.Add((New-Finding $SevError 'root.type' '$' 'document root is not a JSON object'))
        return $out
    }

    $meta = Get-Prop $data 'metadata'
    if (Test-IsObject $meta) {
        $ft = Get-Prop $meta 'qp_file_type'
        if (-not (($ft -is [string]) -and [string]::Equals($ft, $ExpectedFileType, [System.StringComparison]::Ordinal))) {
            [void]$out.Add((New-Finding $SevError 'metadata.qp_file_type' '$.metadata.qp_file_type' `
                        "qp_file_type must be exactly '$ExpectedFileType', got $(ConvertTo-PyRepr $ft)" `
                        $ft "Set metadata.qp_file_type to `"$ExpectedFileType`"."))
        }
        $ver = Get-Prop $meta 'qp_version'
        if (($null -ne $ver) -and (-not ((Test-IsNumber $ver) -or (Test-IsBool $ver)))) {
            [void]$out.Add((New-Finding $SevWarning 'metadata.qp_version' '$.metadata.qp_version' `
                        "qp_version should be a number, got $(ConvertTo-PyRepr $ver)" $ver 'Use a numeric version like 4.5.'))
        }
    }

    # Attribute names declared by THIS file ($null = file carries no attributes
    # section, so undeclared-attribute warnings are suppressed: the attribute
    # may live in a sibling file of the import or in the existing model).
    $attrs = Get-Prop $data 'attributes'
    $attrsDeclared = $null
    if (Test-IsArray $attrs) {
        $attrsDeclared = New-Object 'System.Collections.Generic.HashSet[string]'
        foreach ($a in $attrs) {
            if (Test-IsObject $a) {
                $an = Get-Prop $a 'attribute_name'
                if ($an -is [string]) { [void]$attrsDeclared.Add((Get-ModelNameKey $an)) }
            }
        }
    }

    $metrics = Get-Prop $data 'metrics'
    if (Test-IsArray $metrics) {
        if (@($metrics).Count -eq 0) {
            [void]$out.Add((New-Finding $SevWarning 'metrics.empty_deletes_computed' '$.metrics' `
                        'metrics is an empty list: importing this file deletes every computed metric of the model' `
                        $null 'Omit the metrics property entirely to leave metrics untouched.'))
        }
        $declared = New-Object 'System.Collections.Generic.HashSet[string]'
        $masterdata = New-Object 'System.Collections.Generic.HashSet[string]'
        foreach ($m in $metrics) {
            if (Test-IsObject $m) {
                $mn = Get-Prop $m 'metric_name'
                if ($mn -is [string]) {
                    $mk = Get-ModelNameKey $mn
                    if ($mk.Length -gt 0) { [void]$declared.Add($mk) }
                    $mt = Get-Prop $m 'metric_type'
                    if (($mt -is [string]) -and ($mt -ceq 'MasterData')) {
                        [void]$masterdata.Add($mk)
                    }
                }
            }
        }
        $seen = @{}
        $i = 0
        foreach ($metric in $metrics) {
            if (Test-IsObject $metric) {
                Add-MetricChecks $metric $i $declared $masterdata $seen $attrsDeclared $out
            }
            $i++
        }
    }

    if (Test-IsArray $attrs) {
        $i = 0
        foreach ($attr in $attrs) {
            if (-not (Test-IsObject $attr)) { $i++; continue }
            $path = "`$.attributes[$i]"
            Add-BlankNameCheck (Get-Prop $attr 'attribute_name') "$path.attribute_name" $out
            $chars = Get-Prop $attr 'characteristics'
            if (Test-IsArray $chars) {
                $j = 0
                foreach ($ch in $chars) {
                    if (Test-IsObject $ch) {
                        Add-BlankNameCheck (Get-Prop $ch 'characteristic_name') "$path.characteristics[$j].characteristic_name" $out
                    }
                    $j++
                }
            }
            $i++
        }
    }

    if ($strict) { Invoke-ExplicitNullChecks $data '$' $out }
    return $out
}

exit (Invoke-QpValidation $args 'model.schema.json' $PSScriptRoot 'Get-ModelSemantic' $false)
