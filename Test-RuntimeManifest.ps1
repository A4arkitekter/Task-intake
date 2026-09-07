param(
    [string]$RuntimePath = (Join-Path $PSScriptRoot "runtime"),
    [string]$ContractPath = (Join-Path $PSScriptRoot "runtime-contract.json")
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "tools\Install-Helpers.ps1")

if (-not (Test-Path -LiteralPath $RuntimePath -PathType Container)) {
    throw "Runtime-mappen mangler: $RuntimePath"
}
if (-not (Test-Path -LiteralPath $ContractPath -PathType Leaf)) {
    throw "GitHub-kodens runtime-kontrakt mangler: $ContractPath"
}

$root = [IO.Path]::GetFullPath((Resolve-Path -LiteralPath $RuntimePath).ProviderPath).TrimEnd('\')
$manifestPath = Join-Path $root "runtime-manifest.json"
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Runtime-manifest mangler: $manifestPath"
}

$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$contract = Get-Content -LiteralPath $ContractPath -Raw | ConvertFrom-Json
$contractFields = @("whisperModel", "whisperRepo", "ollamaModel")
$errors = 0

if ([int]$manifest.schema -ne [int]$contract.manifestSchema) {
    Write-Host "FEJL Runtime-manifestets schema passer ikke til programversionen." -ForegroundColor Red
    $errors++
}
foreach ($field in $contractFields) {
    if ([string]$manifest.$field -ne [string]$contract.$field) {
        Write-Host "FEJL Runtime-versionen passer ikke til GitHub-koden: $field" -ForegroundColor Red
        $errors++
    }
}

$metadataFiles = @("README.txt")
$checked = 0
$manifestPaths = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($entry in $manifest.files) {
    if ($metadataFiles -contains $entry.path) { continue }

    $checked++
    $relativePath = ([string]$entry.path).Replace('\', '/')
    if ([System.IO.Path]::IsPathRooted($relativePath) -or $relativePath -match '(^|/|\\)\.\.(/|\\|$)') {
        Write-Host "FEJL Ugyldig sti i runtime-manifest: $relativePath" -ForegroundColor Red
        $errors++
        continue
    }
    if (-not $manifestPaths.Add($relativePath)) {
        Write-Host "FEJL Dobbelt fil i runtime-manifest: $relativePath" -ForegroundColor Red
        $errors++
        continue
    }
    $path = Join-Path $root ($relativePath.Replace('/', '\'))
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        Write-Host "FEJL Mangler: $relativePath" -ForegroundColor Red
        $errors++
        continue
    }
    $item = Get-Item -LiteralPath $path
    if ($item.Length -ne [long]$entry.bytes) {
        Write-Host "FEJL Forkert størrelse: $relativePath" -ForegroundColor Red
        $errors++
        continue
    }
    $hash = Get-FileSha256 $path
    if ($hash -ne [string]$entry.sha256) {
        Write-Host "FEJL Forkert checksum: $relativePath" -ForegroundColor Red
        $errors++
    }
}

$actualFiles = Get-ChildItem -LiteralPath $root -Recurse -File | ForEach-Object {
    $_.FullName.Substring($root.Length).TrimStart('\').Replace('\', '/')
} | Where-Object { $_ -notin @("runtime-manifest.json", "README.txt") }
foreach ($relativePath in $actualFiles) {
    if (-not $manifestPaths.Contains($relativePath)) {
        Write-Host "FEJL Ukendt fil findes i runtime, men ikke i manifestet: $relativePath" -ForegroundColor Red
        $errors++
    }
}

if ($checked -eq 0) {
    Write-Host "FEJL Runtime-manifestet indeholder ingen runtime-filer." -ForegroundColor Red
    $errors++
}
if ($errors) {
    Write-Host ""
    Write-Host "STOP: Runtime-mappen er ufuldstændig, beskadiget eller fra en anden version." -ForegroundColor Red
    Write-Host "Kopiér HELE runtime-mappen igen fra \\a4diskstation4\A4software\task-intake\runtime." -ForegroundColor Yellow
    throw "Runtime-manifest fejlede med $errors fejl."
}
Write-Host "Runtime passer til programversionen: $checked runtime-filer godkendt." -ForegroundColor Green
