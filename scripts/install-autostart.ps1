# Registrerer en planlagt opgave, så indtagelsen starter ved login uden et vindue.
# Autostart skal pege på Start-Indtagelse.ps1. Ellers kan opdateringsknappen ikke genstarte.
# Kør som dig selv, ikke som administrator.
$ErrorActionPreference = "Stop"

$repo = (Resolve-Path "$PSScriptRoot\..").Path
$starter = Join-Path $repo "Start-Indtagelse.ps1"
$taskName = "Task-intake"

if (-not (Test-Path -LiteralPath $starter -PathType Leaf)) {
    Write-Error "Mangler $starter."
}

$action = New-ScheduledTaskAction `
    -Execute (Join-Path $PSHOME "powershell.exe") `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$starter`" -NoBrowser" `
    -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Starter stemmeindtagelsen på http://127.0.0.1:8000" `
    -Force | Out-Null

Write-Host "Opgaven '$taskName' er registreret og starter ved login."
Write-Host "Start den nu med:  Start-ScheduledTask -TaskName $taskName"
Write-Host "Fjern den igen med: Unregister-ScheduledTask -TaskName $taskName -Confirm:`$false"
