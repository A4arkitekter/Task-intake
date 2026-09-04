param([string]$Destination)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$defaultDestination = "\\a4diskstation4\A4software\task-intake\updates"

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

$tempRoot = $null
try {
    & (Join-Path $PSScriptRoot "Test-GitContents.ps1")
    $dirty = @(& git status --porcelain)
    if ($LASTEXITCODE -ne 0) { throw "Git-status kunne ikke laeses." }
    if ($dirty.Count) { throw "Commit aendringerne, foer en opdatering udgives." }

    if (-not $Destination) { $Destination = $defaultDestination }
    $Destination = [IO.Path]::GetFullPath($Destination)
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null

    $commit = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $commit) { throw "Git-versionen kunne ikke bestemmes." }
    $version = $commit.Substring(0, 12)
    $files = @(& git ls-files)
    if ($LASTEXITCODE -ne 0 -or -not $files.Count) { throw "Git-filerne kunne ikke laeses." }

    $tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("intake-publish-" + [Guid]::NewGuid().ToString("N"))
    $stage = Join-Path $tempRoot "package"
    New-Item -ItemType Directory -Path $stage -Force | Out-Null
    $manifestFiles = @()
    foreach ($file in $files) {
        $source = Join-Path $PSScriptRoot $file
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Git-filen mangler: $file" }
        $target = Join-Path $stage $file
        New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
        Copy-Item -LiteralPath $source -Destination $target -Force
        $manifestFiles += [ordered]@{
            path = $file.Replace('\', '/')
            size = (Get-Item -LiteralPath $target).Length
            sha256 = Get-FileSha256 $target
        }
    }

    [ordered]@{
        schema = 1
        version = $version
        commit = $commit
        createdUtc = [DateTime]::UtcNow.ToString("o")
        files = $manifestFiles
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $stage "_update-manifest.json") -Encoding UTF8

    $packageName = "intake-update-$version.zip"
    $localPackage = Join-Path $tempRoot $packageName
    Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $localPackage -CompressionLevel Optimal
    $publishedPackage = Join-Path $Destination $packageName
    Copy-Item -LiteralPath $localPackage -Destination $publishedPackage -Force
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "OPDATER.bat") -Destination (Join-Path $Destination "OPDATER.bat") -Force
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "Update-Intake.ps1") -Destination (Join-Path $Destination "Update-Intake.ps1") -Force

    $latest = [ordered]@{
        schema = 1
        version = $version
        package = $packageName
        size = (Get-Item -LiteralPath $publishedPackage).Length
        sha256 = Get-FileSha256 $publishedPackage
        createdUtc = [DateTime]::UtcNow.ToString("o")
    }
    $latestTemp = Join-Path $Destination ("latest-" + [Guid]::NewGuid().ToString("N") + ".json")
    $latest | ConvertTo-Json | Set-Content -LiteralPath $latestTemp -Encoding UTF8
    Move-Item -LiteralPath $latestTemp -Destination (Join-Path $Destination "latest.json") -Force

    Write-Host "Opdatering $version er udgivet til $Destination" -ForegroundColor Green
    Write-Host "Kollegainstallationer henter den ved naeste start eller med knappen i indbakken."
    Write-Host "Eksisterende installationer uden updater kan hente OPDATER.bat og Update-Intake.ps1 her en gang." -ForegroundColor Yellow
} finally {
    if ($tempRoot -and (Test-Path -LiteralPath $tempRoot -PathType Container)) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
