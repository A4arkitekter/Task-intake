param([switch]$NoBrowser)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Stop-Start([string]$Message) {
    Write-Host ""
    Write-Host "FEJL: $Message" -ForegroundColor Red
    exit 1
}

function Write-BrowserUpdateResult([bool]$Ok, [string]$Code) {
    $resultPath = Join-Path $PSScriptRoot ".browser-update-result.json"
    $payload = [ordered]@{
        ok = $Ok
        code = $Code
        completedUtc = [DateTime]::UtcNow.ToString("o")
    } | ConvertTo-Json -Compress
    [IO.File]::WriteAllText($resultPath, $payload, (New-Object Text.UTF8Encoding($false)))
}

function Test-LocalPortInUse([int]$Port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $connection = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        if (-not $connection.AsyncWaitHandle.WaitOne(750)) { return $false }
        $client.EndConnect($connection)
        return $true
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

Write-Host "========================================"
Write-Host " Indtagelse"
Write-Host "========================================"
Write-Host ""

$runtimeManifest = Join-Path $PSScriptRoot "runtime\runtime-manifest.json"
$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot "app\main.py") -PathType Leaf)) {
    Stop-Start "Programfilerne mangler. Koer OPDATER.bat. Kontakt IT, hvis filerne stadig mangler."
}
if (-not (Test-Path -LiteralPath $runtimeManifest -PathType Leaf)) {
    Stop-Start "Runtime mangler. Kopier HELE runtime-mappen fra \\a4diskstation4\A4software\task-intake\runtime, og koer SETUP.bat."
}
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    Stop-Start "Den lokale installation mangler. Koer SETUP.bat."
}

$portText = & $venvPython -c "from app.config import PORT; print(PORT)" 2>&1
$port = 0
if ($LASTEXITCODE -ne 0 -or -not [int]::TryParse(("$portText").Trim(), [ref]$port) -or $port -lt 1 -or $port -gt 65535) {
    Stop-Start "PORT i .env er ugyldig. Koer SYSTEMTJEK.bat."
}
$url = "http://127.0.0.1:$port"

$stateCheck = Join-Path $PSScriptRoot "Test-InstallState.ps1"
& (Join-Path $PSHOME "powershell.exe") -NoProfile -ExecutionPolicy Bypass -File $stateCheck
if ($LASTEXITCODE -ne 0) {
    Stop-Start "Installationen skal opdateres. Koer SETUP.bat en gang, og start derefter igen."
}

$health = $null
try {
    $health = Invoke-RestMethod -Uri "$url/api/health" -TimeoutSec 3
} catch { }

if ($health -and $health.ok) {
    Write-Host "Programmet koerer allerede. Browseren aabnes igen." -ForegroundColor Green
    if (-not $NoBrowser) { Start-Process -FilePath $url }
    exit 0
}

if (Test-LocalPortInUse -Port $port) {
    Stop-Start "Port $port bruges af et andet program. Luk det program, eller kontakt IT. Ingen processer stoppes automatisk."
}

Write-Host "Browseren aabnes automatisk, naar serveren er klar."
Write-Host "Manuel adresse: $url"
Write-Host ""

if (-not $NoBrowser) { $env:OPEN_BROWSER = "1" }
while ($true) {
    & $venvPython -m app
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 42) { break }

    Write-Host ""
    Write-Host "Browseren har bedt om en opdatering. Vent mens programmet opdateres..." -ForegroundColor Cyan
    $updater = Join-Path $PSScriptRoot "Update-Intake.ps1"
    & (Join-Path $PSHOME "powershell.exe") -NoProfile -ExecutionPolicy Bypass -File $updater
    $updateExitCode = $LASTEXITCODE
    if ($updateExitCode -ne 0) {
        Write-BrowserUpdateResult $false "update_failed"
        $env:OPEN_BROWSER = "0"
        continue
    }

    & (Join-Path $PSHOME "powershell.exe") -NoProfile -ExecutionPolicy Bypass -File $stateCheck -Quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Opdateringen kraever en automatisk tilpasning af installationen..." -ForegroundColor Yellow
        & (Join-Path $PSHOME "powershell.exe") -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "setup.ps1") -NonInteractive
        if ($LASTEXITCODE -ne 0) {
            Write-BrowserUpdateResult $false "setup_failed"
            Stop-Start "Opdateringen kraever SETUP.bat."
        }
    }

    Write-BrowserUpdateResult $true "updated"
    Write-Host "Programmet er opdateret og starter igen..." -ForegroundColor Green
    $env:OPEN_BROWSER = "0"
}

Write-Host ""
if ($exitCode -ne 0) {
    Write-Host "Serveren stoppede med fejlkode $exitCode." -ForegroundColor Red
    Write-Host "Koer SYSTEMTJEK.bat; den opretter fejlrapport.zip til IT." -ForegroundColor Yellow
    exit $exitCode
}

Write-Host "Serveren er stoppet."
exit 0
