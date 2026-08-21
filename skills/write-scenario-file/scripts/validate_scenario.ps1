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
        return
    }
    if (-not (Test-IsObject $settings)) { return }
    $name = Get-Prop $settings 'scenario_name'
    if (($name -is [string]) -and [string]::IsNullOrWhiteSpace($name)) {
        [void]$out.Add((New-Finding $SevWarning 'settings.scenario_name_blank' '$.settings.scenario_name' `
                    "scenario_name is blank" $name 'Give the scenario a meaningful, unique name.'))
    }
    $thr = Get-Prop $settings 'instance_selection_threshold'
    if ((Test-IsNumber $thr) -and (-not (($thr -ge 0) -and ($thr -le 1)))) {
        [void]$out.Add((New-Finding $SevWarning 'settings.threshold_range' '$.settings.instance_selection_threshold' `
                    "instance_selection_threshold ($(Format-Num $thr)) is outside the expected 0..1 range" $thr 'Use a fractional interest between 0 and 1.'))
    }
}

function Add-OptimizationChecks($opt, $out) {
    if (-not (Test-IsObject $opt)) { return }
    $obj = Get-Prop $opt 'objective_metric_name'
    if (-not (($obj -is [string]) -and (-not [string]::IsNullOrWhiteSpace($obj)))) {
        [void]$out.Add((New-Finding $SevWarning 'optimization.objective_missing' '$.optimization.objective_metric_name' `
                    "optimization block has no objective_metric_name" $obj 'Name the metric to optimize, e.g. an NPV metric.'))
    }
    $tp = Get-Prop $opt 'objective_time_period'
    if ((Test-IsInt $tp) -and ($tp -lt 0)) {
        [void]$out.Add((New-Finding $SevError 'optimization.objective_period_negative' '$.optimization.objective_time_period' `
                    "objective_time_period ($(Format-Num $tp)) is negative" $tp 'Time periods are 0-based and non-negative.'))
    }
    $mls = Get-Prop $opt 'max_local_solver'
    if ((Test-IsInt $mls) -and (-not (($mls -ge 0) -and ($mls -le 100)))) {
        [void]$out.Add((New-Finding $SevWarning 'optimization.max_local_solver_range' '$.optimization.max_local_solver' `
                    "max_local_solver ($(Format-Num $mls)) is outside the supported 0..100 range" $mls 'Use up to 100 local solvers.'))
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
        $ltype = Get-Prop $lim 'limit_type'
        if ($null -eq $ltype) {
            [void]$out.Add((New-Finding $SevWarning 'metric_limit.no_type' "$path.limit_type" `
                        "metric_limit for '$(Format-PyStr $mname)' has no limit_type" $null 'Set limit_type to Minimum or Maximum.'))
        }
        $targets = Get-Prop $lim 'targets'
        if (Test-IsArray $targets) {
            $t = 0
            foreach ($tg in $targets) {
                if (-not (Test-IsObject $tg)) { $t++; continue }
                $p = Get-Prop $tg 'period'
                if ((Test-IsInt $p) -and ($p -lt 0)) {
                    [void]$out.Add((New-Finding $SevError 'metric_limit.period_negative' "$path.targets[$t].period" `
                                "target period ($(Format-Num $p)) is negative" $p 'Time periods are 0-based and non-negative.'))
                }
                $t++
            }
        }
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
        $selections = Get-Prop $s 'selections'
        if (Test-IsArray $selections) {
            $j = 0
            foreach ($pv in $selections) {
                if (-not (Test-IsObject $pv)) { $j++; continue }
                $period = Get-Prop $pv 'period'
                $value = Get-Prop $pv 'value'
                if ((Test-IsInt $period) -and ($period -lt 0)) {
                    [void]$out.Add((New-Finding $SevError 'selection.period_negative' "$path.selections[$j].period" `
                                "selection period ($(Format-Num $period)) is negative" $period 'Time periods are 0-based and non-negative.'))
                }
                if ((Test-IsNumber $value) -and ($value -lt 0)) {
                    [void]$out.Add((New-Finding $SevError 'selection.value_negative' "$path.selections[$j].value" `
                                "selected quantity ($(Format-Num $value)) is negative" $value 'Selected quantities are non-negative (0 = not selected).'))
                }
                $j++
            }
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
