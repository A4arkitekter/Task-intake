param([switch]$Quiet)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "tools\Install-Helpers.ps1")
Set-Location $PSScriptRoot
$statePath = Join-Path $PSScriptRoot "install-state.json"
$contract = Get-Content -LiteralPath (Join-Path $PSScriptRoot "install-contract.json") -Raw | ConvertFrom-Json
$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

function Fail-State([string]$Message) {
    if (-not $Quiet) { Write-Host "INSTALLATION SKAL OPDATERES: $Message" -ForegroundColor Yellow }
    exit 1
}

if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) {
    Fail-State "install-state.json mangler. Kør SETUP.bat."
}
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    Fail-State ".venv mangler. Kør SETUP.bat."
}

$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
$pythonVersion = & $venvPython -c "import platform; print(platform.python_version())" 2>$null
if ($LASTEXITCODE -ne 0 -or $pythonVersion -ne [string]$contract.pythonVersion) {
    Fail-State "Python-miljøet matcher ikke programversionen. Kør SETUP.bat."
}

$requiredFiles = @("install-contract.json", "runtime-contract.json", "requirements.txt", "requirements-lock.txt")
foreach ($file in $requiredFiles) {
    $expected = [string]$state.files.$file
    $actual = Get-FileSha256 (Join-Path $PSScriptRoot $file)
    if (-not $expected -or $actual -ne $expected) {
        Fail-State "GitHub har ændret installationskravene ($file). Kør SETUP.bat igen."
    }
}

if (-not $Quiet) { Write-Host "Installationen matcher programversionen." -ForegroundColor Green }
exit 0
