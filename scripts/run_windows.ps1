param(
    [Parameter()]
    [string]$ProjectConfig,

    [Parameter()]
    [switch]$PreviewOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location "$scriptDir\.."

$venvPath = Join-Path $PWD ".venv"
if (-not (Test-Path $venvPath)) {
    py -3 -m venv $venvPath
}

& "$venvPath\Scripts\Activate.ps1"

$pythonExe = Join-Path $venvPath "Scripts/python.exe"
$requirementsFile = Join-Path $PWD "requirements.txt"
$packageInstalled = $false
$dependenciesHealthy = $false

& $pythonExe -m pip show ski-terrain-generator | Out-Null
if ($LASTEXITCODE -eq 0) {
    $packageInstalled = $true
}

if ($packageInstalled) {
    & $pythonExe -m pip check | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $dependenciesHealthy = $true
    }
}

if (-not $dependenciesHealthy) {
    & $pythonExe -m pip install --upgrade pip
    if (Test-Path $requirementsFile) {
        & $pythonExe -m pip install -r $requirementsFile
    }
    & $pythonExe -m pip install -e .
}

if ([string]::IsNullOrWhiteSpace($ProjectConfig)) {
    $ProjectConfig = Read-Host "Enter the project YAML path (default: config/projects/example.yml)"
}

if ([string]::IsNullOrWhiteSpace($ProjectConfig)) {
    $ProjectConfig = "config/projects/example.yml"
}

$cliArgs = @($ProjectConfig)
if ($PreviewOnly) {
    $cliArgs += "--preview-only"
}

ski-terrain @cliArgs

Read-Host "Press Enter to exit"
