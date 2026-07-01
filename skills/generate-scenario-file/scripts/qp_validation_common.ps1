# Shared core for the PowerShell fallback validators (validate_portfolio.ps1 /
# validate_scenario.ps1). Pure Windows PowerShell 5.1 / .NET Framework 4.8 - no
# external modules, no NuGet, no network.
#
# This is the no-Python fallback for the QPortfolio authoring skills. It mirrors
# the Python validators (validate_*.py) closely enough that tests/conformance_ps.py
# can assert identical findings, summary counters and exit codes against every
# fixture. The Python validators remain the source of truth.
#
# This file is intentionally duplicated byte-for-byte under each skill's scripts/
# directory (conformance_ps.py asserts the two copies are identical), mirroring
# the cross-file duplication the Python validators already carry.

# Deterministic, culture-independent number formatting / comparison.
[System.Threading.Thread]::CurrentThread.CurrentCulture = [System.Globalization.CultureInfo]::InvariantCulture
[System.Threading.Thread]::CurrentThread.CurrentUICulture = [System.Globalization.CultureInfo]::InvariantCulture

$SevError = 'error'
$SevWarning = 'warning'

# --------------------------------------------------------------------------- #
# Type helpers for ConvertFrom-Json output (PSCustomObject objects, Object[]
# arrays). PS 5.1 has no -AsHashtable; we walk PSObject.Properties so we can
# tell an absent key from an explicit null (matches Python `k in d` vs `d[k] is None`).
# --------------------------------------------------------------------------- #
function Test-IsObject($x) { $x -is [System.Management.Automation.PSCustomObject] }
function Test-IsArray($x) { ($x -is [System.Collections.IEnumerable]) -and ($x -isnot [string]) }
function Test-HasProp($obj, $name) {
    if (-not (Test-IsObject $obj)) { return $false }
    return $null -ne $obj.PSObject.Properties[$name]
}
function Get-Prop($obj, $name) {
    if (-not (Test-IsObject $obj)) { return $null }
    $p = $obj.PSObject.Properties[$name]
    if ($null -eq $p) { return $null }
    # Comma-wrap so an array value is returned intact (PowerShell otherwise
    # unrolls a returned collection, collapsing a single-element array to a scalar).
    return , $p.Value
}

function Test-IsBool($x) { $x -is [bool] }
# Python `x is True`: only a real boolean true, never a truthy number.
function Test-IsTrue($x) { ($x -is [bool]) -and $x }
# Python isinstance(x, int): JSON ints land as Int32/Int64 (5.0 lands as Decimal).
function Test-IsInt($x) { (-not (Test-IsBool $x)) -and (($x -is [int]) -or ($x -is [long])) }
# Python isinstance(x, (int, float)): any JSON number, excluding bool.
function Test-IsNumber($x) {
    if (Test-IsBool $x) { return $false }
    return ($x -is [int]) -or ($x -is [long]) -or ($x -is [double]) -or ($x -is [decimal])
}
# JSON-Schema "integer": any number with zero fractional part (jsonschema parity).
function Test-IsSchemaInteger($x) {
    if (Test-IsBool $x) { return $false }
    if (($x -is [int]) -or ($x -is [long])) { return $true }
    if ($x -is [double]) {
        if ([double]::IsNaN($x) -or [double]::IsInfinity($x)) { return $false }
        return [math]::Floor($x) -eq $x
    }
    if ($x -is [decimal]) { return [math]::Floor($x) -eq $x }
    return $false
}

# Python str() of a JSON number: ints have no point, floats always keep one.
function Format-Num($v) {
    if ($null -eq $v) { return 'None' }
    if (Test-IsBool $v) { if ($v) { return 'True' } else { return 'False' } }
    if ($v -is [double]) {
        if ([double]::IsNaN($v)) { return 'nan' }
        if ([double]::IsPositiveInfinity($v)) { return 'inf' }
        if ([double]::IsNegativeInfinity($v)) { return '-inf' }
        $s = $v.ToString('R', [System.Globalization.CultureInfo]::InvariantCulture)
        if ($s -notmatch '[.eE]') { $s = $s + '.0' }
        return ($s -replace 'E', 'e')
    }
    return [string]$v
}

# Python str() for {x} message interpolation (None -> 'None', strings as-is, numbers via Format-Num).
function Format-PyStr($v) {
    if ($null -eq $v) { return 'None' }
    if (Test-IsBool $v) { if ($v) { return 'True' } else { return 'False' } }
    if ($v -is [string]) { return $v }
    return (Format-Num $v)
}

# Python str() of a sorted list of ints, e.g. [2, 3].
function Format-IntList($items) {
    return '[' + ((@($items) | ForEach-Object { Format-Num $_ }) -join ', ') + ']'
}

# Python repr() for {x!r} message interpolation (strings single-quoted, None, numbers bare).
function ConvertTo-PyRepr($v) {
    if ($null -eq $v) { return 'None' }
    if (Test-IsBool $v) { if ($v) { return 'True' } else { return 'False' } }
    if ($v -is [string]) {
        $e = $v.Replace('\', '\\').Replace("'", "\'")
        return "'" + $e + "'"
    }
    return (Format-Num $v)
}

# --------------------------------------------------------------------------- #
# Finding helper (key order matches the Python finding() dict exactly).
# --------------------------------------------------------------------------- #
function New-Finding($severity, $check, $json_path, $message, $offending_value = $null, $hint = $null) {
    return [ordered]@{
        severity        = $severity
        check           = $check
        json_path       = $json_path
        message         = $message
        offending_value = $offending_value
        hint            = $hint
    }
}

# --------------------------------------------------------------------------- #
# JSON loading + non-finite rejection (Python parse_constant parity -> exit 2).
# PS 5.1 ConvertFrom-Json silently accepts NaN/Infinity, so we walk and reject.
# --------------------------------------------------------------------------- #
function Test-HasNonFinite($node) {
    if ($node -is [double]) { return ([double]::IsNaN($node) -or [double]::IsInfinity($node)) }
    if (Test-IsObject $node) {
        foreach ($p in $node.PSObject.Properties) { if (Test-HasNonFinite $p.Value) { return $true } }
        return $false
    }
    if (Test-IsArray $node) {
        foreach ($e in $node) { if (Test-HasNonFinite $e) { return $true } }
        return $false
    }
    return $false
}

function Read-JsonDocument($path) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        return @{ ok = $false; message = "cannot read ${path}: file not found" }
    }
    try {
        $text = [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8)
    } catch {
        return @{ ok = $false; message = "cannot read ${path}: $($_.Exception.Message)" }
    }
    try {
        $data = $text | ConvertFrom-Json
    } catch {
        return @{ ok = $false; message = "${path} is not valid JSON (or contains NaN/Infinity): $($_.Exception.Message)" }
    }
    if (Test-HasNonFinite $data) {
        return @{ ok = $false; message = "${path} is not valid JSON (or contains NaN/Infinity)" }
    }
    return @{ ok = $true; data = $data }
}

# --------------------------------------------------------------------------- #
# Subset JSON-Schema engine (Draft 2020-12 keywords this product's schemas use).
# Errors are collected with their raw path segments so we can reproduce Python's
# `sorted(absolute_path)` ordering exactly.
# --------------------------------------------------------------------------- #
function Convert-SegsToPath($segs) {
    $s = '$'
    foreach ($seg in $segs) {
        if (($seg -is [int]) -or ($seg -is [long])) { $s += "[$seg]" } else { $s += ".$seg" }
    }
    return $s
}

function Add-SchemaError($errs, $segs, $validator, $message) {
    [void]$errs.Add([ordered]@{
            json_path = (Convert-SegsToPath $segs)
            message   = $message
            validator = $validator
            _segs     = $segs
        })
}

function Resolve-SchemaRef($ref, $root) {
    if ($ref -isnot [string]) { return $null }
    if (-not $ref.StartsWith('#/')) { return $null }
    $cur = $root
    foreach ($tok in $ref.Substring(2).Split('/')) {
        $t = $tok.Replace('~1', '/').Replace('~0', '~')
        if (Test-HasProp $cur $t) { $cur = (Get-Prop $cur $t) } else { return $null }
    }
    return $cur
}

function Test-JsonTypeMatch($instance, $types) {
    foreach ($t in @($types)) {
        switch ($t) {
            'null' { if ($null -eq $instance) { return $true } }
            'boolean' { if (Test-IsBool $instance) { return $true } }
            'object' { if (Test-IsObject $instance) { return $true } }
            'array' { if (Test-IsArray $instance) { return $true } }
            'string' { if ($instance -is [string]) { return $true } }
            'number' { if (Test-IsNumber $instance) { return $true } }
            'integer' { if (Test-IsSchemaInteger $instance) { return $true } }
        }
    }
    return $false
}

function Test-JsonScalarEqual($a, $b) {
    if (($null -eq $a) -and ($null -eq $b)) { return $true }
    if (($null -eq $a) -or ($null -eq $b)) { return $false }
    if (($a -is [string]) -and ($b -is [string])) {
        return [string]::Equals($a, $b, [System.StringComparison]::Ordinal)
    }
    if ((Test-IsNumber $a) -and (Test-IsNumber $b)) { return ($a -eq $b) }
    if ((Test-IsBool $a) -and (Test-IsBool $b)) { return ($a -eq $b) }
    return $false
}

# RFC-6901 pointer into one array item -> a stable string key (Python _resolve_pointer).
function Resolve-Pointer($item, $pointer) {
    $cur = $item
    $tokens = $pointer.Split('/')
    for ($t = 1; $t -lt $tokens.Count; $t++) {
        $tok = $tokens[$t].Replace('~1', '/').Replace('~0', '~')
        if ((Test-IsObject $cur) -and (Test-HasProp $cur $tok)) {
            $cur = (Get-Prop $cur $tok)
        } else {
            return "__missing__::$pointer"
        }
    }
    if ((Test-IsObject $cur) -or (Test-IsArray $cur)) { return "json::" + (ConvertTo-CanonicalJson $cur) }
    if ($null -eq $cur) { return 'null::' }
    if ($cur -is [string]) { return "str::$cur" }
    if (Test-IsBool $cur) { if ($cur) { return 'bool::true' } else { return 'bool::false' } }
    return "num::" + (Format-Num $cur)
}

# json.dumps(sort_keys=True) equivalent for the rare object/array pointer target.
function ConvertTo-CanonicalJson($node) {
    if ($null -eq $node) { return 'null' }
    if ($node -is [string]) { return ($node | ConvertTo-Json -Compress) }
    if (Test-IsBool $node) { if ($node) { return 'true' } else { return 'false' } }
    if (Test-IsNumber $node) { return (Format-Num $node) }
    if (Test-IsArray $node) {
        $parts = @()
        foreach ($e in $node) { $parts += (ConvertTo-CanonicalJson $e) }
        return '[' + ($parts -join ',') + ']'
    }
    if (Test-IsObject $node) {
        $names = @($node.PSObject.Properties | ForEach-Object { $_.Name } | Sort-Object)
        $parts = @()
        foreach ($n in $names) {
            $parts += (($n | ConvertTo-Json -Compress) + ':' + (ConvertTo-CanonicalJson (Get-Prop $node $n)))
        }
        return '{' + ($parts -join ',') + '}'
    }
    return 'null'
}

function Invoke-SchemaNode($schema, $instance, $segs, $root, $errs) {
    if (-not (Test-IsObject $schema)) { return }
    foreach ($kw in $schema.PSObject.Properties) {
        $name = $kw.Name
        $val = $kw.Value
        switch -CaseSensitive ($name) {
            '$ref' {
                $target = Resolve-SchemaRef $val $root
                if ($null -ne $target) { Invoke-SchemaNode $target $instance $segs $root $errs }
            }
            'type' {
                if (-not (Test-JsonTypeMatch $instance $val)) {
                    $tn = (@($val) -join "', '")
                    Add-SchemaError $errs $segs 'type' "is not of type '$tn'"
                }
            }
            'enum' {
                $matched = $false
                foreach ($ev in @($val)) { if (Test-JsonScalarEqual $instance $ev) { $matched = $true; break } }
                if (-not $matched) { Add-SchemaError $errs $segs 'enum' "is not one of the allowed values" }
            }
            'required' {
                if (Test-IsObject $instance) {
                    foreach ($rp in @($val)) {
                        if (-not (Test-HasProp $instance $rp)) {
                            Add-SchemaError $errs $segs 'required' "'$rp' is a required property"
                        }
                    }
                }
            }
            'properties' {
                if (Test-IsObject $instance) {
                    foreach ($ps in $val.PSObject.Properties) {
                        $pn = $ps.Name
                        if (Test-HasProp $instance $pn) {
                            Invoke-SchemaNode $ps.Value (Get-Prop $instance $pn) ($segs + @([string]$pn)) $root $errs
                        }
                    }
                }
            }
            'additionalProperties' {
                if ((Test-IsObject $instance) -and ($val -is [bool]) -and (-not $val)) {
                    $allowed = @()
                    if (Test-HasProp $schema 'properties') {
                        $allowed = @((Get-Prop $schema 'properties').PSObject.Properties | ForEach-Object { $_.Name })
                    }
                    $extras = @()
                    foreach ($ip in $instance.PSObject.Properties) {
                        if ($allowed -notcontains $ip.Name) { $extras += $ip.Name }
                    }
                    if ($extras.Count -gt 0) {
                        $ex = ($extras | ForEach-Object { "'$_'" }) -join ', '
                        Add-SchemaError $errs $segs 'additionalProperties' "Additional properties are not allowed ($ex unexpected)"
                    }
                }
            }
            'items' {
                if (Test-IsArray $instance) {
                    $i = 0
                    foreach ($el in $instance) {
                        Invoke-SchemaNode $val $el ($segs + @([int]$i)) $root $errs
                        $i++
                    }
                }
            }
            'minimum' {
                if ((Test-IsNumber $instance) -and ($instance -lt $val)) {
                    Add-SchemaError $errs $segs 'minimum' "$(Format-Num $instance) is less than the minimum of $(Format-Num $val)"
                }
            }
            'maximum' {
                if ((Test-IsNumber $instance) -and ($instance -gt $val)) {
                    Add-SchemaError $errs $segs 'maximum' "$(Format-Num $instance) is greater than the maximum of $(Format-Num $val)"
                }
            }
            'exclusiveMinimum' {
                if ((Test-IsNumber $instance) -and ($instance -le $val)) {
                    Add-SchemaError $errs $segs 'exclusiveMinimum' "$(Format-Num $instance) is less than or equal to the exclusive minimum of $(Format-Num $val)"
                }
            }
            'exclusiveMaximum' {
                if ((Test-IsNumber $instance) -and ($instance -ge $val)) {
                    Add-SchemaError $errs $segs 'exclusiveMaximum' "$(Format-Num $instance) is greater than or equal to the exclusive maximum of $(Format-Num $val)"
                }
            }
            'minLength' {
                if (($instance -is [string]) -and ($instance.Length -lt $val)) {
                    Add-SchemaError $errs $segs 'minLength' "is too short"
                }
            }
            'maxLength' {
                if (($instance -is [string]) -and ($instance.Length -gt $val)) {
                    Add-SchemaError $errs $segs 'maxLength' "is too long"
                }
            }
            'pattern' {
                if (($instance -is [string]) -and (-not [regex]::IsMatch($instance, $val))) {
                    Add-SchemaError $errs $segs 'pattern' "does not match '$val'"
                }
            }
            'uniqueKeys' {
                if ((Test-IsArray $instance) -and (Test-IsArray $val)) {
                    $seen = @{}
                    $idx = 0
                    foreach ($item in $instance) {
                        $parts = @()
                        foreach ($ptr in $val) { $parts += (Resolve-Pointer $item $ptr) }
                        $key = ($parts -join ([char]1))
                        if ($seen.ContainsKey($key)) {
                            $kp = (@($val) -join "', '")
                            Add-SchemaError $errs $segs 'uniqueKeys' "array items must be unique by ['$kp']: index $idx duplicates index $($seen[$key])"
                        } else {
                            $seen[$key] = $idx
                        }
                        $idx++
                    }
                }
            }
        }
    }
}

# Compare two raw segment lists the way Python compares list(absolute_path).
function Compare-Segs($a, $b) {
    $la = @($a).Count; $lb = @($b).Count
    $n = [Math]::Min($la, $lb)
    for ($i = 0; $i -lt $n; $i++) {
        $x = $a[$i]; $y = $b[$i]
        $xi = (($x -is [int]) -or ($x -is [long]))
        $yi = (($y -is [int]) -or ($y -is [long]))
        if ($xi -and $yi) {
            if ($x -lt $y) { return -1 }
            if ($x -gt $y) { return 1 }
        } elseif ((-not $xi) -and (-not $yi)) {
            $c = [string]::CompareOrdinal([string]$x, [string]$y)
            if ($c -lt 0) { return -1 }
            if ($c -gt 0) { return 1 }
        } else {
            if ($xi) { return -1 } else { return 1 }
        }
    }
    if ($la -lt $lb) { return -1 }
    if ($la -gt $lb) { return 1 }
    return 0
}

# Stable insertion sort (preserves insertion order for equal paths, like Python's sorted()).
function Sort-SchemaErrors($errs) {
    $arr = [object[]]@($errs)
    $n = $arr.Count
    for ($i = 1; $i -lt $n; $i++) {
        $cur = $arr[$i]; $j = $i - 1
        while (($j -ge 0) -and ((Compare-Segs $arr[$j]._segs $cur._segs) -gt 0)) {
            $arr[$j + 1] = $arr[$j]; $j--
        }
        $arr[$j + 1] = $cur
    }
    return @($arr | ForEach-Object {
            [ordered]@{ json_path = $_.json_path; message = $_.message; validator = $_.validator }
        })
}

# --------------------------------------------------------------------------- #
# Shared semantic helpers (identical in both Python validators).
# --------------------------------------------------------------------------- #
function Get-OpportunityOutcomes($section) {
    if (-not (Test-IsObject $section)) { return , @() }
    $oo = Get-Prop $section 'opportunity_outcomes'
    if (Test-IsArray $oo) { return , $oo } else { return , @() }
}

function Get-NumOrNull($obj, $key) {
    $v = Get-Prop $obj $key
    if (Test-IsNumber $v) { return $v } else { return $null }
}

function Invoke-LimitNumericChecks($limit, $path, $out, $label) {
    $tmin = Get-NumOrNull $limit 'total_minimum'
    $tmax = Get-NumOrNull $limit 'total_maximum'
    if (($null -ne $tmin) -and ($null -ne $tmax) -and ($tmax -lt $tmin)) {
        [void]$out.Add((New-Finding $SevError 'limit.total_max_lt_min' "$path.total_maximum" `
                    "${label}: total_maximum ($(Format-Num $tmax)) < total_minimum ($(Format-Num $tmin))" `
                    $tmax 'Schema requires total_maximum >= total_minimum.'))
    }
    $imin = Get-NumOrNull $limit 'total_instances_minimum'
    $imax = Get-NumOrNull $limit 'total_instances_maximum'
    if (($null -ne $imin) -and ($null -ne $imax) -and ($imax -lt $imin)) {
        [void]$out.Add((New-Finding $SevError 'limit.inst_max_lt_min' "$path.total_instances_maximum" `
                    "${label}: total_instances_maximum ($(Format-Num $imax)) < total_instances_minimum ($(Format-Num $imin))" `
                    $imax 'Schema requires total_instances_maximum >= total_instances_minimum.'))
    }
    foreach ($key in @('total_minimum', 'total_maximum', 'total_instances_minimum', 'total_instances_maximum', 'interior_limit')) {
        $v = Get-NumOrNull $limit $key
        if (($null -ne $v) -and ($v -lt 0)) {
            [void]$out.Add((New-Finding $SevError 'limit.negative' "$path.$key" `
                        "${label}: $key ($(Format-Num $v)) is negative" $v 'Selection quantities are non-negative.'))
        }
    }
    $mins = Get-Prop $limit 'time_period_minima'; if (-not (Test-IsArray $mins)) { $mins = @() } else { $mins = @($mins) }
    $maxs = Get-Prop $limit 'time_period_maxima'; if (-not (Test-IsArray $maxs)) { $maxs = @() } else { $maxs = @($maxs) }
    for ($idx = 0; $idx -lt $mins.Count; $idx++) {
        $v = $mins[$idx]
        if ((Test-IsNumber $v) -and ($v -lt 0)) {
            [void]$out.Add((New-Finding $SevError 'limit.period_negative' "$path.time_period_minima[$idx]" `
                        "${label}: time_period_minima[$idx] ($(Format-Num $v)) is negative" $v 'Per-period selections are non-negative.'))
        }
    }
    for ($idx = 0; $idx -lt $maxs.Count; $idx++) {
        $v = $maxs[$idx]
        if ((Test-IsNumber $v) -and ($v -lt 0)) {
            [void]$out.Add((New-Finding $SevError 'limit.period_negative' "$path.time_period_maxima[$idx]" `
                        "${label}: time_period_maxima[$idx] ($(Format-Num $v)) is negative" $v 'Per-period selections are non-negative.'))
        }
    }
    $shared = [Math]::Min($mins.Count, $maxs.Count)
    for ($idx = 0; $idx -lt $shared; $idx++) {
        $lo = $mins[$idx]; $hi = $maxs[$idx]
        if ((Test-IsNumber $lo) -and (Test-IsNumber $hi) -and ($hi -lt $lo)) {
            [void]$out.Add((New-Finding $SevError 'limit.period_max_lt_min' "$path.time_period_maxima[$idx]" `
                        "${label}: time_period_maxima[$idx] ($(Format-Num $hi)) < time_period_minima[$idx] ($(Format-Num $lo))" `
                        $hi 'Each per-period maximum must be >= the matching minimum.'))
        }
    }
    if ((Test-IsTrue (Get-Prop $limit 'integer_only')) -and ($null -ne (Get-Prop $limit 'interior_limit'))) {
        [void]$out.Add((New-Finding $SevWarning 'limit.interior_ignored' "$path.interior_limit" `
                    "${label}: interior_limit is ignored when integer_only is true" $null 'Drop interior_limit or set integer_only false.'))
    }
    $il = Get-NumOrNull $limit 'interior_limit'
    if (($null -ne $il) -and ($null -ne $tmax) -and ($il -gt $tmax)) {
        [void]$out.Add((New-Finding $SevWarning 'limit.interior_gt_max' "$path.interior_limit" `
                    "${label}: interior_limit ($(Format-Num $il)) > total_maximum ($(Format-Num $tmax))" $il 'Min Fraction should not exceed the total maximum.'))
    }
}

function Invoke-ExplicitNullChecks($node, $path, $out) {
    if (Test-IsObject $node) {
        foreach ($p in $node.PSObject.Properties) {
            $k = $p.Name; $v = $p.Value
            if ($null -eq $v) {
                [void]$out.Add((New-Finding $SevWarning 'style.explicit_null' "$path.$k" `
                            "'$k' is explicitly null; omit optional fields instead" $null 'Remove the key rather than writing null.'))
            } else {
                Invoke-ExplicitNullChecks $v "$path.$k" $out
            }
        }
    } elseif (Test-IsArray $node) {
        $i = 0
        foreach ($v in $node) { Invoke-ExplicitNullChecks $v "$path[$i]" $out; $i++ }
    }
}

# --------------------------------------------------------------------------- #
# Schema discovery (prefer an in-repo server copy over the bundled one).
# --------------------------------------------------------------------------- #
function Get-ServerSchemaWalkUp($startDir, $schemaFileName) {
    $dir = $null
    try { $dir = [System.IO.DirectoryInfo]$startDir } catch { return $null }
    while ($null -ne $dir) {
        $cand = Join-Path (Join-Path $dir.FullName 'server\Esi.Sp.Portable\Schemas') $schemaFileName
        if (Test-Path -LiteralPath $cand -PathType Leaf) { return $cand }
        $dir = $dir.Parent
    }
    return $null
}

function Find-Schema($explicit, $targetPath, $scriptRoot, $schemaFileName) {
    if ($explicit) { return @{ path = $explicit; source = 'explicit' } }
    $targetFull = [System.IO.Path]::GetFullPath($targetPath)
    $targetParent = [System.IO.Path]::GetDirectoryName($targetFull)
    foreach ($start in @($targetParent, (Get-Location).Path)) {
        $found = Get-ServerSchemaWalkUp $start $schemaFileName
        if ($found) { return @{ path = $found; source = 'server-in-repo' } }
    }
    $bundled = Join-Path (Join-Path (Split-Path -Parent $scriptRoot) 'schemas') $schemaFileName
    if (Test-Path -LiteralPath $bundled -PathType Leaf) { return @{ path = $bundled; source = 'bundled' } }
    return @{ path = $null; source = 'none' }
}

function Get-Sha256($path) {
    try { return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash } catch { return $null }
}

# --------------------------------------------------------------------------- #
# Emit helpers + text format (parity with Python _emit_*/_print_text).
# --------------------------------------------------------------------------- #
function Emit-IoError($fmt, $msg) {
    if ($fmt -eq 'json') {
        [Console]::Out.WriteLine((([ordered]@{ ok = $false; error = 'io'; message = $msg }) | ConvertTo-Json -Depth 5))
    } else {
        [Console]::Error.WriteLine("IO/PARSE ERROR: $msg")
    }
}

function Emit-EnvError($fmt, $msg) {
    if ($fmt -eq 'json') {
        [Console]::Out.WriteLine((([ordered]@{ ok = $false; error = 'environment'; message = $msg }) | ConvertTo-Json -Depth 5))
    } else {
        [Console]::Error.WriteLine("ENVIRONMENT ERROR: $msg")
    }
}

function Write-TextResult($result) {
    $s = $result.summary
    $status = if ($result.ok) { 'VALID' } else { 'INVALID' }
    [Console]::Out.WriteLine("$status  (schema=$($result.schema_source): $($result.schema_path_used))")
    if ($result.Contains('portfolio_path_used') -and $result.portfolio_path_used) {
        [Console]::Out.WriteLine("  portfolio=$($result.portfolio_path_used)")
    }
    [Console]::Out.WriteLine("  schema_errors=$($s.schema_errors) hard_errors=$($s.hard_errors) warnings=$($s.warnings)")
    if ($result.Contains('drift_warning')) { [Console]::Out.WriteLine("  ! $($result.drift_warning)") }
    foreach ($e in $result.schema_errors) {
        [Console]::Out.WriteLine("  [schema] $($e.json_path): $($e.message) ($($e.validator))")
    }
    foreach ($f in $result.semantic) {
        $tag = if ($f.severity -eq $SevError) { 'ERROR' } else { 'warn ' }
        [Console]::Out.WriteLine("  [$tag] $($f.check) @ $($f.json_path): $($f.message)")
        if ($f.hint) { [Console]::Out.WriteLine("          hint: $($f.hint)") }
    }
}

# --------------------------------------------------------------------------- #
# Generic driver shared by both validators. The per-skill driver supplies its
# semantic-check function by name and the schema/file-type specifics.
# --------------------------------------------------------------------------- #
function Invoke-QpValidation($Argv, $SchemaFileName, $ScriptRoot, $SemanticFn, [bool]$SupportsPortfolio) {
    $file = $null; $schemaArg = $null; $portfolioArg = $null; $fmt = 'json'; $strict = $false
    $pos = New-Object System.Collections.ArrayList
    for ($i = 0; $i -lt @($Argv).Count; $i++) {
        $a = $Argv[$i]
        if ($a -eq '--schema') { $i++; $schemaArg = $Argv[$i] }
        elseif ($a -eq '--portfolio') { $i++; $portfolioArg = $Argv[$i] }
        elseif ($a -eq '--format') { $i++; $fmt = $Argv[$i] }
        elseif ($a -eq '--strict-nulls') { $strict = $true }
        else { [void]$pos.Add($a) }
    }
    if ($pos.Count -ge 1) { $file = $pos[0] }
    if (-not $file) { Emit-IoError $fmt 'no input file given'; return 2 }

    $doc = Read-JsonDocument $file
    if (-not $doc.ok) { Emit-IoError $fmt $doc.message; return 2 }
    $data = $doc.data

    $disc = Find-Schema $schemaArg $file $ScriptRoot $SchemaFileName
    if ((-not $disc.path) -or (-not (Test-Path -LiteralPath $disc.path -PathType Leaf))) {
        Emit-EnvError $fmt "no $SchemaFileName found (server copy or bundled)"; return 3
    }
    try {
        $schema = [System.IO.File]::ReadAllText($disc.path, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
    } catch {
        Emit-EnvError $fmt "cannot load schema $($disc.path): $($_.Exception.Message)"; return 3
    }

    $portfolioNames = $null; $portfolioNote = $null
    if ($SupportsPortfolio -and $portfolioArg) {
        $pdoc = Read-JsonDocument $portfolioArg
        if ($pdoc.ok) { $portfolioNames = Get-PortfolioNames $pdoc.data }
        else { $portfolioNote = "could not load --portfolio $portfolioArg for cross-ref: $($pdoc.message)" }
    }

    $errs = New-Object System.Collections.ArrayList
    Invoke-SchemaNode $schema $data @() $schema $errs
    $schemaErrors = @(Sort-SchemaErrors $errs)

    $semantic = @(& $SemanticFn $data $strict $portfolioNames)
    if ($portfolioNote) {
        $note = New-Finding $SevWarning 'crossref.portfolio_unreadable' '$' $portfolioNote $null 'Fix the portfolio path/content to enable cross-reference checks.'
        $semantic = @($note) + $semantic
    }
    $hard = @($semantic | Where-Object { $_.severity -eq $SevError })
    $warns = @($semantic | Where-Object { $_.severity -eq $SevWarning })

    $drift = $null
    if ($disc.source -eq 'server-in-repo') {
        $bundled = Join-Path (Join-Path (Split-Path -Parent $ScriptRoot) 'schemas') $SchemaFileName
        if ((Test-Path -LiteralPath $bundled -PathType Leaf) -and ((Get-Sha256 $bundled) -ne (Get-Sha256 $disc.path))) {
            $drift = 'bundled schema differs from the in-repo server schema; run sync_schema.py'
        }
    }

    $ok = ($schemaErrors.Count -eq 0) -and ($hard.Count -eq 0)
    $result = [ordered]@{
        ok               = $ok
        schema_path_used = [string]$disc.path
        schema_source    = $disc.source
    }
    if ($SupportsPortfolio) {
        if ($portfolioArg) { $result['portfolio_path_used'] = [string]$portfolioArg } else { $result['portfolio_path_used'] = $null }
    }
    $result['summary'] = [ordered]@{
        schema_errors = $schemaErrors.Count
        hard_errors   = $hard.Count
        warnings      = $warns.Count
    }
    $result['schema_errors'] = [object[]]$schemaErrors
    $result['semantic'] = [object[]]$semantic
    if ($drift) { $result['drift_warning'] = $drift }

    if ($fmt -eq 'json') {
        [Console]::Out.WriteLine(($result | ConvertTo-Json -Depth 20))
    } else {
        Write-TextResult $result
    }
    if ($ok) { return 0 } else { return 1 }
}
