$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot
$logPath = Join-Path $PSScriptRoot "systemtjek.txt"
$reportPath = Join-Path $PSScriptRoot "fejlrapport.zip"
$started = $false

function New-ErrorReport {
    param([string]$Destination)

    $stage = Join-Path ([IO.Path]::GetTempPath()) ("intake-fejlrapport-" + [Guid]::NewGuid().ToString("N"))
    try {
        New-Item -ItemType Directory -Path $stage -Force | Out-Null

        $summary = @(
            "Indtagelse - fejlrapport",
            "Oprettet: $([DateTime]::Now.ToString('yyyy-MM-dd HH:mm:ss zzz'))",
            "Computer: $env:COMPUTERNAME",
            "Windows-bruger: $env:USERDOMAIN\$env:USERNAME",
            "Projektmappe: $PSScriptRoot",
            "",
            "Rapporten indeholder kun tekstlogs og installationsstatus.",
            "Den indeholder ikke .env, adgangskoder, runtime, lydfiler eller databasen."
        )
        $summary | Set-Content -LiteralPath (Join-Path $stage "rapportinfo.txt") -Encoding UTF8

        $copySanitized = {
            param([string]$Source, [string]$Target)
            $content = [IO.File]::ReadAllText($Source)
            $content = [regex]::Replace($content, '(?im)(APP_PASSWORD\s*=\s*)\S+', '$1[SKJULT]')
            $content = [regex]::Replace($content, '(?im)(SECRET_KEY\s*=\s*)\S+', '$1[SKJULT]')
            [IO.File]::WriteAllText($Target, $content, (New-Object Text.UTF8Encoding($false)))
        }

        foreach ($name in @(
            "setup-log.txt", "systemtjek.txt", "install-state.json"
        )) {
            $source = Join-Path $PSScriptRoot $name
            if (Test-Path -LiteralPath $source -PathType Leaf) {
                & $copySanitized $source (Join-Path $stage $name)
            }
        }

        $appLog = Join-Path $PSScriptRoot "data\logs\app.log"
        if (Test-Path -LiteralPath $appLog -PathType Leaf) {
            & $copySanitized $appLog (Join-Path $stage "app.log")
        }

        if (Test-Path -LiteralPath $Destination -PathType Leaf) {
            Remove-Item -LiteralPath $Destination -Force
        }
        Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $Destination -CompressionLevel Optimal -Force
        return $true
    } catch {
        Write-Host "ADVARSEL Fejlrapporten kunne ikke oprettes: $($_.Exception.Message)" -ForegroundColor Yellow
        return $false
    } finally {
        if (Test-Path -LiteralPath $stage -PathType Container) {
            Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

try {
    try {
        Start-Transcript -LiteralPath $logPath -Force | Out-Null
        $started = $true
    } catch { }
    & (Join-Path $PSScriptRoot "check_setup.ps1")
    $exitCode = $LASTEXITCODE
} finally {
    if ($started) { try { Stop-Transcript | Out-Null } catch { } }
}
Write-Host ""
Write-Host "Systemtjekket er gemt her: $logPath" -ForegroundColor Cyan
if (New-ErrorReport -Destination $reportPath) {
    Write-Host "Samlet fejlrapport er gemt her: $reportPath" -ForegroundColor Cyan
    Write-Host "Send kun fejlrapport.zip til IT, hvis problemet fortsætter." -ForegroundColor Cyan
}
exit $exitCode
