param(
    [string]$RuntimePath = (Join-Path $PSScriptRoot "runtime"),
    [string]$ContractPath = (Join-Path $PSScriptRoot "runtime-contract.json")
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "tools\Install-Helpers.ps1")
$root = [IO.Path]::GetFullPath((Resolve-Path -LiteralPath $RuntimePath).ProviderPath).TrimEnd('\')
$contract = Get-Content -LiteralPath $ContractPath -Raw | ConvertFrom-Json
$metadataNames = @("runtime-manifest.json", "README.txt")
$files = Get-ChildItem -LiteralPath $root -Recurse -File |
    Where-Object { $metadataNames -notcontains $_.Name } |
    Sort-Object FullName |
    ForEach-Object {
        $full = [IO.Path]::GetFullPath($_.FullName)
        if (-not $full.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Filen ligger uden for runtime-mappen: $full"
        }
        [ordered]@{
            path = $full.Substring($root.Length).TrimStart('\').Replace('\', '/')
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
