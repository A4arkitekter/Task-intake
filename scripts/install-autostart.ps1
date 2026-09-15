# Registrerer autostart ved login uden et vindue.
# Skal pege på Start-Indtagelse.ps1, ellers kan opdateringsknappen ikke genstarte.
# Bruger tre lag: planlagt opgave hvis muligt, ellers altid Startup-genvej og HKCU Run.
# Må ikke køres fra Git-udviklingsmappen. Kør som dig selv, ikke som administrator.
param([string]$InstallRoot = "")

$ErrorActionPreference = "Stop"

if ($InstallRoot) {
    $repo = [IO.Path]::GetFullPath($InstallRoot)
} else {
    $repo = (Resolve-Path "$PSScriptRoot\..").Path
}
$starter = Join-Path $repo "Start-Indtagelse.ps1"
$taskName = "Task-intake"
$powershell = Join-Path $PSHOME "powershell.exe"
$argument = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$starter`" -NoBrowser"
$autostartLog = Join-Path $repo "autostart-log.txt"

function Write-AutostartLog([string]$Message) {
    $line = "$(Get-Date -Format 'yyyy-MM-ddTHH:mm:ss') $Message"
    Add-Content -LiteralPath $autostartLog -Value $line -Encoding UTF8
}

if (-not (Test-Path -LiteralPath $starter -PathType Leaf)) {
    Write-Error "Mangler $starter."
}
if (Test-Path -LiteralPath (Join-Path $repo ".git") -PathType Container) {
    throw "Autostart maa ikke saettes fra Git-mappen ($repo). Koer scriptet fra den installerede kopi, typisk C:\apps\task-intake."
}

function Write-StartupShortcut {
    $startupDir = [Environment]::GetFolderPath("Startup")
    $lnk = Join-Path $startupDir "Indtagelse.lnk"
    $wsh = New-Object -ComObject WScript.Shell
    $shortcut = $wsh.CreateShortcut($lnk)
    $shortcut.TargetPath = $powershell
    $shortcut.Arguments = $argument
    $shortcut.WorkingDirectory = $repo
    $shortcut.WindowStyle = 7
    $shortcut.Description = "Starter stemmeindtagelsen ved login"
    $shortcut.Save()
    return $lnk
}

function Write-RunKey {
    $command = "`"$powershell`" $argument"
    $key = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
    New-Item -Path $key -Force | Out-Null
    Set-ItemProperty -Path $key -Name $taskName -Value $command
    return $command
}

$registeredTask = $false
try {
    $action = New-ScheduledTaskAction `
        -Execute $powershell `
        -Argument $argument `
        -WorkingDirectory $repo
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $trigger.Delay = "PT30S"
    $settings = New-ScheduledTaskSettingsSet `
        -MultipleInstances IgnoreNew `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit ([TimeSpan]::Zero)
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask `
        -TaskName $taskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description "Starter stemmeindtagelsen på http://127.0.0.1:8000" `
        -Force | Out-Null
    $registeredTask = $true
} catch {
    Write-AutostartLog "Planlagt opgave fejlede: $($_.Exception.Message)"
    Write-Host "Planlagt opgave kunne ikke oprettes ($($_.Exception.Message)). Bruger Startup og Run-nøgle i stedet." -ForegroundColor Yellow
}

$shortcut = Write-StartupShortcut
$runValue = Write-RunKey
Write-AutostartLog "Autostart sat til $starter (task=$registeredTask shortcut=$shortcut)"

Write-Host "Autostart er sat."
if ($registeredTask) {
    Write-Host "Planlagt opgave '$taskName' starter 30 sekunder efter login."
} else {
    Write-Host "Planlagt opgave mangler (ofte 'adgang nægtet'). Startup-genvej og Run-nøgle er sat."
}
Write-Host "Startup: $shortcut"
Write-Host "Run: $runValue"
Write-Host "Start nu med:  Start-Process -FilePath `"$powershell`" -ArgumentList '$argument'"
Write-Host "Fjern med: Unregister-ScheduledTask -TaskName $taskName -Confirm:`$false ; Remove-Item -LiteralPath `"$shortcut`" -ErrorAction SilentlyContinue ; Remove-ItemProperty -Path HKCU:\Software\Microsoft\Windows\CurrentVersion\Run -Name $taskName -ErrorAction SilentlyContinue"
