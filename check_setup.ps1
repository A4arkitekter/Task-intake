param(
    [switch]$ForceCpu,
    [string]$RuntimePath = "",
    [switch]$SkipRuntimeManifest
)

$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot
. (Join-Path $PSScriptRoot "tools\Install-Helpers.ps1")
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$script:fail = 0
$script:warn = 0
$contract = Get-Content -LiteralPath (Join-Path $PSScriptRoot "install-contract.json") -Raw | ConvertFrom-Json
$runtimeContract = Get-Content -LiteralPath (Join-Path $PSScriptRoot "runtime-contract.json") -Raw | ConvertFrom-Json
$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$runtime = if ($RuntimePath) { [System.IO.Path]::GetFullPath($RuntimePath) } else { Join-Path $PSScriptRoot "runtime" }

function Ok($message) { Write-Host "  OK   $message" -ForegroundColor Green }
function Fail($message) { Write-Host "  FEJL $message" -ForegroundColor Red; $script:fail++ }
function Warn($message) { Write-Host "  ADVARSEL $message" -ForegroundColor Yellow; $script:warn++ }

Write-Host ""
Write-Host "=== Indtagelse - systemtjek ===" -ForegroundColor Cyan
Write-Host "Projektmappe: $PWD"

if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
    $version = & $venvPython -c "import platform; print(platform.python_version())" 2>$null
    if ($LASTEXITCODE -eq 0 -and $version -eq [string]$contract.pythonVersion) {
        Ok "Python $version i projektets .venv"
    } else {
        Fail "Projektets .venv bruger Python $version; programversionen kræver $($contract.pythonVersion). Kør SETUP.bat"
    }
} else { Fail "Projektets .venv mangler. Kør SETUP.bat" }

if (Test-Path -LiteralPath ".env" -PathType Leaf) {
    Ok ".env findes lokalt og er udelukket fra Git"
} else { Warn ".env mangler; kør SETUP.bat" }

if (-not $SkipRuntimeManifest) {
    if (Test-Path -LiteralPath "$runtime\runtime-manifest.json" -PathType Leaf) {
        try {
            & (Join-Path $PSScriptRoot "Test-RuntimeManifest.ps1") -RuntimePath $runtime
            Ok "Runtime-manifest og GitHub-kontrakt er godkendt"
        } catch {
            Fail "Runtime passer ikke til programversionen: $($_.Exception.Message)"
        }
    } else {
        Fail "Runtime-manifest mangler. Kopiér HELE runtime-mappen fra $($contract.nasRuntime)"
    }
}

$modelRoot = Join-Path $PSScriptRoot "data\models"
$modelHint = Join-Path $modelRoot "models--Systran--faster-whisper-large-v3"
if (Test-Path -LiteralPath $modelHint -PathType Container) {
    Ok "Whisper $($runtimeContract.whisperModel) ligger lokalt"
} else {
    Warn "Whisper-modellen er ikke kopieret til data\models. Første start henter den fra nettet."
}

if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
    & $venvPython -c "import fastapi, faster_whisper, av" 2>$null
    if ($LASTEXITCODE -eq 0) { Ok "Python-pakkerne kan importeres" }
    else { Fail "Python-pakkerne kan ikke importeres. Kør SETUP.bat" }
}

$gpuName = if ($ForceCpu) { $null } else { Get-NvidiaGpuName }
if ($gpuName) { Ok "NVIDIA-GPU fundet: $gpuName" }
else { Ok "Ingen NVIDIA-GPU. Whisper og Ollama bruger CPU." }

$ollama = Get-Command "ollama.exe" -ErrorAction SilentlyContinue
if ($ollama) {
    Ok "Ollama er installeret"
    $listed = & $ollama.Source list 2>$null | Out-String
    if ($listed -match [regex]::Escape(([string]$runtimeContract.ollamaModel).Split(':')[0])) {
        Ok "Ollama-modellen $($runtimeContract.ollamaModel) er installeret"
    } else {
        Warn "Ollama-modellen $($runtimeContract.ollamaModel) mangler. Kør: ollama pull $($runtimeContract.ollamaModel)"
    }
} else {
    Warn "Ollama mangler. Overskrifter falder tilbage til rå Whisper-tekst, indtil den er installeret."
}

$inbox = Join-Path $env:USERPROFILE "Dropbox\Apps\ASRRecordings"
if (Test-Path -LiteralPath ".env" -PathType Leaf) {
    $inboxLine = Select-String -Path ".env" -Pattern '^\s*INBOX_DIR=(.+)$' | Select-Object -Last 1
    if ($inboxLine) { $inbox = $inboxLine.Matches[0].Groups[1].Value.Trim().Trim('"') }
}
if (Test-Path -LiteralPath $inbox -PathType Container) {
    Ok "Overvåget Dropbox-mappe findes: $inbox"
} else {
    Warn "Dropbox-mappen findes ikke endnu: $inbox. Sæt ASR Voice Recorder og Dropbox op (Android eller iPhone)."
}

try {
    $outlook = New-Object -ComObject Outlook.Application
    [void]$outlook
    Ok "Outlook kan åbnes fra denne computer"
} catch {
    Warn "Outlook svarede ikke. Wrike-mail og den daglige rykker kræver en kørende Outlook."
}

Write-Host ""
if ($script:fail -gt 0) {
    Write-Host "Systemtjekket fandt $script:fail fejl og $script:warn advarsler." -ForegroundColor Red
    exit 1
}
if ($script:warn -gt 0) {
    Write-Host "Systemtjekket er bestået med $script:warn advarsler." -ForegroundColor Yellow
    exit 0
}
Write-Host "Systemtjekket er bestået." -ForegroundColor Green
exit 0
