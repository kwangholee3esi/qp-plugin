# PowerShell fallback validator for a QPortfolio Portable JSON *portfolio* file.
# Used only when Python is unavailable; mirrors validate_portfolio.py (the source
# of truth) - same CLI, same exit codes, same JSON output contract.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File validate_portfolio.ps1 `
#       <file.json> [--schema PATH] [--format json|text] [--strict-nulls]
#
# Exit codes: 0 valid | 1 invalid | 2 io/parse error | 3 environment error.

. (Join-Path $PSScriptRoot 'qp_validation_common.ps1')

$ExpectedFileType = 'QPortfolio Data'

# Portfolio-specific reference message ("...not defined in input_data").
function Invoke-RefCheck($name, $valid, $path, $check, $out, $what, $hint) {
    if (($name -is [string]) -and (-not $valid.Contains($name))) {
        [void]$out.Add((New-Finding $SevError $check $path `
                    "references $what '$name' which is not defined in input_data" $name $hint))
    }
}

function Add-Weight($outcome, $siblings, $ocp, $out) {
    $weight = Get-Prop $outcome 'weight'
    $multi = (Test-IsArray $siblings) -and (@($siblings).Count -gt 1)
    if ($null -eq $weight) {
        if ($multi) {
            [void]$out.Add((New-Finding $SevWarning 'weight.missing' "$ocp.weight" `
                        "multi-outcome opportunity has an outcome with no weight (importer normalizes, but be explicit)" `
                        $null 'Set a probability weight for every outcome of an uncertain opportunity.'))
        }
    } elseif ((Test-IsNumber $weight) -and ($weight -lt 0)) {
        [void]$out.Add((New-Finding $SevError 'weight.negative' "$ocp.weight" `
                    "outcome weight $(Format-Num $weight) is negative" $weight 'Weights are probabilities; use a non-negative number.'))
    }
}

function Add-MetricValues($outcome, $ocp, $out) {
    $mvs = Get-Prop $outcome 'metric_values'
    if (-not (Test-IsArray $mvs)) { return }
    $seriesLens = New-Object System.Collections.ArrayList
    $k = 0
    foreach ($mv in $mvs) {
        if (-not (Test-IsObject $mv)) { $k++; continue }
        $mvp = "$ocp.metric_values[$k]"
        $mname = Get-Prop $mv 'metric_name'
        $values = Get-Prop $mv 'values'
        $scalar = Test-IsTrue (Get-Prop $mv 'scalar')
        if (Test-IsArray $values) {
            $len = @($values).Count
            if ($scalar) {
                if ($len -ne 1) {
                    [void]$out.Add((New-Finding $SevError 'scalar.arity' "$mvp.values" `
                                "scalar metric '$(Format-PyStr $mname)' must have exactly one value, got $len" `
                                $len 'A scalar metric carries a single value.'))
                }
            } else {
                if ($len -eq 0) {
                    [void]$out.Add((New-Finding $SevWarning 'series.empty' "$mvp.values" `
                                "non-scalar metric '$(Format-PyStr $mname)' has an empty time series" `
                                $null 'Provide per-period values or mark the metric scalar.'))
                } else {
                    [void]$seriesLens.Add($len)
                }
            }
        }
        $k++
    }
    $distinct = @($seriesLens | Sort-Object -Unique)
    if ($distinct.Count -gt 1) {
        [void]$out.Add((New-Finding $SevWarning 'series.length_mismatch' $ocp `
                    "time-series metrics in this outcome have differing lengths $(Format-IntList $distinct) (importer zero-fills, but verify the horizon)" `
                    ([int[]]$distinct) 'Use one consistent number of periods across metrics.'))
    }
}

# Returns @{ name = HashSet[string] of outcome names }; emits weight/series checks.
function Build-OppIndex($oppList, $rootPath, $out) {
    $index = @{}
    $i = 0
    foreach ($opp in @($oppList)) {
        if (-not (Test-IsObject $opp)) { $i++; continue }
        $name = Get-Prop $opp 'opportunity_name'
        $path = "$rootPath.opportunity_outcomes[$i]"
        $outcomes = Get-Prop $opp 'outcomes'
        $outNames = New-Object 'System.Collections.Generic.HashSet[string]'
        if (Test-IsArray $outcomes) {
            $j = 0
            foreach ($oc in $outcomes) {
                if (-not (Test-IsObject $oc)) { $j++; continue }
                $ocp = "$path.outcomes[$j]"
                $ocn = Get-Prop $oc 'outcome_name'
                if ($ocn -is [string]) { [void]$outNames.Add($ocn) }
                Add-Weight $oc $outcomes $ocp $out
                Add-MetricValues $oc $ocp $out
                $j++
            }
        }
        if ($name -is [string]) { $index[$name] = $outNames }
        $i++
    }
    return $index
}

function Get-OutcomeSet($index, $name) {
    if (($name -is [string]) -and $index.ContainsKey($name)) { return , $index[$name] }
    return , (New-Object 'System.Collections.Generic.HashSet[string]')
}

function New-StringSet { return , (New-Object 'System.Collections.Generic.HashSet[string]') }

function Add-AttributeChecks($attrs, $OPP, $MASTER, $out) {
    if (-not (Test-IsObject $attrs)) { return }
    $declared = New-StringSet
    $decl = Get-Prop $attrs 'attributes'
    if (Test-IsArray $decl) { foreach ($d in $decl) { if ($d -is [string]) { [void]$declared.Add($d) } } }
    $rows = Get-Prop $attrs 'opportunity_attributes'
    if (-not (Test-IsArray $rows)) { return }
    $seenOrder = @{}
    $i = 0
    foreach ($row in $rows) {
        if (-not (Test-IsObject $row)) { $i++; continue }
        $path = "`$.attributes.opportunity_attributes[$i]"
        $name = Get-Prop $row 'opportunity_name'
        $isMd = Test-IsTrue (Get-Prop $row 'is_master_data')
        if ($name -is [string]) {
            $valid = New-Object 'System.Collections.Generic.HashSet[string]' (, [string[]]@($OPP))
            if ($isMd) { [void]$valid.UnionWith($MASTER) }
            if (-not $valid.Contains($name)) {
                $where = if ($isMd) { 'input_data/master_data' } else { 'input_data' }
                [void]$out.Add((New-Finding $SevError 'ref.attr_opportunity' "$path.opportunity_name" `
                            "attribute row references '$name' not defined in $where" $name 'Match an existing opportunity, or set is_master_data.'))
            }
        }
        $order = Get-Prop $row 'order'
        if (Test-IsInt $order) {
            if ($seenOrder.ContainsKey($order)) {
                [void]$out.Add((New-Finding $SevWarning 'attr.order_duplicate' "$path.order" `
                            "order $order is reused (also at index $($seenOrder[$order]))" $order 'Use a distinct 0-based order per opportunity.'))
            } else {
                $seenOrder[$order] = $i
            }
        }
        $chars = Get-Prop $row 'characteristics'
        if (Test-IsArray $chars) {
            $c = 0
            foreach ($ch in $chars) {
                if (-not (Test-IsObject $ch)) { $c++; continue }
                $a = Get-Prop $ch 'attribute'
                $cp = "$path.characteristics[$c].attribute"
                if ($a -is [string]) {
                    if (($declared.Count -gt 0) -and (-not $declared.Contains($a))) {
                        [void]$out.Add((New-Finding $SevWarning 'attr.undeclared' $cp `
                                    "attribute '$a' is used but not declared in attributes.attributes" $a 'Add it to attributes.attributes or remove the characteristic.'))
                    }
                }
                $c++
            }
        }
        $i++
    }
}

function Add-OutcomeDependencyChecks($dep, $OPP, $oppIndex, $out) {
    if (-not (Test-IsObject $dep)) { return }
    $deps = Get-Prop $dep 'dependencies'
    if (-not (Test-IsArray $deps)) { return }
    $i = 0
    foreach ($d in $deps) {
        if (-not (Test-IsObject $d)) { $i++; continue }
        $path = "`$.outcome_dependency.dependencies[$i]"
        $ind = Get-Prop $d 'independent_opportunity'
        $dpd = Get-Prop $d 'dependent_opportunity'
        Invoke-RefCheck $ind $OPP "$path.independent_opportunity" 'ref.outcome_dep.independent' $out 'independent opportunity' 'Add it to input_data or fix the name.'
        Invoke-RefCheck $dpd $OPP "$path.dependent_opportunity" 'ref.outcome_dep.dependent' $out 'dependent opportunity' 'Add it to input_data or fix the name.'
        if (($ind -is [string]) -and ($ind -ceq $dpd)) {
            [void]$out.Add((New-Finding $SevWarning 'outcome_dep.self' $path `
                        "independent and dependent opportunity are both '$ind'" $ind 'An opportunity should not depend on itself.'))
        }
        $indOut = Get-OutcomeSet $oppIndex $ind
        $depOut = Get-OutcomeSet $oppIndex $dpd
        $cases = Get-Prop $d 'target_cases'
        if (-not (Test-IsArray $cases)) { $i++; continue }
        $seenInd = New-StringSet
        $j = 0
        foreach ($case in $cases) {
            if (-not (Test-IsObject $case)) { $j++; continue }
            $cpath = "$path.target_cases[$j]"
            $inds = Get-Prop $case 'independent_outcomes'
            if (Test-IsArray $inds) {
                foreach ($o in $inds) {
                    if ($o -eq '*') { continue }
                    if (($o -is [string]) -and ($indOut.Count -gt 0) -and (-not $indOut.Contains($o))) {
                        [void]$out.Add((New-Finding $SevError 'ref.outcome_dep.independent_outcome' "$cpath.independent_outcomes" `
                                    "independent outcome '$o' is not an outcome of '$(Format-PyStr $ind)'" $o 'Use a real outcome name or "*" for all others.'))
                    }
                    if ($o -is [string]) {
                        if ($seenInd.Contains($o)) {
                            [void]$out.Add((New-Finding $SevError 'outcome_dep.independent_outcome_dup' "$cpath.independent_outcomes" `
                                        "independent outcome '$o' mapped by more than one case" $o 'Each independent outcome maps in at most one case.'))
                        }
                        [void]$seenInd.Add($o)
                    }
                }
            }
            $weights = Get-Prop $case 'outcome_weights'
            if (Test-IsArray $weights) {
                $w = 0
                foreach ($ow in $weights) {
                    if (-not (Test-IsObject $ow)) { $w++; continue }
                    $douts = Get-Prop $ow 'dependent_outcomes'
                    if (Test-IsArray $douts) {
                        foreach ($o in $douts) {
                            if (($o -is [string]) -and ($depOut.Count -gt 0) -and (-not $depOut.Contains($o))) {
                                [void]$out.Add((New-Finding $SevError 'ref.outcome_dep.dependent_outcome' "$cpath.outcome_weights[$w].dependent_outcomes" `
                                            "dependent outcome '$o' is not an outcome of '$(Format-PyStr $dpd)'" $o 'Use a real outcome name of the dependent opportunity.'))
                            }
                        }
                    }
                    $w++
                }
            }
            $j++
        }
        $i++
    }
}

function Add-SelectionConstraintChecks($sc, $OPP, $out) {
    if (-not (Test-IsObject $sc)) { return }
    $limits = Get-Prop $sc 'opportunity_limits'
    if (-not (Test-IsArray $limits)) { return }
    $i = 0
    foreach ($lim in $limits) {
        if (-not (Test-IsObject $lim)) { $i++; continue }
        $path = "`$.selection_constraints.opportunity_limits[$i]"
        $name = Get-Prop $lim 'opportunity_name'
        if ($name -is [string]) {
            Invoke-RefCheck $name $OPP "$path.opportunity_name" 'ref.constraint_opportunity' $out 'opportunity' 'Add it to input_data or fix the name.'
        }
        Invoke-LimitNumericChecks $lim $path $out "opportunity '$(Format-PyStr $name)'"
        $i++
    }
}

function Add-SelectionDependencyChecks($sd, $OPP, $out) {
    if (-not (Test-IsObject $sd)) { return }
    $deps = Get-Prop $sd 'dependencies'
    if (-not (Test-IsArray $deps)) { return }
    $i = 0
    foreach ($d in $deps) {
        if (-not (Test-IsObject $d)) { $i++; continue }
        $path = "`$.selection_dependency.dependencies[$i]"
        $dpd = Get-Prop $d 'dependent_opportunity'
        $ind = Get-Prop $d 'independent_opportunity'
        Invoke-RefCheck $dpd $OPP "$path.dependent_opportunity" 'ref.selection_dep.dependent' $out 'dependent opportunity' 'Add it to input_data or fix the name.'
        Invoke-RefCheck $ind $OPP "$path.independent_opportunity" 'ref.selection_dep.independent' $out 'independent opportunity' 'Add it to input_data or fix the name.'
        if (($ind -is [string]) -and ($ind -ceq $dpd)) {
            [void]$out.Add((New-Finding $SevWarning 'selection_dep.self' $path `
                        "dependent and independent opportunity are both '$ind'" $ind 'An opportunity should not depend on itself.'))
        }
        $i++
    }
}

function Add-SelectionGroupChecks($sg, $OPP, $out) {
    if (-not (Test-IsObject $sg)) { return }
    $groups = Get-Prop $sg 'groups'
    $groupNames = New-StringSet
    if (Test-IsArray $groups) {
        $i = 0
        foreach ($g in $groups) {
            if (-not (Test-IsObject $g)) { $i++; continue }
            $path = "`$.selection_group.groups[$i]"
            $gname = Get-Prop $g 'group_name'
            if ($gname -is [string]) { [void]$groupNames.Add($gname) }
            $members = Get-Prop $g 'members'
            if (Test-IsArray $members) {
                $m = 0
                foreach ($mem in $members) {
                    if (-not (Test-IsObject $mem)) { $m++; continue }
                    $mp = "$path.members[$m].opportunity_name"
                    $mn = Get-Prop $mem 'opportunity_name'
                    Invoke-RefCheck $mn $OPP $mp 'ref.group_member' $out 'member opportunity' 'Members must be defined opportunities.'
                    $m++
                }
            }
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

function Add-MasterDefaultCheck($masterData, $attrs, $masterOpps, $out) {
    if ((-not (Test-IsObject $masterData)) -or (@($masterOpps).Count -eq 0)) { return }
    $qualified = New-StringSet
    if (Test-IsObject $attrs) {
        $rows = Get-Prop $attrs 'opportunity_attributes'
        if (Test-IsArray $rows) {
            foreach ($row in $rows) {
                if ((-not (Test-IsObject $row)) -or (-not (Test-IsTrue (Get-Prop $row 'is_master_data')))) { continue }
                $chars = Get-Prop $row 'characteristics'
                $hasValue = $false
                if (Test-IsArray $chars) {
                    foreach ($c in $chars) {
                        if (Test-IsObject $c) {
                            $v = Get-Prop $c 'value'
                            if (($null -ne $v) -and ($v -ne '')) { $hasValue = $true }
                        }
                    }
                }
                if ($hasValue) { [void]$qualified.Add((Get-NameKey (Get-Prop $row 'opportunity_name'))) }
            }
        }
    }
    $masterNames = New-StringSet
    foreach ($o in @($masterOpps)) {
        if (Test-IsObject $o) { [void]$masterNames.Add((Get-NameKey (Get-Prop $o 'opportunity_name'))) }
    }
    if (($masterNames.Count -gt 0) -and ($qualified.IsSupersetOf($masterNames))) {
        [void]$out.Add((New-Finding $SevError 'master.no_default' '$.master_data' `
                    "every master-data set is attribute-qualified; a default set (no attributes) must always exist" `
                    $null 'Add a master-data set with no attribute characteristics.'))
    }
}

# Stable key so a null/numeric opportunity_name survives set membership (Python keeps None).
function Get-NameKey($v) {
    if ($null -eq $v) { return "`0null" }
    if ($v -is [string]) { return "s:$v" }
    return "n:$(Format-Num $v)"
}

function Get-PortfolioSemantic($data, $strict, $portfolioNames) {
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

    $inputOpps = Get-OpportunityOutcomes (Get-Prop $data 'input_data')
    $oppIndex = Build-OppIndex $inputOpps '$.input_data' $out
    $OPP = New-StringSet
    foreach ($k in $oppIndex.Keys) { if ($k -is [string]) { [void]$OPP.Add($k) } }

    $masterOpps = Get-OpportunityOutcomes (Get-Prop $data 'master_data')
    $masterIndex = Build-OppIndex $masterOpps '$.master_data' $out
    $MASTER = New-StringSet
    foreach ($k in $masterIndex.Keys) { if ($k -is [string]) { [void]$MASTER.Add($k) } }

    Add-AttributeChecks (Get-Prop $data 'attributes') $OPP $MASTER $out
    Add-OutcomeDependencyChecks (Get-Prop $data 'outcome_dependency') $OPP $oppIndex $out
    Add-SelectionConstraintChecks (Get-Prop $data 'selection_constraints') $OPP $out
    Add-SelectionDependencyChecks (Get-Prop $data 'selection_dependency') $OPP $out
    Add-SelectionGroupChecks (Get-Prop $data 'selection_group') $OPP $out
    Add-MasterDefaultCheck (Get-Prop $data 'master_data') (Get-Prop $data 'attributes') $masterOpps $out

    if ($strict) { Invoke-ExplicitNullChecks $data '$' $out }
    return $out
}

exit (Invoke-QpValidation $args 'portfolio.schema.json' $PSScriptRoot 'Get-PortfolioSemantic' $false)
