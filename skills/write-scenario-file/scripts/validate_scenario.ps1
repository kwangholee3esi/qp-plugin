# PowerShell fallback validator for a QPortfolio Portable JSON *scenario* file.
# Used only when Python is unavailable; mirrors validate_scenario.py (the source
# of truth) - same CLI, same exit codes, same JSON output contract.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File validate_scenario.ps1 `
#       <file.json> [--schema PATH] [--portfolio PATH] [--format json|text] [--strict-nulls]
#
# Exit codes: 0 valid | 1 invalid | 2 io/parse error | 3 environment error.

. (Join-Path $PSScriptRoot 'qp_validation_common.ps1')

$ExpectedFileType = 'QPortfolio Scenario Data'

function New-StringSet { return , (New-Object 'System.Collections.Generic.HashSet[string]') }

# Scenario-specific reference message ("...not defined in the portfolio").
function Invoke-RefCheck($name, $valid, $path, $check, $out, $what, $hint) {
    if (($name -is [string]) -and (-not $valid.Contains($name))) {
        [void]$out.Add((New-Finding $SevError $check $path `
                    "references $what '$name' which is not defined in the portfolio" $name $hint))
    }
}

# extract_portfolio_names: (opportunity names, metric names) from a portfolio doc.
function Get-PortfolioNames($portfolio) {
    $opps = New-StringSet
    $metrics = New-StringSet
    if (Test-IsObject $portfolio) {
        foreach ($section in @('input_data', 'master_data')) {
            foreach ($opp in (Get-OpportunityOutcomes (Get-Prop $portfolio $section))) {
                if (-not (Test-IsObject $opp)) { continue }
                $name = Get-Prop $opp 'opportunity_name'
                if ($name -is [string]) { [void]$opps.Add($name) }
                $outcomes = Get-Prop $opp 'outcomes'
                if (Test-IsArray $outcomes) {
                    foreach ($oc in $outcomes) {
                        if (-not (Test-IsObject $oc)) { continue }
                        $mvs = Get-Prop $oc 'metric_values'
                        if (Test-IsArray $mvs) {
                            foreach ($mv in $mvs) {
                                if (Test-IsObject $mv) {
                                    $mn = Get-Prop $mv 'metric_name'
                                    if ($mn -is [string]) { [void]$metrics.Add($mn) }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    return @{ opps = $opps; metrics = $metrics }
}

function Add-SettingsChecks($settings, $out) {
    if ($null -eq $settings) {
        [void]$out.Add((New-Finding $SevWarning 'settings.missing' '$.settings' `
                    "scenario has no settings block; a scenario_name is recommended" $null 'Add settings.scenario_name to identify the scenario.'))
    }
}

function Add-OptimizationChecks($opt, $out) {
    if (-not (Test-IsObject $opt)) { return }
    $obj = Get-Prop $opt 'objective_metric_name'
    if ($null -eq $obj) {
        [void]$out.Add((New-Finding $SevWarning 'optimization.objective_missing' '$.optimization.objective_metric_name' `
                    "optimization block has no objective_metric_name" $obj 'Name the metric to optimize, e.g. an NPV metric.'))
    }
}

function Add-MetricLimitChecks($limits, $settings, $out) {
    if (-not (Test-IsArray $limits)) { return }
    $softEnabled = (Test-IsObject $settings) -and (Test-IsTrue (Get-Prop $settings 'enable_soft_constraints'))
    $i = 0
    foreach ($lim in $limits) {
        if (-not (Test-IsObject $lim)) { $i++; continue }
        $path = "`$.metric_limits[$i]"
        $mname = Get-Prop $lim 'metric_name'
        # limit_type is required by the schema, which reports a missing one as an
        # error; a second WARNING here would report the same defect twice.
        if ((Test-IsTrue (Get-Prop $lim 'soft')) -and (-not $softEnabled)) {
            [void]$out.Add((New-Finding $SevWarning 'metric_limit.soft_disabled' "$path.soft" `
                        "metric_limit '$(Format-PyStr $mname)' is soft but settings.enable_soft_constraints is not true" `
                        $null 'Set settings.enable_soft_constraints true, or make the limit hard.'))
        }
        $i++
    }
}

function Add-OpportunitySelectionChecks($sel, $out) {
    if (-not (Test-IsArray $sel)) { return }
    $seen = New-StringSet
    $i = 0
    foreach ($s in $sel) {
        if (-not (Test-IsObject $s)) { $i++; continue }
        $path = "`$.opportunity_selections[$i]"
        $name = Get-Prop $s 'opportunity_name'
        if ($name -is [string]) {
            if ($seen.Contains($name)) {
                [void]$out.Add((New-Finding $SevError 'unique.selection_opportunity' "$path.opportunity_name" `
                            "duplicate opportunity_selections entry for '$name'" $name "List each opportunity's selections once."))
            }
            [void]$seen.Add($name)
        }
        $i++
    }
}

function Add-SelectionConstraintChecks($sc, $out) {
    if (-not (Test-IsObject $sc)) { return }
    $limits = Get-Prop $sc 'opportunity_limits'
    if (-not (Test-IsArray $limits)) { return }
    $i = 0
    foreach ($lim in $limits) {
        if (-not (Test-IsObject $lim)) { $i++; continue }
        $path = "`$.selection_constraints.opportunity_limits[$i]"
        $name = Get-Prop $lim 'opportunity_name'
        Invoke-LimitNumericChecks $lim $path $out "opportunity '$(Format-PyStr $name)'"
        $i++
    }
}

function Add-MustNotRatioCheck($d, $path, $out) {
    if ((Get-Prop $d 'type') -cne 'MustNot') { return }
    $needScale = Get-Prop $d 'need_scale'
    $fields = @()
    if ($null -ne (Get-Prop $d 'each_scale')) { $fields += 'each_scale' }
    if (Test-IsTrue (Get-Prop $d 'each_interest')) { $fields += 'each_interest' }
    if ((Test-IsNumber $needScale) -and ($needScale -ne 1)) { $fields += 'need_scale' }
    if (Test-IsTrue (Get-Prop $d 'need_interest')) { $fields += 'need_interest' }
    if ($fields.Count -eq 0) { return }
    $joined = $fields -join ', '
    [void]$out.Add((New-Finding $SevError 'selection_dep.must_not_ratio' $path `
                "a MustNot rule carries a ratio ($joined)" $joined 'A MustNot rule takes need_scale 1, no each_scale, and both interest flags false.'))
}

function Add-SelectionDependencyChecks($sd, $out) {
    if (-not (Test-IsObject $sd)) { return }
    $deps = Get-Prop $sd 'dependencies'
    if (-not (Test-IsArray $deps)) { return }
    $seenPairs = New-StringSet
    $i = 0
    foreach ($d in $deps) {
        if (-not (Test-IsObject $d)) { $i++; continue }
        $path = "`$.selection_dependency.dependencies[$i]"
        $dpd = Get-Prop $d 'dependent_opportunity'
        $ind = Get-Prop $d 'independent_opportunity'
        if (($ind -is [string]) -and ($ind -ceq $dpd)) {
            [void]$out.Add((New-Finding $SevWarning 'selection_dep.self' $path `
                        "dependent and independent opportunity are both '$ind'" $ind 'An opportunity should not depend on itself.'))
        }
        Add-MustNotRatioCheck $d $path $out
        if (($dpd -is [string]) -and ($ind -is [string])) {
            $key = "$dpd" + ([char]1) + "$ind"
            if ($seenPairs.Contains($key)) {
                [void]$out.Add((New-Finding $SevWarning 'selection_dep.duplicate_pair' $path `
                            "more than one rule for dependent '$dpd' / independent '$ind'" ([string[]]@($dpd, $ind)) 'Combine duplicate dependency rules for the same pair.'))
            }
            [void]$seenPairs.Add($key)
        }
        $i++
    }
}

function Add-SelectionGroupChecks($sg, $out) {
    if (-not (Test-IsObject $sg)) { return }
    $groups = Get-Prop $sg 'groups'
    $groupNames = New-StringSet
    if (Test-IsArray $groups) {
        $i = 0
        foreach ($g in $groups) {
            if (-not (Test-IsObject $g)) { $i++; continue }
            $gname = Get-Prop $g 'group_name'
            if ($gname -is [string]) { [void]$groupNames.Add($gname) }
            $i++
        }
    }
    $limits = Get-Prop $sg 'group_limits'
    if (Test-IsArray $limits) {
        $i = 0
        foreach ($lim in $limits) {
            if (-not (Test-IsObject $lim)) { $i++; continue }
            $path = "`$.selection_group.group_limits[$i]"
            $gname = Get-Prop $lim 'group_name'
            if ($gname -is [string]) {
                if (($groupNames.Count -gt 0) -and (-not $groupNames.Contains($gname))) {
                    [void]$out.Add((New-Finding $SevError 'ref.group_limit' "$path.group_name" `
                                "group_limits references group '$gname' with no matching group" $gname 'Match an existing group_name.'))
                }
            }
            Invoke-LimitNumericChecks $lim $path $out "group '$(Format-PyStr $gname)'"
            $i++
        }
    }
}

function Add-CrossReferenceChecks($data, $portfolioNames, $out) {
    if ($null -eq $portfolioNames) {
        [void]$out.Add((New-Finding $SevWarning 'crossref.unchecked' '$' `
                    "no --portfolio supplied; opportunity/metric name references were NOT cross-checked against a portfolio" `
                    $null 'Re-run with --portfolio <portfolio.json> to verify every referenced name.'))
        return
    }
    $opps = $portfolioNames.opps
    $metrics = $portfolioNames.metrics

    $opt = Get-Prop $data 'optimization'
    if (Test-IsObject $opt) {
        $obj = Get-Prop $opt 'objective_metric_name'
        if (($obj -is [string]) -and (-not [string]::IsNullOrWhiteSpace($obj)) -and (-not $metrics.Contains($obj))) {
            [void]$out.Add((New-Finding $SevWarning 'crossref.objective_metric' '$.optimization.objective_metric_name' `
                        "objective metric '$obj' was not found among the portfolio's input/master metrics (it may be a computed/expression metric)" `
                        $obj 'Confirm it is a valid model metric name.'))
        }
    }
    $mlimits = Get-Prop $data 'metric_limits'
    if (Test-IsArray $mlimits) {
        $i = 0
        foreach ($lim in $mlimits) {
            if (Test-IsObject $lim) {
                $mname = Get-Prop $lim 'metric_name'
                if (($mname -is [string]) -and (-not $metrics.Contains($mname))) {
                    [void]$out.Add((New-Finding $SevWarning 'crossref.limit_metric' "`$.metric_limits[$i].metric_name" `
                                "metric_limit metric '$mname' was not found among the portfolio's input/master metrics (it may be a computed/expression metric)" `
                                $mname 'Confirm it is a valid model metric name.'))
                }
            }
            $i++
        }
    }

    $sels = Get-Prop $data 'opportunity_selections'
    if (Test-IsArray $sels) {
        $i = 0
        foreach ($s in $sels) {
            if (Test-IsObject $s) {
                Invoke-RefCheck (Get-Prop $s 'opportunity_name') $opps "`$.opportunity_selections[$i].opportunity_name" `
                    'crossref.selection_opportunity' $out 'opportunity' 'Match an opportunity defined in the portfolio.'
            }
            $i++
        }
    }
    $sc = Get-Prop $data 'selection_constraints'
    if (Test-IsObject $sc) {
        $climits = Get-Prop $sc 'opportunity_limits'
        if (Test-IsArray $climits) {
            $i = 0
            foreach ($lim in $climits) {
                if (Test-IsObject $lim) {
                    Invoke-RefCheck (Get-Prop $lim 'opportunity_name') $opps "`$.selection_constraints.opportunity_limits[$i].opportunity_name" `
                        'crossref.constraint_opportunity' $out 'opportunity' 'Match an opportunity defined in the portfolio.'
                }
                $i++
            }
        }
    }
    $sd = Get-Prop $data 'selection_dependency'
    if (Test-IsObject $sd) {
        $deps = Get-Prop $sd 'dependencies'
        if (Test-IsArray $deps) {
            $i = 0
            foreach ($d in $deps) {
                if (Test-IsObject $d) {
                    Invoke-RefCheck (Get-Prop $d 'dependent_opportunity') $opps "`$.selection_dependency.dependencies[$i].dependent_opportunity" `
                        'crossref.dep_dependent' $out 'dependent opportunity' 'Match a portfolio opportunity.'
                    Invoke-RefCheck (Get-Prop $d 'independent_opportunity') $opps "`$.selection_dependency.dependencies[$i].independent_opportunity" `
                        'crossref.dep_independent' $out 'independent opportunity' 'Match a portfolio opportunity.'
                }
                $i++
            }
        }
    }
    $sg = Get-Prop $data 'selection_group'
    if (Test-IsObject $sg) {
        $groups = Get-Prop $sg 'groups'
        if (Test-IsArray $groups) {
            $i = 0
            foreach ($g in $groups) {
                if (Test-IsObject $g) {
                    $members = Get-Prop $g 'members'
                    if (Test-IsArray $members) {
                        $m = 0
                        foreach ($mem in $members) {
                            if (Test-IsObject $mem) {
                                Invoke-RefCheck (Get-Prop $mem 'opportunity_name') $opps "`$.selection_group.groups[$i].members[$m].opportunity_name" `
                                    'crossref.group_member' $out 'member opportunity' 'Match a portfolio opportunity.'
                            }
                            $m++
                        }
                    }
                }
                $i++
            }
        }
    }
}

function Get-ScenarioSemantic($data, $strict, $portfolioNames) {
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

    Add-SettingsChecks (Get-Prop $data 'settings') $out
    Add-OptimizationChecks (Get-Prop $data 'optimization') $out
    Add-MetricLimitChecks (Get-Prop $data 'metric_limits') (Get-Prop $data 'settings') $out
    $null = Add-OpportunitySelectionChecks (Get-Prop $data 'opportunity_selections') $out
    $null = Add-SelectionConstraintChecks (Get-Prop $data 'selection_constraints') $out
    $null = Add-SelectionDependencyChecks (Get-Prop $data 'selection_dependency') $out
    $null = Add-SelectionGroupChecks (Get-Prop $data 'selection_group') $out

    Add-CrossReferenceChecks $data $portfolioNames $out

    if ($strict) { Invoke-ExplicitNullChecks $data '$' $out }
    return $out
}

exit (Invoke-QpValidation $args 'scenario.schema.json' $PSScriptRoot 'Get-ScenarioSemantic' $true)
