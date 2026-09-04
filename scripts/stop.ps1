# Stopper indtagelsen, uanset om den blev startet i en terminal eller af den planlagte opgave.
$ErrorActionPreference = "Stop"

$stopped = $false

try {
    if (Get-ScheduledTask -TaskName "Task-intake" -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName "Task-intake" -ErrorAction SilentlyContinue
    }
} catch {}

$connections = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
foreach ($procId in ($connections.OwningProcess | Sort-Object -Unique)) {
    $process = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if (-not $process) { continue }
    if ($process.ProcessName -notin @("python", "pythonw")) {
        Write-Warning "Port 8000 holdes af $($process.ProcessName) (PID $procId). Rører den ikke."
        continue
    }
    Stop-Process -Id $procId -Force
    Write-Host "Stoppede $($process.ProcessName) (PID $procId)."
    $stopped = $true
}

if (-not $stopped) {
    Write-Host "Ingen indtagelse kørte på port 8000."
}
