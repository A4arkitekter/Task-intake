param(
    [ValidateSet("Auto", "GPU", "CPU")]
    [string]$Backend = "Auto",
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
. (Join-Path $PSScriptRoot "tools\Install-Helpers.ps1")
$contract = Get-Content -LiteralPath (Join-Path $PSScriptRoot "install-contract.json") -Raw | ConvertFrom-Json
if (-not $PythonPath) { $PythonPath = Join-Path $PSScriptRoot ".venv\Scripts\python.exe" }
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Python i projektets .venv blev ikke fundet. Kør SETUP.bat."
}

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    & $FilePath @Arguments
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) { throw "$Label fejlede med kode $exitCode." }
}

$requestedBackend = $Backend
if ($Backend -eq "Auto") {
    $hasNvidia = $false
    if (-not ($env:FORCE_CPU -match '^(1|true|yes|on)$')) {
        $hasNvidia = [bool](Get-NvidiaGpuName)
    }
    $Backend = if ($hasNvidia) { "GPU" } else { "CPU" }
}

Write-Host "Opgraderer installationsværktøjer i .venv ..." -ForegroundColor Cyan
Invoke-NativeCommand "Installation af pip/setuptools/wheel" $PythonPath @(
    "-m", "pip", "install", "--disable-pip-version-check", "--upgrade",
    "pip==$($contract.pipVersion)",
    "setuptools==$($contract.setuptoolsVersion)",
    "wheel==$($contract.wheelVersion)"
)

Write-Host "Installerer de låste programafhængigheder ..." -ForegroundColor Cyan
Invoke-NativeCommand "Installation af requirements.txt" $PythonPath @(
    "-m", "pip", "install", "--disable-pip-version-check",
    "-r", (Join-Path $PSScriptRoot "requirements.txt"),
    "-c", (Join-Path $PSScriptRoot "requirements-lock.txt")
)

if ($Backend -eq "GPU") {
    Write-Host "Installerer CUDA-biblioteker til Whisper på GPU ..." -ForegroundColor Cyan
    $gpuReq = Join-Path $PSScriptRoot "requirements-gpu.txt"
    $gpuArgs = @(
        "-m", "pip", "install", "--disable-pip-version-check",
        "-r", $gpuReq
    )
    $wheelDir = Join-Path $PSScriptRoot "runtime\gpu"
    if (Test-Path -LiteralPath $wheelDir -PathType Container) {
        $gpuArgs += @("--find-links", $wheelDir, "--no-index")
        Write-Host "Bruger GPU-hjul fra runtime\gpu (NAS)." -ForegroundColor Cyan
    }
    Invoke-NativeCommand "Installation af GPU-pakker" $PythonPath $gpuArgs
}

Invoke-NativeCommand "Kontrol af Python-afhængigheder" $PythonPath @("-m", "pip", "check")
Invoke-NativeCommand "Kontrol af programimport" $PythonPath @(
    "-c",
    "import fastapi, faster_whisper, av; print('FastAPI/Whisper OK')"
)

if ($Backend -eq "GPU") {
    & $PythonPath -c "import ctranslate2, sys; sys.exit(0 if ctranslate2.get_cuda_device_count() else 1)"
    if ($LASTEXITCODE -ne 0) {
        if ($requestedBackend -eq "GPU") {
            throw "GPU blev krævet, men CTranslate2 kan ikke bruge CUDA."
        }
        Write-Host "ADVARSEL NVIDIA blev fundet, men CUDA virker ikke. Whisper bruger CPU." -ForegroundColor Yellow
        $Backend = "CPU"
    }
}
Write-Host "Python-pakkerne er installeret og kontrolleret ($Backend)." -ForegroundColor Green
if ($Backend -eq "GPU") { exit 10 } else { exit 0 }
