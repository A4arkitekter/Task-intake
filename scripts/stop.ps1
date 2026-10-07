# Stopper indtagelsen, uanset om den blev startet i en terminal eller af den planlagte opgave.
$ErrorActionPreference = "Stop"
$repo = (Resolve-Path "$PSScriptRoot\..").Path
$python = Join-Path $repo ".venv\Scripts\python.exe"
$port = 7000
if (Test-Path -LiteralPath $python -PathType Leaf) {
    $portText = & $python -c "from app.config import PORT; print(PORT)" 2>$null
    $configuredPort = 0
    if ($LASTEXITCODE -eq 0 -and [int]::TryParse(("$portText").Trim(), [ref]$configuredPort)) {
        $port = $configuredPort
    }
}

$stopped = $false

try {
    if (Get-ScheduledTask -TaskName "Task-intake" -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName "Task-intake" -ErrorAction SilentlyContinue
    }
} catch {}

# Supervisoren starter python -m app igen, hvis den får lov at leve.
$intakeProcesses = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" -ErrorAction SilentlyContinue)
foreach ($proc in $intakeProcesses) {
    $line = [string]$proc.CommandLine
    if (-not $line) { continue }
    if ($line.IndexOf($repo, [StringComparison]::OrdinalIgnoreCase) -lt 0) { continue }
    $isApp = $line -match '-m\s+app'
    $isSupervisor = $line -like "*service_supervisor.py*"
    if (-not ($isApp -or $isSupervisor)) { continue }
    Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
    Write-Host "Stoppede $($proc.Name) (PID $($proc.ProcessId))."
    $stopped = $true
}

$connections = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
foreach ($procId in ($connections.OwningProcess | Sort-Object -Unique)) {
    $process = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if (-not $process) { continue }
    if ($process.ProcessName -notin @("python", "pythonw")) {
        Write-Warning "Port $port holdes af $($process.ProcessName) (PID $procId). Rører den ikke."
        continue
    }
    Stop-Process -Id $procId -Force
    Write-Host "Stoppede $($process.ProcessName) (PID $procId)."
    $stopped = $true
}

if (-not $stopped) {
    Write-Host "Ingen indtagelse kørte på port $port."
}
