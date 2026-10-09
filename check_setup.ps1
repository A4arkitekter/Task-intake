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

$ollamaExe = $null
$ollamaCmd = Get-Command "ollama.exe" -ErrorAction SilentlyContinue
if ($ollamaCmd) { $ollamaExe = $ollamaCmd.Source }
if (-not $ollamaExe) {
    foreach ($path in @(
        (Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"),
        (Join-Path ${env:ProgramFiles} "Ollama\ollama.exe")
    )) {
        if ($path -and (Test-Path -LiteralPath $path -PathType Leaf)) { $ollamaExe = $path; break }
    }
}
if ($ollamaExe) {
    Ok "Ollama er installeret"
    if (Test-OllamaBlobsPresent) { Ok "Ollama-modellen ligger lokalt" }
    else { Warn "Ollama-modellen mangler. Kopiér runtime\ollama-models fra NAS ind i programmets runtime-mappe, og kør SETUP.bat igen." }
} else {
    Warn "Ollama mangler. Overskrifter falder tilbage til rå Whisper-tekst, indtil den er installeret."
}

$inbox = Join-Path $env:USERPROFILE "OneDrive\Apps\ASR Cloud Uploads\asr"
if (Test-Path -LiteralPath ".env" -PathType Leaf) {
    $inboxLine = Select-String -Path ".env" -Pattern '^\s*INBOX_DIR=(.+)$' | Select-Object -Last 1
    if ($inboxLine) { $inbox = $inboxLine.Matches[0].Groups[1].Value.Trim().Trim('"') }
}
if (Test-Path -LiteralPath "data\admin-settings.json" -PathType Leaf) {
    $settingsLine = Select-String -Path "data\admin-settings.json" -Pattern '"inbox_dir"\s*:\s*"([^"]+)"' | Select-Object -Last 1
    if ($settingsLine) { $inbox = $settingsLine.Matches[0].Groups[1].Value.Trim() }
}
if (Test-Path -LiteralPath $inbox -PathType Container) {
    Ok "Overvåget optagelsesmappe findes: $inbox"
} else {
    Warn "Optagelsesmappen findes ikke endnu: $inbox. Sæt ASR Voice Recorder (Android) eller RecUp (iPhone) op med OneDrive. Stien kan rettes i browseren."
}

$tokenSet = $false
$clientSet = $false
$secretSet = $false
if (Test-Path -LiteralPath ".env" -PathType Leaf) {
    $tokenLine = Select-String -Path ".env" -Pattern '^\s*WRIKE_TOKEN=(.+)$' | Select-Object -Last 1
    $clientLine = Select-String -Path ".env" -Pattern '^\s*WRIKE_CLIENT_ID=(.+)$' | Select-Object -Last 1
    $secretLine = Select-String -Path ".env" -Pattern '^\s*WRIKE_CLIENT_SECRET=(.+)$' | Select-Object -Last 1
    if ($tokenLine -and $tokenLine.Matches[0].Groups[1].Value.Trim()) { $tokenSet = $true }
    if ($clientLine -and $clientLine.Matches[0].Groups[1].Value.Trim()) { $clientSet = $true }
    if ($secretLine -and $secretLine.Matches[0].Groups[1].Value.Trim()) { $secretSet = $true }
}
if ($tokenSet -and $clientSet -and $secretSet) {
    Ok "Wrikes tre nøgler er sat (Client ID, Client secret og token)."
} else {
    Warn "Wrikes nøgler mangler. Åbn http://127.0.0.1:7000 og udfyld Client ID, Client secret og Get token i browseren. Log ind i Wrike som dig selv."
}

try {
    $outlook = New-Object -ComObject Outlook.Application
    [void]$outlook
    Ok "Outlook kan åbnes fra denne computer"
} catch {
    Warn "Outlook svarede ikke. Den daglige rykker kræver en kørende Outlook."
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
