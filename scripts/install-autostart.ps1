# Registrerer en planlagt opgave, så indtagelsen starter ved login uden et vindue.
# Kør som dig selv, ikke som administrator.
$ErrorActionPreference = "Stop"

$repo = (Resolve-Path "$PSScriptRoot\..").Path
$pythonw = Join-Path $repo ".venv\Scripts\pythonw.exe"
$taskName = "Task-intake"

if (-not (Test-Path $pythonw)) {
    Write-Error "Mangler $pythonw. Opret .venv og kør pip install -r requirements.txt først."
}

$action = New-ScheduledTaskAction -Execute $pythonw -Argument "-m app" -WorkingDirectory $repo
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
