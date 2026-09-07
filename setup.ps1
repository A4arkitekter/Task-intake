param(
    [switch]$ForceCpu,
    [switch]$SkipPackages,
    [switch]$SkipPythonInstall,
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
. (Join-Path $PSScriptRoot "tools\Install-Helpers.ps1")
$contractPath = Join-Path $PSScriptRoot "install-contract.json"
$contract = Get-Content -LiteralPath $contractPath -Raw | ConvertFrom-Json
$pythonVersion = [string]$contract.pythonVersion
$pythonInstallerSha256 = "edec09c4853aeae9ac36efb8c9f95b6b8e2fee65eee56d9767a8b7c69c574403"
$pythonDownloadAttempts = 2
$pythonDownloadTimeoutSeconds = 300
$pythonInstallerTimeoutSeconds = 900
$pythonTarget = Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"
$venvPath = Join-Path $PSScriptRoot ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
$logPath = Join-Path $PSScriptRoot "setup-log.txt"
$nasRuntime = [string]$contract.nasRuntime
$transcriptStarted = $false

function Write-Status {
    param(
        [Parameter(Mandatory = $true)][string]$Message,
        [ConsoleColor]$Color = [ConsoleColor]::Cyan
    )
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $Message" -ForegroundColor $Color
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

function Test-PythonVersion([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    $result = Invoke-ProcessCapture $Path '-c "import platform; print(platform.python_version())"'
    return ($result.ExitCode -eq 0 -and $result.Output -eq $pythonVersion)
}

function Find-Python {
    if (Test-PythonVersion $pythonTarget) { return $pythonTarget }
    $launcher = Get-Command "py.exe" -ErrorAction SilentlyContinue
    if ($launcher) {
        $result = Invoke-ProcessCapture $launcher.Source '-3.13 -c "import sys; print(sys.executable)"'
        $candidate = $result.Output
        if ($result.ExitCode -eq 0 -and $candidate -and (Test-PythonVersion $candidate)) { return $candidate }
    }
    $python = Get-Command "python.exe" -ErrorAction SilentlyContinue
    if ($python -and (Test-PythonVersion $python.Source)) { return $python.Source }
    return $null
}

function Install-Python {
    if ($SkipPythonInstall) { throw "Python $pythonVersion mangler, og installation blev fravalgt." }
    $installer = Join-Path ([System.IO.Path]::GetTempPath()) "python-$pythonVersion-amd64.exe"
    $url = "https://www.python.org/ftp/python/$pythonVersion/python-$pythonVersion-amd64.exe"
    try {
        $downloaded = $false
        for ($attempt = 1; $attempt -le $pythonDownloadAttempts; $attempt++) {
            try {
                if (Test-Path -LiteralPath $installer -PathType Leaf) { Remove-Item -LiteralPath $installer -Force }
                Write-Status "Henter Python $pythonVersion fra python.org (forsøg $attempt af $pythonDownloadAttempts) ..."
                Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $installer -TimeoutSec $pythonDownloadTimeoutSeconds
                $downloaded = $true
                break
            } catch {
                if ($attempt -eq $pythonDownloadAttempts) {
                    throw "Python kunne ikke hentes efter $attempt forsøg: $($_.Exception.Message)"
                }
                Write-Status "Downloadforsøget fejlede. Prøver automatisk én gang mere." Yellow
            }
        }
        if (-not $downloaded) { throw "Python-installeren blev ikke hentet." }
        $downloadMiB = [math]::Round((Get-Item -LiteralPath $installer).Length / 1MB, 1)
        Write-Status "Download færdig ($downloadMiB MB). Kontrollerer checksum og signatur ..."
        if ((Get-FileSha256 $installer) -ne $pythonInstallerSha256) {
            throw "Python-installeren har forkert checksum. Filen bruges ikke."
        }
        $signature = Get-AuthenticodeSignature -LiteralPath $installer
        if ($signature.Status -ne "Valid" -or $signature.SignerCertificate.Subject -notmatch "Python Software Foundation") {
            throw "Python-installeren har ikke en gyldig Python Software Foundation-signatur."
        }
        $targetDir = Split-Path -Parent $pythonTarget
        $arguments = "/quiet InstallAllUsers=0 PrependPath=0 Include_launcher=1 Include_test=0 TargetDir=`"$targetDir`""
        Write-Status "Starter Python-installationen. Se efter en Windows-dialog, som kan ligge bag dette vindue."
        $process = Start-Process -FilePath $installer -ArgumentList $arguments -PassThru
        $stopwatch = [Diagnostics.Stopwatch]::StartNew()
        $nextUpdate = 30
        while (-not $process.HasExited) {
            Start-Sleep -Seconds 1
            $process.Refresh()
            if ($stopwatch.Elapsed.TotalSeconds -ge $nextUpdate) {
                Write-Status "Python-installationen arbejder stadig ($([int]$stopwatch.Elapsed.TotalMinutes) min). Kontroller eventuelle Windows-dialoger."
                $nextUpdate += 30
            }
            if ($stopwatch.Elapsed.TotalSeconds -ge $pythonInstallerTimeoutSeconds) {
                try { $process.Kill() } catch { }
                throw "Python-installationen blev afbrudt efter $([int]$stopwatch.Elapsed.TotalMinutes) minutter uden at afslutte."
            }
        }
        $process.WaitForExit()
        if ($process.ExitCode -notin @(0, 3010) -or -not (Test-PythonVersion $pythonTarget)) {
            throw "Python-installation fejlede med kode $($process.ExitCode)."
        }
        Write-Status "Python $pythonVersion er installeret og kontrolleret." Green
        return $pythonTarget
    } finally {
        if (Test-Path -LiteralPath $installer -PathType Leaf) { Remove-Item -LiteralPath $installer -Force }
    }
}

function New-Secret([int]$Length = 32) {
    $chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    $bytes = New-Object byte[] $Length
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return -join ($bytes | ForEach-Object { $chars[$_ % $chars.Length] })
}

function Get-DefaultInboxDir {
    $dropbox = Join-Path $env:USERPROFILE "Dropbox"
    $candidates = @(
        (Join-Path $dropbox "Apps\ASRRecordings"),
        (Join-Path $dropbox "Apps\RecUp Memos"),
        (Join-Path $dropbox "Apps\RecUp"),
        (Join-Path $dropbox "RecUp")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Container) { return $candidate }
    }
    return $candidates[0]
}

function Initialize-LocalDataDirs {
    foreach ($dir in @(
        (Join-Path $PSScriptRoot "data\audio"),
        (Join-Path $PSScriptRoot "data\behandlet"),
        (Join-Path $PSScriptRoot "data\models")
    )) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

function Write-ColleagueEnv([bool]$UseGpu) {
    $envPath = Join-Path $PSScriptRoot ".env"
    if (Test-Path -LiteralPath $envPath -PathType Leaf) {
        Write-Status "Eksisterende .env bevares."
        return
    }
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot ".env.example") -Destination $envPath
    $password = New-Secret 12
    $secret = New-Secret 40
    $inbox = Get-DefaultInboxDir
    $mail = ""
    if (-not $NonInteractive) {
        Write-Host ""
        Write-Host "Android: ASR Voice Recorder -> Dropbox\Apps\ASRRecordings" -ForegroundColor Cyan
        Write-Host "iPhone: RecUp -> Dropbox\Apps\RecUp Memos (eller Apps\RecUp)" -ForegroundColor Cyan
        Write-Host "Optagelser hentes fra denne mappe:" -ForegroundColor Cyan
        Write-Host "  $inbox"
        $inboxTyped = Read-Host "Tryk Enter for at bruge den, eller skriv en anden sti"
        if ($inboxTyped.Trim()) { $inbox = $inboxTyped.Trim().Trim('"') }
        do {
            $mail = (Read-Host "Din arbejdmail (kopi på Wrike-mails og den daglige rykker)").Trim()
            if ($mail -notmatch '^[^@\s]+@[^@\s]+\.[^@\s]+$') {
                Write-Host "Skriv en gyldig mailadresse, for eksempel navn@a4.dk." -ForegroundColor Yellow
                $mail = ""
            }
        } while (-not $mail)
    } else {
        $mail = "kollega@a4.dk"
    }
    $device = if ($UseGpu) { "cuda" } else { "cpu" }
    $compute = if ($UseGpu) { "int8_float16" } else { "int8" }
    $modelDir = Join-Path $PSScriptRoot "data\models"
    $lines = Get-Content -LiteralPath $envPath
    $replacements = @{
        "APP_PASSWORD=skift-mig" = "APP_PASSWORD=$password"
        "SECRET_KEY=skift-denne-til-en-lang-tilfaeldig-streng" = "SECRET_KEY=$secret"
        "WHISPER_DEVICE=cpu" = "WHISPER_DEVICE=$device"
        "WHISPER_COMPUTE_TYPE=int8" = "WHISPER_COMPUTE_TYPE=$compute"
        "MAIL_CC=ep@a4.dk" = "MAIL_CC=$mail"
        "# INBOX_DIR=C:\Users\dig\Dropbox\Apps\ASRRecordings" = "INBOX_DIR=$inbox"
        "# REMIND_TO=dig@firma.dk" = "REMIND_TO=$mail"
    }
    $updated = foreach ($line in $lines) {
        $out = $line
        foreach ($key in $replacements.Keys) {
            if ($line -eq $key) { $out = $replacements[$key]; break }
        }
        $out
    }
    $updated += "MODEL_DIR=$modelDir"
    Set-Content -LiteralPath $envPath -Value $updated -Encoding utf8
    Write-Status "Adgangskoden til indbakken er: $password" Yellow
    Write-Status "Gem den. Den står også i den lokale .env, som aldrig må kopieres til NAS eller GitHub." Yellow
    if (-not (Test-Path -LiteralPath $inbox -PathType Container)) {
        Write-Status "Dropbox-mappen $inbox findes endnu ikke. Det er i orden — sæt ASR (Android) eller RecUp (iPhone) og Dropbox op bagefter." Yellow
    }
}

function Copy-WhisperRuntime {
    $destRoot = Join-Path $PSScriptRoot "data\models"
    $candidates = @(
        (Join-Path $PSScriptRoot "runtime\models--Systran--faster-whisper-large-v3"),
        (Join-Path $PSScriptRoot "runtime\whisper-large-v3"),
        (Join-Path $PSScriptRoot "runtime\huggingface\hub\models--Systran--faster-whisper-large-v3")
    )
    $source = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Container } | Select-Object -First 1
    if (-not $source) {
        Write-Status "Ingen Whisper-model i runtime. Foerste start henter den fra nettet (cirka 2,9 GB)." Yellow
        return
    }
    $name = Split-Path -Leaf $source
    if ($name -eq "whisper-large-v3") { $name = "models--Systran--faster-whisper-large-v3" }
    $dest = Join-Path $destRoot $name
    if (Test-Path -LiteralPath $dest -PathType Container) {
        Write-Status "Whisper-modellen ligger allerede lokalt."
        return
    }
    Write-Status "Kopierer Whisper large-v3 fra runtime ..."
    New-Item -ItemType Directory -Path $destRoot -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $dest -Recurse -Force
}

function Install-OllamaRuntime {
    $ollama = Get-Command "ollama.exe" -ErrorAction SilentlyContinue
    if (-not $ollama) {
        $setup = @(
            (Join-Path $PSScriptRoot "runtime\OllamaSetup.exe"),
            (Join-Path $PSScriptRoot "runtime\ollama\OllamaSetup.exe")
        ) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
        if (-not $setup) {
            Write-Status "Ollama mangler, og installeren ligger ikke i runtime. Installér Ollama manuelt, eller læg OllamaSetup.exe i runtime." Yellow
            return
        }
        Write-Status "Installerer Ollama fra runtime ..."
        $process = Start-Process -FilePath $setup -ArgumentList "/VERYSILENT" -PassThru -Wait
        if ($process.ExitCode -notin @(0, 3010)) {
            throw "Ollama-installationen fejlede med kode $($process.ExitCode)."
        }
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
        $ollama = Get-Command "ollama.exe" -ErrorAction SilentlyContinue
    }
    if (-not $ollama) {
        Write-Status "Ollama blev ikke fundet på PATH efter installationen. Start computeren igen, og kør SETUP.bat." Yellow
        return
    }

    $modelSource = Join-Path $PSScriptRoot "runtime\ollama-models"
    $modelDest = Join-Path $env:USERPROFILE ".ollama\models"
    if ((Test-Path -LiteralPath $modelSource -PathType Container) -and -not (Test-Path -LiteralPath $modelDest -PathType Container)) {
        Write-Status "Kopierer Ollama-modellen fra runtime ..."
        New-Item -ItemType Directory -Path (Split-Path -Parent $modelDest) -Force | Out-Null
        Copy-Item -LiteralPath $modelSource -Destination $modelDest -Recurse -Force
    }

    $contractRt = Get-Content -LiteralPath (Join-Path $PSScriptRoot "runtime-contract.json") -Raw | ConvertFrom-Json
    $wanted = [string]$contractRt.ollamaModel
    $listed = & $ollama.Source list 2>$null | Out-String
    if ($listed -notmatch [regex]::Escape($wanted.Split(':')[0])) {
        Write-Status "Henter Ollama-modellen $wanted (kan tage tid) ..."
        & $ollama.Source pull $wanted
        if ($LASTEXITCODE -ne 0) {
            Write-Status "Ollama kunne ikke hente $wanted. Kør 'ollama pull $wanted' senere." Yellow
        }
    } else {
        Write-Status "Ollama-modellen $wanted er allerede installeret." Green
    }
}

try {
    try {
        Start-Transcript -LiteralPath $logPath -Force | Out-Null
        $transcriptStarted = $true
    } catch {
        Write-Host "ADVARSEL Installationsloggen kunne ikke oprettes: $($_.Exception.Message)" -ForegroundColor Yellow
    }

    Write-Status "=== Trin 1 af 5: Kontrollerer computer og runtime ==="
    if (-not [Environment]::Is64BitOperatingSystem) { throw "Programmet kræver 64-bit Windows 10 eller 11." }
    $runtimeManifest = Join-Path $PSScriptRoot "runtime\runtime-manifest.json"
    if (-not (Test-Path -LiteralPath $runtimeManifest -PathType Leaf)) {
        throw "RUNTIME MANGLER. GitHub indeholder kun programkoden. Kopiér HELE runtime-mappen fra $nasRuntime, så filen findes her: $runtimeManifest"
    }
    & (Join-Path $PSScriptRoot "Test-RuntimeManifest.ps1")

    if (-not (Test-Path -LiteralPath $venvPython) -and -not $SkipPackages) {
        $driveRoot = [System.IO.Path]::GetPathRoot($PSScriptRoot)
        $freeGiB = [math]::Floor(([System.IO.DriveInfo]::new($driveRoot)).AvailableFreeSpace / 1GB)
        if ($freeGiB -lt [int]$contract.minimumFreeDiskGiB) {
            throw "Der er kun $freeGiB GB ledig plads. Førstegangsinstallationen kræver mindst $($contract.minimumFreeDiskGiB) GB ledig plads."
        }
    }

    Write-Status "=== Trin 2 af 5: Kontrollerer Python ==="
    if ($ForceCpu) { $env:FORCE_CPU = "1" }

    if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
        $venvVersion = & $venvPython -c "import platform; print(platform.python_version())" 2>$null
        if ($LASTEXITCODE -ne 0 -or $venvVersion -ne $pythonVersion) {
            Write-Status "Den eksisterende .venv bruger Python $venvVersion og genopbygges med $pythonVersion." Yellow
            Remove-Item -LiteralPath $venvPath -Recurse -Force
        }
    }
    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
        $basePython = Find-Python
        if (-not $basePython) { $basePython = Install-Python }
        Write-Status "Opretter lokal .venv med Python $pythonVersion ..."
        Invoke-NativeCommand "Oprettelse af .venv" $basePython @("-m", "venv", $venvPath)
    }

    Write-Status "=== Trin 3 af 5: Installerer Python-pakker ==="
    $useGpu = $false
    if (-not $SkipPackages) {
        $backend = if ($ForceCpu) { "CPU" } else { "Auto" }
        & (Join-Path $PSScriptRoot "install.ps1") -Backend $backend -PythonPath $venvPython
        $pkgExit = $LASTEXITCODE
        if ($pkgExit -notin @(0, 10)) { throw "Installation af pakker fejlede med kode $pkgExit." }
        $useGpu = ($pkgExit -eq 10)
    } elseif (-not $ForceCpu) {
        $useGpu = [bool](Get-NvidiaGpuName)
    }

    Write-Status "=== Trin 4 af 5: Lokal konfiguration, Whisper og Ollama ==="
    Initialize-LocalDataDirs
    Write-ColleagueEnv -UseGpu $useGpu
    Copy-WhisperRuntime
    Install-OllamaRuntime

    $winapp = Join-Path $PSScriptRoot "scripts\register-windows.ps1"
    if (Test-Path -LiteralPath $winapp -PathType Leaf) {
        & (Join-Path $PSHOME "powershell.exe") -NoProfile -ExecutionPolicy Bypass -File $winapp
    } else {
        & $venvPython -c "from app.winapp import register; register()"
    }

    $autostart = Join-Path $PSScriptRoot "scripts\install-autostart.ps1"
    if (Test-Path -LiteralPath $autostart -PathType Leaf) {
        & (Join-Path $PSHOME "powershell.exe") -NoProfile -ExecutionPolicy Bypass -File $autostart
    }

    Write-Status "=== Trin 5 af 5: Kører samlet systemtjek ==="
    & (Join-Path $PSScriptRoot "check_setup.ps1") -ForceCpu:$ForceCpu -SkipRuntimeManifest
    if ($LASTEXITCODE -ne 0) { throw "Systemtjekket fandt fejl. Se setup-log.txt." }

    $stateFiles = @("install-contract.json", "runtime-contract.json", "requirements.txt", "requirements-lock.txt")
    $stateHashes = [ordered]@{}
    foreach ($file in $stateFiles) {
        $stateHashes[$file] = Get-FileSha256 (Join-Path $PSScriptRoot $file)
    }
    [ordered]@{
        schema = 1
        installedUtc = [DateTime]::UtcNow.ToString("o")
        pythonVersion = $pythonVersion
        files = $stateHashes
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $PSScriptRoot "install-state.json") -Encoding utf8

    Write-Status "Opsætning færdig og registreret. Programmet starter ved login. Start nu med START.bat." Green
} finally {
    if ($transcriptStarted) { try { Stop-Transcript | Out-Null } catch { } }
}
