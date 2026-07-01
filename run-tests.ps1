<#
.SYNOPSIS
    Run the QP authoring plugin's tests.

.DESCRIPTION
    Runs the two validator regression suites and the full schema-coverage test.
    Stops at the first suite that fails (non-zero exit).

.PARAMETER Target
    Which suite to run: all (default), portfolio, scenario, or coverage.

.PARAMETER Python
    Python interpreter to use (default: python).

.EXAMPLE
    .\run-tests.ps1
    .\run-tests.ps1 -Target coverage
    .\run-tests.ps1 -Python python3
#>
[CmdletBinding()]
param(
    [ValidateSet('all', 'portfolio', 'scenario', 'coverage')]
    [string]$Target = 'all',
    [string]$Python = 'python'
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

# Ordered: name -> runner script (relative to this file).
$suites = [ordered]@{
    portfolio = 'skills/generate-portfolio-file/tests/run_tests.py'
    scenario  = 'skills/generate-scenario-file/tests/run_tests.py'
    coverage  = 'tests/run_coverage_tests.py'
}

if ($Target -eq 'all') {
    $toRun = $suites.Keys
} else {
    $toRun = @($Target)
}

foreach ($name in $toRun) {
    $script = Join-Path $root $suites[$name]
    Write-Host "=== $name suite ===" -ForegroundColor Cyan
    & $Python $script
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED: $name suite (exit $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

Write-Host "`nAll selected suites passed." -ForegroundColor Green
