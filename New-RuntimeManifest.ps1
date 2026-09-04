param(
    [string]$RuntimePath = (Join-Path $PSScriptRoot "runtime"),
    [string]$ContractPath = (Join-Path $PSScriptRoot "runtime-contract.json")
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "tools\Install-Helpers.ps1")
$root = (Resolve-Path -LiteralPath $RuntimePath).Path
$contract = Get-Content -LiteralPath $ContractPath -Raw | ConvertFrom-Json
$metadataPaths = @(
    (Join-Path $root "runtime-manifest.json"),
    (Join-Path $root "README.txt")
)
$files = Get-ChildItem -LiteralPath $root -Recurse -File |
    Where-Object { $metadataPaths -notcontains $_.FullName } |
    Sort-Object FullName |
    ForEach-Object {
        [ordered]@{
            path = $_.FullName.Substring($root.Length).TrimStart('\').Replace('\', '/')
            bytes = $_.Length
            sha256 = Get-FileSha256 $_.FullName
        }
    }

if ($files.Count -eq 0) { throw "Runtime-mappen indeholder ingen filer." }
$manifest = [ordered]@{
    schema = [int]$contract.manifestSchema
    createdUtc = [DateTime]::UtcNow.ToString("o")
    whisperModel = [string]$contract.whisperModel
    whisperRepo = [string]$contract.whisperRepo
    ollamaModel = [string]$contract.ollamaModel
    files = @($files)
}
$target = Join-Path $root "runtime-manifest.json"
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $target -Encoding utf8
Write-Host "Runtime-manifest skrevet fra GitHub-kontrakten: $target" -ForegroundColor Green
