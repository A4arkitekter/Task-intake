param(
    [string]$Source,
    [switch]$Automatic,
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
if ($CheckOnly) {
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
}
Set-Location $PSScriptRoot
$defaultSource = "\\a4diskstation4\A4software\task-intake\updates"
$stateFile = Join-Path $PSScriptRoot ".update-state.json"
$protectedRoots = @(".git", ".venv", "runtime", "data")
$protectedFiles = @(
    ".env", "install-state.json", "setup-log.txt", "systemtjek.txt",
    "fejlrapport.zip", "update-source.txt", ".update-state.json",
    ".browser-update-result.json"
)

function Test-SmbSourceAvailable([string]$Path) {
    if (-not $Path.StartsWith("\\")) { return $true }
    $parts = $Path.TrimStart('\').Split('\')
    if (-not $parts.Count -or -not $parts[0]) { return $false }
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $connection = $client.BeginConnect($parts[0], 445, $null, $null)
        if (-not $connection.AsyncWaitHandle.WaitOne(3000)) { return $false }
        $client.EndConnect($connection)
        return $true
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Get-SafeTarget([string]$RelativePath) {
    $normalized = ($RelativePath -replace '\\', '/').TrimStart('/')
    if (-not $normalized -or [IO.Path]::IsPathRooted($RelativePath)) {
        throw "Ugyldig filsti i opdateringen: $RelativePath"
    }
    $segments = @($normalized.Split('/'))
    if ($segments -contains ".." -or $segments[0] -in $protectedRoots -or $normalized -in $protectedFiles) {
        throw "Opdateringen forsoeger at aendre en lokal eller beskyttet fil: $RelativePath"
    }
    $root = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\') + '\'
    $target = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ($normalized -replace '/', '\')))
    if (-not $target.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Filstien forlader projektmappen: $RelativePath"
    }
    return $target
}

function Get-FileSha256([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace("-", "").ToLowerInvariant()
    } finally {
        $sha.Dispose()
        $stream.Dispose()
    }
}

function Test-IntakeServerRunning {
    $python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { return $false }
    try {
        $portText = & $python -c "from app.config import PORT; print(PORT)" 2>$null
        if ($LASTEXITCODE -ne 0) { return $false }
        $port = 0
        if (-not [int]::TryParse(([string]($portText | Select-Object -Last 1)).Trim(), [ref]$port)) {
            return $false
        }
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/health" -TimeoutSec 2
        return [bool]$health.ok
    } catch {
        return $false
    }
}

try {
    if ($PSScriptRoot.StartsWith("\\")) {
        throw "OPDATER.bat maa ikke koeres fra NAS'en. Kopier OPDATER.bat og Update-Intake.ps1 til computerens lokale programmappe, og koer den der."
    }
    if (Test-Path -LiteralPath (Join-Path $PSScriptRoot ".git") -PathType Container) {
        throw "Dette er en udviklingsmappe med Git. Opdater den med Git i stedet."
    }
    if (-not $CheckOnly -and (Test-IntakeServerRunning)) {
        if ($Automatic) { exit 0 }
        throw "Programmet koerer. Stop det med scripts\stop.ps1, og proev igen."
    }

    if (-not $Source) { $Source = $defaultSource }
    $Source = [IO.Path]::GetFullPath($Source)
    if (-not (Test-SmbSourceAvailable $Source)) {
        throw "Firmaets opdateringsmappe kan ikke kontaktes: $Source"
    }
    $latestPath = Join-Path $Source "latest.json"
    if (-not (Test-Path -LiteralPath $latestPath -PathType Leaf)) {
        throw "Firmaets opdateringsmappe indeholder ikke latest.json: $Source"
    }

    $latest = Get-Content -LiteralPath $latestPath -Raw | ConvertFrom-Json
    if ([int]$latest.schema -ne 1 -or -not $latest.version -or -not $latest.package) {
        throw "Opdateringsbeskrivelsen har et ukendt format."
    }
    $current = $null
    if (Test-Path -LiteralPath $stateFile -PathType Leaf) {
        $current = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
        if ([string]$current.version -eq [string]$latest.version) {
            if ($CheckOnly) {
                [ordered]@{
                    ok = $true
                    updateAvailable = $false
                    currentVersion = [string]$current.version
                    latestVersion = [string]$latest.version
                } | ConvertTo-Json -Compress
                exit 0
            }
            if (-not $Automatic) { Write-Host "Programmet er allerede opdateret ($($latest.version))." -ForegroundColor Green }
            exit 0
        }
    }

    if ($CheckOnly) {
        [ordered]@{
            ok = $true
            updateAvailable = $true
            currentVersion = if ($current) { [string]$current.version } else { $null }
            latestVersion = [string]$latest.version
        } | ConvertTo-Json -Compress
        exit 0
    }

    $packagePath = Join-Path $Source ([string]$latest.package)
    if (-not (Test-Path -LiteralPath $packagePath -PathType Leaf)) {
        throw "Opdateringspakken mangler: $packagePath"
    }
    if ([long]$latest.size -ne (Get-Item -LiteralPath $packagePath).Length) {
        throw "Opdateringspakken har forkert stoerrelse."
    }
    if ((Get-FileSha256 $packagePath) -ne ([string]$latest.sha256).ToLowerInvariant()) {
        throw "Opdateringspakken har forkert checksum og anvendes ikke."
    }

    $tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("intake-update-" + [Guid]::NewGuid().ToString("N"))
    $extractRoot = Join-Path $tempRoot "package"
    $backupRoot = Join-Path $tempRoot "backup"
    New-Item -ItemType Directory -Path $extractRoot,$backupRoot -Force | Out-Null
    try {
        Expand-Archive -LiteralPath $packagePath -DestinationPath $extractRoot -Force
        $manifestPath = Join-Path $extractRoot "_update-manifest.json"
        if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
            throw "Pakken mangler sit interne manifest."
        }
        $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
        if ([string]$manifest.version -ne [string]$latest.version) {
            throw "Pakkens version matcher ikke latest.json."
        }

        $entries = @($manifest.files)
        if (-not $entries.Count) { throw "Opdateringspakken indeholder ingen programfiler." }
        foreach ($entry in $entries) {
            $target = Get-SafeTarget ([string]$entry.path)
            $sourcePath = Join-Path $extractRoot (([string]$entry.path) -replace '/', '\')
            if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
                throw "En fil fra manifestet mangler: $($entry.path)"
            }
            if ([long]$entry.size -ne (Get-Item -LiteralPath $sourcePath).Length -or
                (Get-FileSha256 $sourcePath) -ne ([string]$entry.sha256).ToLowerInvariant()) {
                throw "En fil i pakken er beskadiget: $($entry.path)"
            }
        }

        $newPaths = @{}
        foreach ($entry in $entries) {
            $newPaths[[string]$entry.path] = $true
        }
        $obsoletePaths = @()
        if ($current -and $current.files) {
            foreach ($oldPath in @($current.files)) {
                $oldPath = [string]$oldPath
                if (-not $newPaths.ContainsKey($oldPath)) {
                    [void](Get-SafeTarget $oldPath)
                    $obsoletePaths += $oldPath
                }
            }
        }

        $applied = New-Object System.Collections.Generic.List[string]
        try {
            foreach ($entry in $entries) {
                $relative = ([string]$entry.path) -replace '/', '\'
                $sourcePath = Join-Path $extractRoot $relative
                $target = Get-SafeTarget ([string]$entry.path)
                $targetDir = Split-Path -Parent $target
                New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
                if (Test-Path -LiteralPath $target -PathType Leaf) {
                    $backup = Join-Path $backupRoot $relative
                    New-Item -ItemType Directory -Path (Split-Path -Parent $backup) -Force | Out-Null
                    Copy-Item -LiteralPath $target -Destination $backup -Force
                }
                $applied.Add($relative)
                Copy-Item -LiteralPath $sourcePath -Destination $target -Force
            }
            foreach ($oldPath in $obsoletePaths) {
                $relative = $oldPath -replace '/', '\'
                $target = Get-SafeTarget $oldPath
                if (Test-Path -LiteralPath $target -PathType Leaf) {
                    $backup = Join-Path $backupRoot $relative
                    New-Item -ItemType Directory -Path (Split-Path -Parent $backup) -Force | Out-Null
                    Copy-Item -LiteralPath $target -Destination $backup -Force
                    $applied.Add($relative)
                    Remove-Item -LiteralPath $target -Force
                }
            }

            $newStatePath = Join-Path $tempRoot "new-state.json"
            [ordered]@{
                schema = 1
                version = [string]$latest.version
                updatedUtc = [DateTime]::UtcNow.ToString("o")
                files = @($entries | ForEach-Object { [string]$_.path })
            } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $newStatePath -Encoding UTF8
            Move-Item -LiteralPath $newStatePath -Destination $stateFile -Force
        } catch {
            $rollbackPaths = @($applied)
            [array]::Reverse($rollbackPaths)
            foreach ($relative in $rollbackPaths) {
                $target = Join-Path $PSScriptRoot $relative
                $backup = Join-Path $backupRoot $relative
                if (Test-Path -LiteralPath $backup -PathType Leaf) {
                    Copy-Item -LiteralPath $backup -Destination $target -Force -ErrorAction SilentlyContinue
                } else {
                    Remove-Item -LiteralPath $target -Force -ErrorAction SilentlyContinue
                }
            }
            throw
        }
    } finally {
        if (Test-Path -LiteralPath $tempRoot -PathType Container) {
            Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    Write-Host "Programmet er opdateret til $($latest.version)." -ForegroundColor Green
    & (Join-Path $PSHOME "powershell.exe") -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "Test-InstallState.ps1") -Quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Installationskravene er aendret. Koer SETUP.bat en gang; runtime, .env og data bevares." -ForegroundColor Yellow
    } else {
        Write-Host "SETUP.bat skal ikke koeres. Start programmet normalt." -ForegroundColor Green
    }
    exit 0
} catch {
    if ($CheckOnly) {
        [ordered]@{
            ok = $false
            updateAvailable = $false
            error = [string]$_.Exception.Message
        } | ConvertTo-Json -Compress
        exit 0
    }
    Write-Host "FEJL: $($_.Exception.Message)" -ForegroundColor Red
    if ($Automatic) {
        Write-Host "Den installerede version bruges videre." -ForegroundColor Yellow
        exit 0
    }
    exit 1
}
